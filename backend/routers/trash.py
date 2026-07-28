"""Trash router: aggregate listing of soft-deleted pages, files, and sessions."""

from uuid import UUID

from fastapi import APIRouter, Depends

from ..auth import get_read_scopes
from ..database import get_pool
from ..services import (
    files_service,
    files_tree_service,
    session_service,
)

router = APIRouter(prefix="/api/v1/me", tags=["trash"])


async def _fan_out(list_for_scope, read_scopes: list[UUID]) -> list[dict]:
    """Run a single-scope listing across every scope the caller reads, tagging
    each row with the scope it came from.

    Trash is unpaginated, so gathering per scope and sorting in Python is exact.
    A spanning SQL predicate is the right tool once LIMIT/OFFSET is involved —
    merging pages of separate queries is not the same list.
    """
    rows: list[dict] = []
    for owner_user_id in read_scopes:
        for row in await list_for_scope(owner_user_id):
            rows.append({**row, "owner_user_id": owner_user_id})
    rows.sort(key=lambda row: row["deleted_at"], reverse=True)
    return rows


@router.get("/trash")
async def list_trash(
    read_scopes: list[UUID] = Depends(get_read_scopes),
):
    """Trash listing: pages + files + sessions, each sorted by deleted_at DESC.

    Spans every scope the caller reads — deleting something from a workspace
    then hunting for it in a scope switcher is the exact confusion this model
    removes. Each row carries `owner_user_id` so the UI can say which place it
    came from, and `deleted_by`'s display name so it can say who did it without
    a second round-trip.
    """
    pages = await _fan_out(files_tree_service.list_trashed_pages, read_scopes)
    files = await _fan_out(files_service.list_trashed_files, read_scopes)
    sessions = await _fan_out(session_service.list_trashed_sessions, read_scopes)

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
            "owner_user_id": str(row["owner_user_id"]),
            "deleted_at": row["deleted_at"],
            "deleted_by": str(row["deleted_by"]) if row.get("deleted_by") else None,
            "deleted_by_name": (actor["display_name"] or actor["name"] if actor else None),
        }

    return {
        "pages": [_render(p, "name") for p in pages],
        "files": [_render(f, "name") for f in files],
        "sessions": [_render(s, "session_id") for s in sessions],
    }
