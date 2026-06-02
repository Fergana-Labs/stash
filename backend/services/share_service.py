"""Sharing: grant a principal (user or cartridge) access to an object.

Primary path is sharing a folder/file/session with a person by email. Only the
object's owner (its workspace member) may share it. Folder/session-folder shares
cascade to contents — that's handled at read time by permission_service, not here.

Sharing with an email that isn't a Stash user yet raises 404 for now; a pending
invite that converts on signup is a follow-up.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from ..database import get_pool
from . import permission_service

_SHAREABLE = {"file", "page", "folder", "session", "session_folder"}
_PERMISSIONS = {"read", "write"}


async def _require_owner(object_type: str, object_id: UUID, user_id: UUID) -> UUID:
    """The caller must own the object (be its workspace member). Returns workspace_id."""
    workspace_id = await permission_service.resolve_workspace_id(object_type, object_id)
    if workspace_id is None or not await permission_service.is_workspace_member(
        workspace_id, user_id
    ):
        raise HTTPException(status_code=404, detail="Not found")
    return workspace_id


async def share_with_user_by_email(
    *,
    object_type: str,
    object_id: UUID,
    email: str,
    permission: str,
    owner_id: UUID,
) -> dict:
    if object_type not in _SHAREABLE:
        raise HTTPException(status_code=400, detail=f"can't share a {object_type}")
    if permission not in _PERMISSIONS:
        raise HTTPException(status_code=400, detail="permission must be read or write")
    workspace_id = await _require_owner(object_type, object_id, owner_id)

    pool = get_pool()
    user = await pool.fetchrow("SELECT id FROM users WHERE lower(email) = lower($1)", email)
    if not user:
        raise HTTPException(status_code=404, detail=f"No Stash user with email {email}")
    if user["id"] == owner_id:
        raise HTTPException(status_code=400, detail="You already own this")
    row = await pool.fetchrow(
        """
        INSERT INTO shares (workspace_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by)
        VALUES ($1, $2, $3, 'user', $4, $5, $6)
        ON CONFLICT (object_type, object_id, principal_type, principal_id)
        DO UPDATE SET permission = EXCLUDED.permission
        RETURNING id
        """,
        workspace_id,
        object_type,
        object_id,
        user["id"],
        permission,
        owner_id,
    )
    return {"id": str(row["id"]), "principal_type": "user", "principal_id": str(user["id"])}


async def unshare(
    *, object_type: str, object_id: UUID, principal_type: str, principal_id: UUID, owner_id: UUID
) -> None:
    await _require_owner(object_type, object_id, owner_id)
    await get_pool().execute(
        "DELETE FROM shares WHERE object_type = $1 AND object_id = $2 "
        "AND principal_type = $3 AND principal_id = $4",
        object_type,
        object_id,
        principal_type,
        principal_id,
    )


async def list_object_shares(object_type: str, object_id: UUID, owner_id: UUID) -> list[dict]:
    await _require_owner(object_type, object_id, owner_id)
    rows = await get_pool().fetch(
        """
        SELECT s.principal_type, s.principal_id, s.permission,
               u.name AS user_name, u.display_name AS user_display, u.email AS user_email,
               c.title AS cartridge_title
        FROM shares s
        LEFT JOIN users u ON s.principal_type = 'user' AND u.id = s.principal_id
        LEFT JOIN cartridges c ON s.principal_type = 'cartridge' AND c.id = s.principal_id
        WHERE s.object_type = $1 AND s.object_id = $2
        ORDER BY s.created_at
        """,
        object_type,
        object_id,
    )
    return [
        {
            "principal_type": r["principal_type"],
            "principal_id": str(r["principal_id"]),
            "permission": r["permission"],
            "label": r["user_display"] or r["user_name"] or r["cartridge_title"] or "",
            "email": r["user_email"],
        }
        for r in rows
    ]
