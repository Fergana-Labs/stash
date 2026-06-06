"""Session folders: the shareable unit for sessions.

A folder groups related sessions (one per project/repo, plus a per-workspace
Default that catches chat-UI and un-targeted CLI sessions). Folders share the
same access model as cartridges — a (workspace_permission, public_permission)
pair computed into private/workspace/public — and access cascades to the
sessions inside (see permission_service). Public folders are reachable by slug
without login, rendered by the same session viewer.
"""

from __future__ import annotations

import re
import secrets
from uuid import UUID

from ..database import get_pool
from . import permission_service

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_GENERAL_PERMISSION_VALUES = {"none", "read", "write"}

DEFAULT_FOLDER_NAME = "Default"

_FOLDER_COLS = (
    "sf.id, sf.workspace_id, sf.slug, sf.name, sf.owner_user_id, "
    "owner_user.name AS owner_name, owner_user.display_name AS owner_display_name, "
    "CASE WHEN sf.public_permission != 'none' THEN 'public' ELSE 'private' END AS access, "
    "sf.workspace_permission, sf.public_permission, "
    "sf.discoverable, sf.cover_image_url, sf.view_count, sf.is_default, "
    "sf.created_at, sf.updated_at, "
    "(SELECT COUNT(*) FROM sessions s "
    " WHERE s.session_folder_id = sf.id AND s.deleted_at IS NULL) AS session_count, "
    "(SELECT COUNT(*) FROM shares sh WHERE sh.object_type = 'session_folder' "
    " AND sh.object_id = sf.id AND sh.principal_type = 'user') AS share_count"
)
_FOLDER_FROM = "FROM session_folders sf JOIN users owner_user ON owner_user.id = sf.owner_user_id"
_FOLDER_SELECT = f"SELECT {_FOLDER_COLS} {_FOLDER_FROM}"


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower()).strip("-")[:64] or "folder"
    return f"{base}-{secrets.token_urlsafe(4)[:6].lower()}"


# Visibility is a two-state axis now (the old "workspace" tier collapsed into
# private after the 1:1 workspace↔user migration). "Shared" is derived in the UI
# from the invite (share_count) list, not stored here.
def _visibility_for_permissions(workspace_permission: str, public_permission: str) -> str:
    return "public" if public_permission != "none" else "private"


def _validate_permissions(
    workspace_permission: str, public_permission: str, discoverable: bool
) -> None:
    if workspace_permission not in _GENERAL_PERMISSION_VALUES:
        raise ValueError("Unsupported workspace folder permission")
    if public_permission not in _GENERAL_PERMISSION_VALUES:
        raise ValueError("Unsupported public folder permission")
    if discoverable and public_permission == "none":
        raise ValueError("Discoverable folders must be public")


