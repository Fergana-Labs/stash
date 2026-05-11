"""Public share-link routes (Phase 5).

Two prefixes:
- ``/api/v1/stashes/{id}/shares/*`` (auth required) — sender mints/lists/revokes.
- ``/api/v1/shares/{token}/*`` (no auth) — recipient resolution + ask.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ..auth import get_current_user, get_current_user_optional
from ..services import ask_service, share_service, workspace_service

sender_router = APIRouter(prefix="/api/v1/stashes", tags=["shares"])
public_router = APIRouter(prefix="/api/v1/shares", tags=["shares-public"])


class CreateShareRequest(BaseModel):
    permission: str = "view"
    ttl_days: int | None = 14


@sender_router.post("/{stash_id}/shares")
async def mint_share_link(
    stash_id: UUID,
    req: CreateShareRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a stash member")
    if req.permission not in ("view", "comment", "edit-request"):
        raise HTTPException(status_code=400, detail="Invalid permission")
    return await share_service.create_link(
        stash_id=stash_id,
        creator_id=current_user["id"],
        ttl_days=req.ttl_days,
        permission=req.permission,
    )


@sender_router.get("/{stash_id}/shares")
async def list_share_links(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    if not await workspace_service.is_member(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a stash member")
    return await share_service.list_links(stash_id)


@sender_router.delete("/{stash_id}/shares/{token}", status_code=204)
async def revoke_share_link(
    stash_id: UUID,
    token: str,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a stash member")
    if not await share_service.revoke_link(token, stash_id):
        raise HTTPException(status_code=404, detail="Share link not found")


# --- Recipient routes (no auth) ---


def _check_token_status(status: str) -> None:
    if status == "missing":
        raise HTTPException(status_code=404, detail="Share link not found")
    if status == "revoked":
        raise HTTPException(status_code=410, detail="Share link revoked")
    if status == "expired":
        raise HTTPException(status_code=410, detail="Share link expired")


@public_router.get("/{token}")
async def resolve_share(
    token: str,
    request: Request,
    current_user: dict | None = Depends(get_current_user_optional),
):
    resolved = await share_service.resolve_token(token)
    _check_token_status(resolved["status"])
    link = resolved["link"]

    # Best-effort view counter; never blocks the response.
    try:
        viewer_id = current_user["id"] if current_user else None
        await share_service.record_view(token, viewer_id)
    except Exception:
        pass

    return await share_service.public_projection(link["workspace_id"], link)


class RecipientAskRequest(BaseModel):
    messages: list[dict]
    scope: str = "stash"


@public_router.post("/{token}/ask")
async def recipient_ask(token: str, req: RecipientAskRequest):
    resolved = await share_service.resolve_token(token)
    _check_token_status(resolved["status"])
    link = resolved["link"]
    from ..database import get_pool

    pool = get_pool()
    stash = await pool.fetchrow("SELECT name FROM workspaces WHERE id = $1", link["workspace_id"])
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    return StreamingResponse(
        ask_service.stream_ask(
            link["workspace_id"],
            stash["name"],
            req.messages,
            tool_set=ask_service.RECIPIENT_TOOL_SET,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RequestEditRequest(BaseModel):
    email: str | None = None
    message: str = ""


@public_router.post("/{token}/request-edit")
async def request_edit(token: str, req: RequestEditRequest):
    resolved = await share_service.resolve_token(token)
    _check_token_status(resolved["status"])
    # For now, just record it as a view event. A future change can route to a
    # notification system. The UI shows the user a confirmation either way.
    return {"status": "submitted", "email": req.email}


class ForkShareRequest(BaseModel):
    name: str | None = None


@public_router.post("/{token}/fork")
async def fork_via_share(
    token: str,
    req: ForkShareRequest,
    current_user: dict = Depends(get_current_user),
):
    resolved = await share_service.resolve_token(token)
    _check_token_status(resolved["status"])
    link = resolved["link"]
    new_ws = await workspace_service.fork_workspace(
        source_id=link["workspace_id"],
        forker_id=current_user["id"],
        name=req.name,
    )
    if not new_ws:
        raise HTTPException(status_code=404, detail="Stash not found or not forkable")
    return {"id": str(new_ws["id"]), "name": new_ws["name"]}
