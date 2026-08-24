"""The Stash VFS as an HTTP endpoint.

Same surface as `stash vfs "<command>"`, for agents with no shell to install the
CLI into. Read-only: the shell has no write commands and rejects redirects.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from stashvfs import MountError

from ..auth import get_current_user
from ..services import end_user_service, security_audit_service, source_service, vfs_service
from ..services.vfs_service import VfsBudgetExceeded

router = APIRouter(prefix="/api/v1/me/vfs", tags=["vfs"])

MAX_SCRIPT_LENGTH = 4096


class VfsRequest(BaseModel):
    # Unknown fields are refused, not dropped: a misspelled user_id would
    # otherwise run UNSCOPED — the whole workspace instead of one user's
    # view — which is an isolation failure, not a typo. Strictness is safe
    # here because only our own clients call this surface.
    model_config = ConfigDict(extra="forbid")

    script: str = Field(max_length=MAX_SCRIPT_LENGTH)
    cwd: str = "/"
    user_id: str | None = Field(
        None,
        max_length=128,
        description="External Multiplayer: narrow the tree to this end user — "
        "shared wiki at /memory, the user's own wiki and files under /files, "
        "the user's transcripts under /sessions",
    )


async def _end_user_ctx(current_user: dict, user_id: str | None) -> dict | None:
    """The developer contract: the caller's key belongs to the workspace's
    scope user, and user_id is asserted by their backend. Isolation between one
    developer's users is enforced at the developer boundary, not here.

    A user id with no row yet is a customer who has not been written for —
    their agent's very first turn reads before it records anything. That reads
    the shared wiki and an empty set of their own material, which is exactly
    right: the accumulated cross-user knowledge is what a new user benefits
    from on day one. The user appears once their first session is uploaded.
    """
    if user_id is None:
        return None
    workspace = await end_user_service.workspace_for_scope(current_user["id"])
    if workspace is None or workspace["external_wiki_folder_id"] is None:
        raise HTTPException(
            status_code=400,
            detail="user_id requires a developer workspace scope — activate the platform first",
        )
    end_user = await end_user_service.find_end_user(workspace["id"], user_id)
    if end_user is None:
        return {
            "external_id": user_id,
            "shared_wiki_folder_id": str(workspace["external_wiki_folder_id"]),
            "wiki_folder_id": None,
            "source_ids": set(),
        }
    connected = await source_service.list_connected_sources(
        current_user["id"], end_user_id=end_user["id"]
    )
    return {
        "external_id": end_user["external_id"],
        "shared_wiki_folder_id": str(workspace["external_wiki_folder_id"]),
        "wiki_folder_id": str(end_user["wiki_folder_id"]),
        "source_ids": {s["id"] for s in connected},
    }


class VfsSearch(BaseModel):
    pattern: str = Field(max_length=MAX_SCRIPT_LENGTH)
    roots: list[str] = Field(max_length=64)
    docs_scanned: int = Field(ge=0)


@router.post("")
async def run_vfs(
    body: VfsRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Run one bash-shaped script (`ls`, `cat`, `find`, `grep`, pipes) over the
    caller's Stash and return what a terminal would have shown.

    A non-zero `exit_code` is a shell result, not a transport failure — `grep`
    finding nothing exits 1. Callers read `stdout`/`stderr`, same as a shell.
    """
    authorization = request.headers.get("authorization")
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="The VFS runs every read as the calling credential; use an API key, not a cookie.",
        )
    end_user_ctx = await _end_user_ctx(current_user, body.user_id)
    try:
        return await vfs_service.run_vfs_script(
            request.app, authorization, body.script, body.cwd, end_user_ctx
        )
    except MountError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except VfsBudgetExceeded as e:
        raise HTTPException(status_code=413, detail=str(e)) from e


@router.post("/searches", status_code=204)
async def record_vfs_search(
    body: VfsSearch,
    current_user: dict = Depends(get_current_user),
):
    """The one search audit event standing in for a VFS grep. The grep's
    per-document reads carry via='scan' and are excluded from content-activity
    analytics; this row is what the dashboard counts, on the caller's real
    surface (cli for `stash vfs`, ask for the server-side VFS)."""
    await security_audit_service.record_event(
        action="source.searched",
        actor_user_id=current_user["id"],
        owner_user_id=current_user["id"],
        target_type="vfs",
        target_id=" ".join(body.roots),
        metadata={
            "query_hash": security_audit_service.hash_value(body.pattern),
            "docs_scanned": body.docs_scanned,
        },
    )


@router.get("/resolve")
async def resolve_path(
    path: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """The app route of the Stash object behind a VFS path (`app_url` is null
    for synthetic nodes like `_index.jsonl`). Chat citations deep-link
    through this."""
    authorization = request.headers.get("authorization")
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="The VFS runs every read as the calling credential; use an API key, not a cookie.",
        )
    try:
        return await vfs_service.resolve_vfs_path(request.app, authorization, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"No such path: {path}") from e
    except MountError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