def _row(r) -> dict:
    return {
        "id": str(r["id"]),
        "workspace_id": str(r["workspace_id"]),
        "slug": r["slug"],
        "name": r["name"],
        "owner_user_id": str(r["owner_user_id"]),
        "owner_name": r["owner_name"],
        "owner_display_name": r["owner_display_name"],
        "access": r["access"],
        "workspace_permission": r["workspace_permission"],
        "public_permission": r["public_permission"],
        "discoverable": r["discoverable"],
        "cover_image_url": r["cover_image_url"],
        "view_count": int(r["view_count"]),
        "is_default": r["is_default"],
        "session_count": int(r["session_count"] or 0),
        "share_count": int(r["share_count"] or 0),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


async def create_folder(
    workspace_id: UUID,
    owner_user_id: UUID,
    name: str,
    *,
    workspace_permission: str = "read",
    public_permission: str = "none",
    discoverable: bool = False,
    is_default: bool = False,
) -> dict:
    _validate_permissions(workspace_permission, public_permission, discoverable)
    r = await get_pool().fetchrow(
        f"WITH inserted AS ("
        "  INSERT INTO session_folders "
        "    (workspace_id, owner_user_id, name, slug, workspace_permission, "
        "     public_permission, discoverable, is_default) "
        "  VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
        "  RETURNING *"
        f") {_FOLDER_SELECT.replace('session_folders sf', 'inserted sf')}",
        workspace_id,
        owner_user_id,
        name,
        _slugify(name),
        workspace_permission,
        public_permission,
        discoverable,
        is_default,
    )
    return _row(r)


async def ensure_default_folder(workspace_id: UUID, owner_user_id: UUID) -> dict:
    """Get-or-create the workspace's single Default folder. Sessions that aren't
    pushed to a specific folder land here (chat-UI + un-targeted CLI sessions)."""
    existing = await get_pool().fetchrow(
        f"{_FOLDER_SELECT} WHERE sf.workspace_id = $1 AND sf.is_default",
        workspace_id,
    )
    if existing:
        return _row(existing)
    return await create_folder(
        workspace_id,
        owner_user_id,
        DEFAULT_FOLDER_NAME,
        workspace_permission="read",
        is_default=True,
    )


async def list_folders(workspace_id: UUID, user_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        f"{_FOLDER_SELECT} "
        "WHERE sf.workspace_id = $1 "
        "AND (sf.owner_user_id = $2 "
        "  OR sf.public_permission != 'none' "
        "  OR (sf.workspace_permission != 'none' AND EXISTS ("
        "    SELECT 1 FROM workspace_members wm "
        "    WHERE wm.workspace_id = sf.workspace_id AND wm.user_id = $2"
        "  )) "
        "  OR EXISTS ("
        "    SELECT 1 FROM shares sh "
        "    WHERE sh.object_type = 'session_folder' AND sh.object_id = sf.id "
        "      AND sh.principal_type = 'user' AND sh.principal_id = $2"
        "  )) "
        "ORDER BY sf.is_default DESC, sf.name",
        workspace_id,
        user_id,
    )
    return [_row(r) for r in rows]


async def get_folder(folder_id: UUID) -> dict | None:
    r = await get_pool().fetchrow(f"{_FOLDER_SELECT} WHERE sf.id = $1", folder_id)
    return _row(r) if r else None


async def user_can_manage(folder_id: UUID, user_id: UUID) -> bool:
    row = await get_pool().fetchrow(
        "SELECT workspace_id FROM session_folders WHERE id = $1",
        folder_id,
    )
    if not row:
        return False
    return await permission_service.check_access(
        "session_folder",
        folder_id,
        user_id,
        workspace_id=row["workspace_id"],
        require_write=True,
    )


async def update_folder(folder_id: UUID, user_id: UUID, updates: dict) -> dict | None:
    pool = get_pool()
    folder = await pool.fetchrow(
        "SELECT workspace_permission, public_permission FROM session_folders WHERE id = $1",
        folder_id,
    )
    if not folder or not await user_can_manage(folder_id, user_id):
        return None

    next_workspace_permission = (
        updates.get("workspace_permission") or folder["workspace_permission"]
    )
    next_public_permission = updates.get("public_permission") or folder["public_permission"]
    _validate_permissions(
        next_workspace_permission, next_public_permission, bool(updates.get("discoverable"))
    )
    if updates.get("public_permission") == "none" and updates.get("discoverable") is None:
        updates["discoverable"] = False

    sets, args, idx = [], [], 1
    clearable = {"cover_image_url"}
    for col in (
        "name",
        "workspace_permission",
        "public_permission",
        "discoverable",
        "cover_image_url",
    ):
        if col not in updates:
            continue
        val = updates[col]
        if val is None and col not in clearable:
            continue
        sets.append(f"{col} = ${idx}")
        args.append(val)
        idx += 1
    if sets:
        sets.append("updated_at = now()")
        args.append(folder_id)
        await pool.execute(f"UPDATE session_folders SET {', '.join(sets)} WHERE id = ${idx}", *args)
    return await get_folder(folder_id)


async def delete_folder(folder_id: UUID, user_id: UUID) -> bool:
    """Delete a folder. The Default folder can't be deleted; sessions inside a
    deleted folder fall back to unfiled (ON DELETE SET NULL)."""
    if not await user_can_manage(folder_id, user_id):
        return False
    row = await get_pool().fetchrow(
        "SELECT is_default FROM session_folders WHERE id = $1", folder_id
    )
    if not row or row["is_default"]:
        return False
    await get_pool().execute("DELETE FROM session_folders WHERE id = $1", folder_id)
    return True


async def assign_session(
    workspace_id: UUID,
    user_id: UUID,
    session_row_id: UUID,
    folder_id: UUID | None,
) -> bool:
    pool = get_pool()
    session = await pool.fetchrow(
        "SELECT id FROM sessions WHERE id = $1 AND workspace_id = $2",
        session_row_id,
        workspace_id,
    )
    if not session:
        return False

    can_write_session = await permission_service.check_access(
        "session",
        session_row_id,
        user_id,
        workspace_id=workspace_id,
        require_write=True,
    )
    if not can_write_session:
        return False

    if folder_id is not None:
        folder = await pool.fetchrow(
            "SELECT id FROM session_folders WHERE id = $1 AND workspace_id = $2",
            folder_id,
            workspace_id,
        )
        if not folder:
            return False
        can_write_folder = await permission_service.check_access(
            "session_folder",
            folder_id,
            user_id,
            workspace_id=workspace_id,
            require_write=True,
        )
        if not can_write_folder:
            return False

    result = await pool.execute(
        "UPDATE sessions SET session_folder_id = $2 WHERE id = $1 AND workspace_id = $3",
        session_row_id,
        folder_id,
        workspace_id,
    )
    return result == "UPDATE 1"


async def get_public_folder(slug: str, viewer_id: UUID | None = None) -> dict | None:
    """Resolve a folder by slug for the given viewer (None = anonymous). The
    folder is the privacy boundary: public folders render anonymously, workspace
    folders for members, private folders for the owner or explicitly-shared
    users. Bumps view_count on a successful read."""
    from . import permission_service

    pool = get_pool()
    row = await pool.fetchrow(f"{_FOLDER_SELECT} WHERE sf.slug = $1", slug)
    if not row:
        return None
    folder = _row(row)
    if not await permission_service.check_access(
        "session_folder", UUID(folder["id"]), viewer_id, workspace_id=UUID(folder["workspace_id"])
    ):
        return None
    await pool.execute(
        "UPDATE session_folders SET view_count = view_count + 1 WHERE id = $1", row["id"]
    )
    return folder


async def list_folder_sessions(folder_id: UUID) -> list[dict]:
    """Lightweight session summaries for a folder's public/drilled-in view,
    sourced the same way as /me/sessions but scoped to one folder."""
    rows = await get_pool().fetch(
        "SELECT s.id, s.session_id, s.agent_name, s.cwd, s.started_at, s.finished_at, "
        "  u.display_name AS user_name, "
        "  (SELECT COUNT(*) FROM history_events he "
        "   WHERE he.session_id = s.session_id AND he.workspace_id = s.workspace_id) AS event_count, "
        "  (SELECT MAX(he.created_at) FROM history_events he "
        "   WHERE he.session_id = s.session_id AND he.workspace_id = s.workspace_id) AS last_event_at "
        "FROM sessions s "
        "LEFT JOIN users u ON u.id = s.created_by "
        "WHERE s.session_folder_id = $1 AND s.deleted_at IS NULL "
        "ORDER BY s.started_at DESC NULLS LAST",
        folder_id,
    )
    return [
        {
            "id": str(r["id"]),
            "session_id": r["session_id"],
            "agent_name": r["agent_name"] or "",
            "cwd": r["cwd"],
            "user_name": r["user_name"],
            "event_count": int(r["event_count"] or 0),
            "started_at": r["started_at"],
            "last_event_at": r["last_event_at"],
        }
        for r in rows
    ]
