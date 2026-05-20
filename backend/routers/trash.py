"""Trash router: aggregate listing of soft-deleted pages, files, and sessions."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..database import get_pool
from ..services import (
    files_service,
    files_tree_service,
    session_service,
    workspace_service,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["trash"])


async def _check_write(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.can_write(workspace_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="Viewers can read but not modify trash",
        )


@router.get("/trash")
async def list_trash(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Trash listing: pages + files + sessions, each sorted by deleted_at DESC.

    Includes deleted_by display name so the UI can show "Deleted by Alice"
    without a second round-trip.
    """
    await _check_write(workspace_id, current_user["id"])

    pages = await files_tree_service.list_trashed_pages(workspace_id)
    files = await files_service.list_trashed_files(workspace_id)
    sessions = await session_service.list_trashed_sessions(workspace_id)

    actor_ids = {row["deleted_by"] for row in pages + files + sessions if row.get("deleted_by")}
    actors: dict[UUID, dict] = {}
    if actor_ids:
        pool = get_pool()
        actor_rows = await pool.fetch(
            "SELECT id, name, display_name FROM users WHERE id = ANY($1::uuid[])",
            list(actor_ids),
        )
        actors = {
            r["id"]: {"name": r["name"], "display_name": r["display_name"]} for r in actor_rows
        }

    def _render(row: dict, name_key: str) -> dict:
        actor = actors.get(row.get("deleted_by")) if row.get("deleted_by") else None
        return {
            "id": str(row["id"]),
            "name": row[name_key],
            "deleted_at": row["deleted_at"],
            "deleted_by": str(row["deleted_by"]) if row.get("deleted_by") else None,
            "deleted_by_name": (actor["display_name"] or actor["name"] if actor else None),
        }

    return {
        "pages": [_render(p, "name") for p in pages],
        "files": [_render(f, "name") for f in files],
        "sessions": [_render(s, "session_id") for s in sessions],
    }
