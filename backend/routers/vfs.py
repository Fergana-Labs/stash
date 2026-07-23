"""The Stash VFS as an HTTP endpoint.

Same surface as `stash vfs "<command>"`, for agents with no shell to install the
CLI into. Read-only: the shell has no write commands and rejects redirects.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from stashvfs import MountError

from ..auth import get_current_user
from ..services import vfs_service
from ..services.vfs_service import VfsBudgetExceeded

router = APIRouter(prefix="/api/v1/me/vfs", tags=["vfs"])

MAX_SCRIPT_LENGTH = 4096


class VfsRequest(BaseModel):
    script: str = Field(max_length=MAX_SCRIPT_LENGTH)
    cwd: str = "/"


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
    try:
        return await vfs_service.run_vfs_script(request.app, authorization, body.script, body.cwd)
    except MountError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except VfsBudgetExceeded as e:
        raise HTTPException(status_code=413, detail=str(e)) from e


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
