"""Sharing: grant a principal (user or cartridge) access to an object.

Primary path is sharing a folder/file/session with a person by email. Only the
object's owner (its workspace member) may share it. Folder/session-folder shares
cascade to contents — that's handled at read time by permission_service, not here.

Sharing with an email that isn't a Stash user yet records a pending invite
(`share_invites`); it converts to a real share when a user with that email signs
up — see `convert_pending_invites`, called from the register / Auth0 paths.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException

from ..database import get_pool
from . import permission_service

_SHAREABLE = {"file", "page", "folder", "session", "session_folder"}
_PERMISSIONS = {"read", "comment", "write"}


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
    expires_at: datetime | None = None,
) -> dict:
    if object_type not in _SHAREABLE:
        raise HTTPException(status_code=400, detail=f"can't share a {object_type}")
    if permission not in _PERMISSIONS:
        raise HTTPException(status_code=400, detail="permission must be read, comment, or write")
    workspace_id = await _require_owner(object_type, object_id, owner_id)

    pool = get_pool()
    user = await pool.fetchrow("SELECT id FROM users WHERE lower(email) = lower($1)", email)
    if not user:
        # No user with that email yet — stash a pending invite that converts on
        # their signup. We can't validate the address, so this never fails the
        # share; the owner sees it as "invited" until it converts.
        await pool.execute(
            """
            INSERT INTO share_invites (workspace_id, object_type, object_id, email,
                                       permission, created_by, expires_at)
            VALUES ($1, $2, $3, lower($4), $5, $6, $7)
            ON CONFLICT (object_type, object_id, email)
            DO UPDATE SET permission = EXCLUDED.permission, expires_at = EXCLUDED.expires_at
            """,
            workspace_id,
            object_type,
            object_id,
            email,
            permission,
            owner_id,
            expires_at,
        )
        return {"pending": True, "email": email.lower()}
    if user["id"] == owner_id:
        raise HTTPException(status_code=400, detail="You already own this")
    row = await pool.fetchrow(
        """
        INSERT INTO shares (workspace_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by, expires_at)
        VALUES ($1, $2, $3, 'user', $4, $5, $6, $7)
        ON CONFLICT (object_type, object_id, principal_type, principal_id)
        DO UPDATE SET permission = EXCLUDED.permission, expires_at = EXCLUDED.expires_at
        RETURNING id
        """,
        workspace_id,
        object_type,
        object_id,
        user["id"],
        permission,
        owner_id,
        expires_at,
    )
    if object_type == "stash":
        # Sharing a cartridge also rings the recipient's in-app invite bell.
        from . import cartridge_invite_service

        await cartridge_invite_service.create_or_update_invite(
            cartridge_id=object_id,
            recipient_user_id=user["id"],
            invited_by_user_id=owner_id,
            permission=permission,
        )
    return {"id": str(row["id"]), "principal_type": "user", "principal_id": str(user["id"])}


async def convert_pending_invites(user_id: UUID, email: str | None) -> int:
    """Turn this user's pending share_invites (matched by email) into real
    shares. Idempotent — safe to call on every signup/login. Returns the count
    converted."""
    if not email:
        return 0
    pool = get_pool()
    invites = await pool.fetch(
        "SELECT id, workspace_id, object_type, object_id, permission, created_by "
        "FROM share_invites WHERE lower(email) = lower($1)",
        email,
    )
    converted = 0
    for inv in invites:
        if inv["created_by"] == user_id:
            await pool.execute("DELETE FROM share_invites WHERE id = $1", inv["id"])
            continue
        await pool.execute(
            """
            INSERT INTO shares (workspace_id, object_type, object_id, principal_type,
                                principal_id, permission, created_by)
            VALUES ($1, $2, $3, 'user', $4, $5, $6)
            ON CONFLICT (object_type, object_id, principal_type, principal_id)
            DO UPDATE SET permission = EXCLUDED.permission
            """,
            inv["workspace_id"],
            inv["object_type"],
            inv["object_id"],
            user_id,
            inv["permission"],
            inv["created_by"],
        )
        await pool.execute("DELETE FROM share_invites WHERE id = $1", inv["id"])
        converted += 1
    return converted


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
    if object_type == "stash" and principal_type == "user":
        from . import cartridge_invite_service

        await cartridge_invite_service.delete_pending_invite(object_id, principal_id)


async def set_public_access(*, object_type: str, object_id: UUID, enabled: bool, owner_id: UUID) -> None:
    """Toggle the "anyone with the link" grant: one read-level shares row with
    the public principal. Folder grants cascade to contents like any share."""
    if object_type not in _PUBLICLY_SHAREABLE:
        raise HTTPException(status_code=400, detail=f"a {object_type} can't have a public link")
    workspace_id = await _require_owner(object_type, object_id, owner_id)
    pool = get_pool()
    if not enabled:
        await pool.execute(
            "DELETE FROM shares WHERE object_type = $1 AND object_id = $2 "
            "AND principal_type = 'public'",
            object_type,
            object_id,
        )
        return
    await pool.execute(
        """
        INSERT INTO shares (workspace_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by)
        VALUES ($1, $2, $3, 'public', $4, 'read', $5)
        ON CONFLICT (object_type, object_id, principal_type, principal_id) DO NOTHING
        """,
        workspace_id,
        object_type,
        object_id,
        permission_service.PUBLIC_PRINCIPAL_ID,
        owner_id,
    )


async def list_object_shares(object_type: str, object_id: UUID, owner_id: UUID) -> list[dict]:
    await _require_owner(object_type, object_id, owner_id)
    rows = await get_pool().fetch(
        """
        SELECT s.principal_type, s.principal_id, s.permission, s.expires_at,
               (s.expires_at IS NOT NULL AND s.expires_at <= now()) AS expired,
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
    # Owner view keeps expired rows (flagged) so the owner can renew/revoke.
    shares = [
        {
            "principal_type": r["principal_type"],
            "principal_id": str(r["principal_id"]),
            "permission": r["permission"],
            "label": r["user_display"] or r["user_name"] or r["cartridge_title"] or "",
            "email": r["user_email"],
            "pending": False,
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
            "expired": r["expired"],
        }
        for r in rows
    ]
    # Pending invites (shared to an email with no user yet) show as "invited".
    invites = await get_pool().fetch(
        "SELECT email, permission, expires_at, "
        "(expires_at IS NOT NULL AND expires_at <= now()) AS expired FROM share_invites "
        "WHERE object_type = $1 AND object_id = $2 ORDER BY created_at",
        object_type,
        object_id,
    )
    shares.extend(
        {
            "principal_type": "user",
            "principal_id": None,
            "permission": inv["permission"],
            "label": inv["email"],
            "email": inv["email"],
            "pending": True,
            "expires_at": inv["expires_at"].isoformat() if inv["expires_at"] else None,
            "expired": inv["expired"],
        }
        for inv in invites
    )
    return shares


