"""Session folders: a shareable grouping for sessions.

Owned by a user (like everything in their workspace); shareable via the `shares`
table, which cascades to the sessions inside (see permission_service).
"""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool


def _row(r) -> dict:
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "session_count": int(r.get("session_count") or 0),
    }


async def create_folder(workspace_id: UUID, owner_user_id: UUID, name: str) -> dict:
    r = await get_pool().fetchrow(
        "INSERT INTO session_folders (workspace_id, owner_user_id, name) "
        "VALUES ($1, $2, $3) RETURNING id, name",
        workspace_id,
        owner_user_id,
        name,
    )
    return _row(r)


async def list_folders(workspace_id: UUID, owner_user_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT sf.id, sf.name, "
        "  (SELECT COUNT(*) FROM sessions s WHERE s.session_folder_id = sf.id) AS session_count "
        "FROM session_folders sf "
        "WHERE sf.workspace_id = $1 AND sf.owner_user_id = $2 "
        "ORDER BY sf.name",
        workspace_id,
        owner_user_id,
    )
    return [_row(r) for r in rows]


async def assign_session(session_row_id: UUID, folder_id: UUID | None) -> None:
    await get_pool().execute(
        "UPDATE sessions SET session_folder_id = $2 WHERE id = $1",
        session_row_id,
        folder_id,
    )
