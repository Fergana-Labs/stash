"""Sharing: grant a principal (user or skill) access to an object.

Primary path is sharing a folder/file/session with a person by email. Only the
object's owner may share it. Folder/session-folder shares
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
from . import permission_service, security_audit_service, user_scope_service

_SHAREABLE = {"file", "page", "folder", "session", "session_folder", "table", "source"}
_PERMISSIONS = {"read", "comment", "write"}


async def _require_owner(object_type: str, object_id: UUID, user_id: UUID) -> UUID:
    """The caller must be an owner of the object's scope."""
    owner_user_id = await permission_service.resolve_owner_user_id(object_type, object_id)
    if owner_user_id is None or not await user_scope_service.is_owner(owner_user_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    return owner_user_id


async def _record_share_event(
    *,
    action: str,
    actor_user_id: UUID,
    owner_user_id: UUID,
    object_type: str,
    object_id: UUID,
    metadata: dict,
) -> None:
    await security_audit_service.record_event(
        action=action,
        actor_user_id=actor_user_id,
        owner_user_id=owner_user_id,
        target_type=object_type,
        target_id=str(object_id),
        metadata=metadata,
    )


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
    owner_user_id = await _require_owner(object_type, object_id, owner_id)
    normalized_email = email.strip().lower()

    pool = get_pool()
    user = await pool.fetchrow(
        "SELECT id FROM users WHERE lower(email) = $1",
        normalized_email,
    )
    # Both branches below return an identical body. A different response for a
    # known vs unknown email would let any owner probe which
    # addresses have Stash accounts (a user-enumeration oracle). Owners see
    # invite-vs-share state via the shares listing instead.
    if not user:
        # No user with that email yet — stash a pending invite that converts on
        # their signup. We can't validate the address, so this never fails the
        # share; the owner sees it as "invited" until it converts.
        await pool.execute(
            """
            INSERT INTO share_invites (owner_user_id, object_type, object_id, email,
                                       permission, created_by, expires_at)
            VALUES ($1, $2, $3, lower($4), $5, $6, $7)
            ON CONFLICT (object_type, object_id, email)
            DO UPDATE SET permission = EXCLUDED.permission, expires_at = EXCLUDED.expires_at
            """,
            owner_user_id,
            object_type,
            object_id,
            normalized_email,
            permission,
            owner_id,
            expires_at,
        )
        await _record_share_event(
            action="share.invited",
            actor_user_id=owner_id,
            owner_user_id=owner_user_id,
            object_type=object_type,
            object_id=object_id,
            metadata={
                "permission": permission,
                "recipient_email_hash": security_audit_service.hash_value(normalized_email),
            },
        )
        return {"ok": True, "email": normalized_email}
    if user["id"] == owner_id:
        raise HTTPException(status_code=400, detail="You already own this")
    await pool.execute(
        """
        INSERT INTO shares (owner_user_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by, expires_at)
        VALUES ($1, $2, $3, 'user', $4, $5, $6, $7)
        ON CONFLICT (object_type, object_id, principal_type, principal_id)
        DO UPDATE SET permission = EXCLUDED.permission, expires_at = EXCLUDED.expires_at
        """,
        owner_user_id,
        object_type,
        object_id,
        user["id"],
        permission,
        owner_id,
        expires_at,
    )
    await _record_share_event(
        action="share.granted",
        actor_user_id=owner_id,
        owner_user_id=owner_user_id,
        object_type=object_type,
        object_id=object_id,
        metadata={
            "permission": permission,
            "principal_type": "user",
            "recipient_user_hash": security_audit_service.hash_value(str(user["id"])),
        },
    )
    return {"ok": True, "email": normalized_email}


async def convert_pending_invites(user_id: UUID, email: str | None) -> int:
    """Turn this user's pending share_invites (matched by email) into real
    shares. Idempotent — safe to call on every signup/login. Returns the count
    converted."""
    if not email:
        return 0
    pool = get_pool()
    # An invite that expired before signup must not grant anything — drop it.
    await pool.execute(
        "DELETE FROM share_invites WHERE lower(email) = lower($1) "
        "AND expires_at IS NOT NULL AND expires_at <= now()",
        email,
    )
    invites = await pool.fetch(
        "SELECT id, owner_user_id, object_type, object_id, email, permission, created_by, "
        "expires_at "
        "FROM share_invites WHERE lower(email) = lower($1)",
        email,
    )
    converted = 0
    for inv in invites:
        if inv["created_by"] == user_id:
            await pool.execute("DELETE FROM share_invites WHERE id = $1", inv["id"])
            continue
        # The converted share keeps the invite's time bound; permission_service
        # enforces shares.expires_at at read time.
        await pool.execute(
            """
            INSERT INTO shares (owner_user_id, object_type, object_id, principal_type,
                                principal_id, permission, created_by, expires_at)
            VALUES ($1, $2, $3, 'user', $4, $5, $6, $7)
            ON CONFLICT (object_type, object_id, principal_type, principal_id)
            DO UPDATE SET permission = EXCLUDED.permission, expires_at = EXCLUDED.expires_at
            """,
            inv["owner_user_id"],
            inv["object_type"],
            inv["object_id"],
            user_id,
            inv["permission"],
            inv["created_by"],
            inv["expires_at"],
        )
        await pool.execute("DELETE FROM share_invites WHERE id = $1", inv["id"])
        await _record_share_event(
            action="share.invite_converted",
            actor_user_id=inv["created_by"],
            owner_user_id=inv["owner_user_id"],
            object_type=inv["object_type"],
            object_id=inv["object_id"],
            metadata={
                "permission": inv["permission"],
                "recipient_email_hash": security_audit_service.hash_value(inv["email"]),
                "recipient_user_hash": security_audit_service.hash_value(str(user_id)),
            },
        )
        converted += 1
    return converted


async def unshare(
    *, object_type: str, object_id: UUID, principal_type: str, principal_id: UUID, owner_id: UUID
) -> None:
    owner_user_id = await _require_owner(object_type, object_id, owner_id)
    removed = await get_pool().fetchrow(
        "DELETE FROM shares WHERE object_type = $1 AND object_id = $2 "
        "AND principal_type = $3 AND principal_id = $4 "
        "RETURNING permission",
        object_type,
        object_id,
        principal_type,
        principal_id,
    )
    if removed:
        hash_key = "recipient_user_hash" if principal_type == "user" else "principal_id_hash"
        await _record_share_event(
            action="share.revoked",
            actor_user_id=owner_id,
            owner_user_id=owner_user_id,
            object_type=object_type,
            object_id=object_id,
            metadata={
                "permission": removed["permission"],
                "principal_type": principal_type,
                hash_key: security_audit_service.hash_value(str(principal_id)),
            },
        )


async def revoke_pending_invite_by_email(
    *,
    object_type: str,
    object_id: UUID,
    email: str,
    owner_id: UUID,
) -> None:
    owner_user_id = await _require_owner(object_type, object_id, owner_id)
    normalized_email = email.strip().lower()
    removed = await get_pool().fetchrow(
        "DELETE FROM share_invites "
        "WHERE object_type = $1 AND object_id = $2 AND lower(email) = $3 "
        "RETURNING permission",
        object_type,
        object_id,
        normalized_email,
    )
    if removed:
        await _record_share_event(
            action="share.invite_revoked",
            actor_user_id=owner_id,
            owner_user_id=owner_user_id,
            object_type=object_type,
            object_id=object_id,
            metadata={
                "permission": removed["permission"],
                "recipient_email_hash": security_audit_service.hash_value(normalized_email),
            },
        )


async def list_object_shares(object_type: str, object_id: UUID, owner_id: UUID) -> list[dict]:
    await _require_owner(object_type, object_id, owner_id)
    rows = await get_pool().fetch(
        """
        SELECT s.principal_type, s.principal_id, s.permission, s.expires_at,
               (s.expires_at IS NOT NULL AND s.expires_at <= now()) AS expired,
               u.name AS user_name, u.display_name AS user_display, u.email AS user_email,
               c.title AS skill_title
        FROM shares s
        LEFT JOIN users u ON s.principal_type = 'user' AND u.id = s.principal_id
        LEFT JOIN skills c ON s.principal_type = 'skill' AND c.id = s.principal_id
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
            "label": r["user_display"] or r["user_name"] or r["skill_title"] or "",
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
    """Every object shared *with* this user (across owners) — the data behind
    the 'Shared with me' surface. Resolves each share to the object's name, its
    owner, and who shared it."""
    rows = await get_pool().fetch(
        """
        SELECT s.object_type, s.object_id, s.permission, s.owner_user_id,
               COALESCE(ow.display_name, ow.name) AS owner_name,
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
                      ON st.owner_user_id = sess.owner_user_id AND st.session_id = sess.session_id
                    WHERE sess.id = s.object_id AND s.object_type = 'session')
               ) AS name
        FROM shares s
        JOIN users ow ON ow.id = s.owner_user_id
        LEFT JOIN users u ON u.id = s.created_by
        WHERE s.principal_type = 'user' AND s.principal_id = $1
          AND (s.expires_at IS NULL OR s.expires_at > now())
        ORDER BY owner_name, s.object_type, name
        """,
        user_id,
    )
    # Drop rows whose object was deleted out from under the share.
    return [
        {
            "object_type": r["object_type"],
            "object_id": str(r["object_id"]),
            "name": r["name"],
            "owner_user_id": str(r["owner_user_id"]),
            "owner_name": r["owner_name"],
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
        "SELECT s.id, s.owner_user_id, "
        "       COALESCE(ow.display_name, ow.name) AS owner_name, s.session_id, s.agent_name, "
        "       st.title, s.started_at, sf.name AS session_folder_name, "
        "       (ARRAY_AGG(NULLIF(u.display_name, '') ORDER BY he.created_at) "
        "        FILTER (WHERE NULLIF(u.display_name, '') IS NOT NULL))[1] AS user_name, "
        "       COUNT(he.id)::int AS event_count, "
        "       COALESCE(MAX(he.created_at), s.started_at) AS last_event_at "
        "FROM sessions s "
        "LEFT JOIN users ow ON ow.id = s.owner_user_id "
        "LEFT JOIN session_folders sf ON sf.id = s.session_folder_id "
        "LEFT JOIN session_titles st "
        "  ON st.owner_user_id = s.owner_user_id AND st.session_id = s.session_id "
        "LEFT JOIN history_events he "
        "  ON he.owner_user_id = s.owner_user_id AND he.session_id = s.session_id "
        "LEFT JOIN users u ON u.id = he.created_by "
        "WHERE s.session_folder_id = $1 AND s.deleted_at IS NULL "
        "GROUP BY s.id, s.owner_user_id, ow.display_name, ow.name, s.session_id, "
        "         s.agent_name, st.title, s.started_at, sf.name "
        "ORDER BY last_event_at DESC",
        folder_id,
    )
    return [
        {
            "id": str(r["id"]),
            "session_id": r["session_id"],
            "title": r["title"] or r["session_id"],
            "linear_tickets": [],
            "owner_user_id": str(r["owner_user_id"]),
            "owner_name": r["owner_name"],
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
