"""The Stash VFS as an HTTP endpoint.

Same surface as `stash vfs "<command>"`, for agents with no shell to install the
CLI into. Read-only: the shell has no write commands and rejects redirects.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from stashvfs import MountError

from ..auth import get_current_user
from ..services import org_service, security_audit_service, source_service, vfs_service
from ..services.vfs_service import VfsBudgetExceeded

router = APIRouter(prefix="/api/v1/me/vfs", tags=["vfs"])

MAX_SCRIPT_LENGTH = 4096


class VfsRequest(BaseModel):
    script: str = Field(max_length=MAX_SCRIPT_LENGTH)
    cwd: str = "/"
    org_id: str | None = Field(
        None,
        max_length=128,
        description="External Multiplayer: narrow the tree to this org — "
        "shared wiki at /memory, the org's notepad and files under /files, "
        "the org's transcripts under /sessions",
    )


async def _org_ctx(current_user: dict, org_id: str | None) -> dict | None:
    """The developer contract: the caller's key belongs to the workspace's
    scope user, and org_id is asserted by their backend. Unknown org or a
    non-workspace scope fails loud — isolation between one developer's orgs
    is enforced at the developer boundary, not here."""
    if org_id is None:
        return None
    try:
        org = await org_service.resolve_org_for_scope(current_user["id"], org_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    workspace = await org_service.workspace_for_scope(current_user["id"])
    connected = await source_service.list_connected_sources(current_user["id"], org_id=org["id"])
    return {
        "external_id": org["external_id"],
        "wiki_folder_id": str(workspace["external_wiki_folder_id"]),
        "notepad_folder_id": str(org["notepad_folder_id"]),
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
    org_ctx = await _org_ctx(current_user, body.org_id)
    try:
        return await vfs_service.run_vfs_script(
            request.app, authorization, body.script, body.cwd, org_ctx
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
