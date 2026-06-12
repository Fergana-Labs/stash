"""Workspace router: CRUD, membership, invite codes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user, get_current_user_optional
from ..models import (
    InviteTokenCreateRequest,
    InviteTokenCreateResponse,
    InviteTokenListResponse,
    InviteTokenSummary,
    RedeemInviteAuthedRequest,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from ..services import invite_token_service, storage_service, workspace_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


async def _serialize_workspace_for_viewer(
    workspace: dict, viewer_id: UUID | None
) -> WorkspaceResponse:
    is_member = bool(viewer_id and await workspace_service.is_member(workspace["id"], viewer_id))
    if not is_member:
        raise HTTPException(status_code=404, detail="Workspace not found")

    data = dict(workspace)
    return WorkspaceResponse(**data)


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    req: WorkspaceCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.create_workspace(
        name=req.name,
        description=req.description,
        creator_id=current_user["id"],
    )
    return WorkspaceResponse(**ws)


@router.get("/mine", response_model=WorkspaceListResponse)
async def list_my_workspaces(current_user: dict = Depends(get_current_user)):
    workspaces = await workspace_service.list_user_workspaces(current_user["id"])
    return WorkspaceListResponse(workspaces=[WorkspaceResponse(**w) for w in workspaces])


@router.post("/redeem-invite", response_model=WorkspaceResponse)
async def redeem_invite_authed(
    req: RedeemInviteAuthedRequest,
    current_user: dict = Depends(get_current_user),
):
    """Authenticated redeem: join the signed-in user to the workspace."""
    ws = await invite_token_service.redeem_as_existing_user(req.token, current_user["id"])
    if not ws:
        raise HTTPException(
            status_code=404, detail="Invite token is invalid, expired, or exhausted"
        )
    return WorkspaceResponse(**ws)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    current_user: dict | None = Depends(get_current_user_optional),
):
    ws = await workspace_service.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    viewer_id = current_user["id"] if current_user else None
    return await _serialize_workspace_for_viewer(ws, viewer_id)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    req: WorkspaceUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in workspace_service.ROLES_CAN_WRITE:
        raise HTTPException(
            status_code=403, detail="Workspace editors and admins can update workspace"
        )
    ws = await workspace_service.update_workspace(
        workspace_id,
        name=req.name,
        description=req.description,
        cover_image_url=req.cover_image_url,
        icon_url=req.icon_url,
        color_gradient=req.color_gradient,
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse(**ws)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    storage_keys = await workspace_service.delete_workspace(workspace_id, current_user["id"])
    if storage_keys is None:
        raise HTTPException(status_code=403, detail="Only workspace owners can delete")

    for storage_key in storage_keys:
        await storage_service.delete_file(storage_key)


@router.post("/join/{invite_code}", response_model=WorkspaceResponse)
async def join_workspace(
    invite_code: str,
    current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.join_by_invite(invite_code, current_user["id"])
    if not ws:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    return WorkspaceResponse(**ws)


@router.post("/{workspace_id}/invite-code/rotate", response_model=WorkspaceResponse)
async def rotate_invite_code(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.rotate_invite_code(workspace_id, current_user["id"])
    if not ws:
        raise HTTPException(status_code=403, detail="Only workspace admins can rotate invite code")
    return WorkspaceResponse(**ws)


@router.post("/{workspace_id}/leave", status_code=204)
async def leave_workspace(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    left = await workspace_service.leave_workspace(workspace_id, current_user["id"])
    if not left:
        raise HTTPException(status_code=400, detail="Cannot leave as the last workspace admin")


# ---------------------------------------------------------------------------
# Magic-link invite tokens (distinct from the workspace.invite_code shared secret)
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/invite-tokens", response_model=InviteTokenCreateResponse, status_code=201
)
async def create_invite_token(
    workspace_id: UUID,
    req: InviteTokenCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in workspace_service.ROLES_ADMIN:
        raise HTTPException(
            status_code=403, detail="Only workspace admins can create invite tokens"
        )
    ws = await workspace_service.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    row, raw = await invite_token_service.create_token(
        workspace_id=workspace_id,
        creator_id=current_user["id"],
        max_uses=req.max_uses,
        ttl_days=req.ttl_days,
    )
    return InviteTokenCreateResponse(
        id=row["id"],
        token=raw,
        workspace_id=row["workspace_id"],
        workspace_name=ws["name"],
        max_uses=row["max_uses"],
        expires_at=row["expires_at"],
    )


@router.get("/{workspace_id}/invite-tokens", response_model=InviteTokenListResponse)
async def list_invite_tokens(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in workspace_service.ROLES_ADMIN:
        raise HTTPException(status_code=403, detail="Only workspace admins can list invite tokens")
    tokens = await invite_token_service.list_tokens(workspace_id)
    return InviteTokenListResponse(tokens=[InviteTokenSummary(**t) for t in tokens])


@router.delete("/{workspace_id}/invite-tokens/{token_id}", status_code=204)
async def revoke_invite_token(
    workspace_id: UUID,
    token_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in workspace_service.ROLES_ADMIN:
        raise HTTPException(
            status_code=403, detail="Only workspace admins can revoke invite tokens"
        )
    ok = await invite_token_service.revoke_token(token_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Token not found or already revoked")