async def list_shared_with_user(user_id: UUID) -> list[dict]:
    """Every object shared *with* this user (across workspaces) — the data behind
    the 'Shared with me' surface. Resolves each share to the object's name, its
    owning workspace, and who shared it."""
    rows = await get_pool().fetch(
        """
        SELECT s.object_type, s.object_id, s.permission, s.workspace_id,
               w.name AS workspace_name,
               COALESCE(u.display_name, u.name) AS shared_by,
               COALESCE(
                 (SELECT name FROM folders         WHERE id = s.object_id AND s.object_type = 'folder'),
                 (SELECT name FROM session_folders WHERE id = s.object_id AND s.object_type = 'session_folder'),
                 (SELECT name FROM pages           WHERE id = s.object_id AND s.object_type = 'page'),
                 (SELECT name FROM files           WHERE id = s.object_id AND s.object_type = 'file'),
                 (SELECT name FROM tables          WHERE id = s.object_id AND s.object_type = 'table'),
                 (SELECT COALESCE(st.title, sess.session_id)
                    FROM sessions sess
                    LEFT JOIN session_titles st
                      ON st.workspace_id = sess.workspace_id AND st.session_id = sess.session_id
                    WHERE sess.id = s.object_id AND s.object_type = 'session')
               ) AS name
        FROM shares s
        JOIN workspaces w ON w.id = s.workspace_id
        LEFT JOIN users u ON u.id = s.created_by
        WHERE s.principal_type = 'user' AND s.principal_id = $1
          AND (s.expires_at IS NULL OR s.expires_at > now())
        ORDER BY w.name, s.object_type, name
        """,
        user_id,
    )
    # Drop rows whose object was deleted out from under the share.
    return [
        {
            "object_type": r["object_type"],
            "object_id": str(r["object_id"]),
            "name": r["name"],
            "workspace_id": str(r["workspace_id"]),
            "workspace_name": r["workspace_name"],
            "shared_by": r["shared_by"],
            "permission": r["permission"],
        }
        for r in rows
        if r["name"] is not None
    ]


async def list_shared_session_folder_sessions(folder_id: UUID, user_id: UUID) -> list[dict]:
    """Sessions inside a session-folder shared with the user, in the same
    SessionSummary shape as /me/sessions so the viewer renders the full
    chronological/filter browser (not a bare list). Gated on the share."""
    if not await permission_service.check_access("session_folder", folder_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    rows = await get_pool().fetch(
        "SELECT s.id, s.workspace_id, w.name AS workspace_name, s.session_id, s.agent_name, "
        "       st.title, s.started_at, sf.name AS session_folder_name, "
        "       (ARRAY_AGG(NULLIF(u.display_name, '') ORDER BY he.created_at) "
        "        FILTER (WHERE NULLIF(u.display_name, '') IS NOT NULL))[1] AS user_name, "
        "       COUNT(he.id)::int AS event_count, "
        "       COALESCE(MAX(he.created_at), s.started_at) AS last_event_at "
        "FROM sessions s "
        "LEFT JOIN workspaces w ON w.id = s.workspace_id "
        "LEFT JOIN session_folders sf ON sf.id = s.session_folder_id "
        "LEFT JOIN session_titles st "
        "  ON st.workspace_id = s.workspace_id AND st.session_id = s.session_id "
        "LEFT JOIN history_events he "
        "  ON he.workspace_id = s.workspace_id AND he.session_id = s.session_id "
        "LEFT JOIN users u ON u.id = he.created_by "
        "WHERE s.session_folder_id = $1 AND s.deleted_at IS NULL "
        "GROUP BY s.id, s.workspace_id, w.name, s.session_id, s.agent_name, st.title, "
        "         s.started_at, sf.name "
        "ORDER BY last_event_at DESC",
        folder_id,
    )
    return [
        {
            "id": str(r["id"]),
            "session_id": r["session_id"],
            "title": r["title"] or r["session_id"],
            "linear_tickets": [],
            "workspace_id": str(r["workspace_id"]),
            "workspace_name": r["workspace_name"],
            "user_name": r["user_name"] or (r["agent_name"] or "agent"),
            "agent_name": r["agent_name"],
            "event_count": int(r["event_count"] or 0),
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "last_event_at": r["last_event_at"].isoformat() if r["last_event_at"] else None,
            "session_folder_id": str(folder_id),
            "session_folder_name": r["session_folder_name"],
        }
        for r in rows
    ]
