"""Workspace service: CRUD, membership, invite codes."""

import logging
import secrets
from uuid import UUID

from ..database import get_pool
from . import skill_seeds

logger = logging.getLogger(__name__)


async def create_workspace(
    name: str,
    description: str,
    creator_id: UUID,
    is_primary: bool = False,
) -> dict:
    """Create a workspace with the creator as owner.

    Pass is_primary=True to mark the creator's membership as their primary
    workspace — used by /publish as the fallback target when no workspace_id
    is supplied. Only the auto-provisioned signup workspace should pass this.
    """
    pool = get_pool()
    invite_code = ""
    for _ in range(5):
        invite_code = secrets.token_urlsafe(6)[:8]
        exists = await pool.fetchval(
            "SELECT 1 FROM workspaces WHERE invite_code = $1",
            invite_code,
        )
        if not exists:
            break

    row = await pool.fetchrow(
        "INSERT INTO workspaces (name, description, creator_id, invite_code) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, name, description, creator_id, invite_code, "
        "created_at, updated_at, cover_image_url, icon_url, color_gradient",
        name,
        description,
        creator_id,
        invite_code,
    )
    ws = dict(row)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role, is_primary) "
        "VALUES ($1, $2, 'owner', $3)",
        ws["id"],
        creator_id,
        is_primary,
    )
    ws["member_count"] = 1
    # Seed the default slides skill so the ask-the-workspace agent can
    # discover it via list_skills/read_skill when the user asks for a deck.
    # Failures here should not block workspace creation.
    try:
        await skill_seeds.seed_slides_skill(ws["id"], creator_id)
    except Exception:
        logger.exception("seed_slides_skill failed for workspace %s", ws["id"])
    return ws


async def get_primary_for_user(user_id: UUID) -> UUID | None:
    """Return the workspace id the user has marked primary, or None."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT workspace_id FROM workspace_members " "WHERE user_id = $1 AND is_primary LIMIT 1",
        user_id,
    )
    return row["workspace_id"] if row else None


async def get_workspace(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT w.id, w.name, w.description, w.creator_id, w.invite_code, "
        "w.created_at, w.updated_at, w.cover_image_url, w.icon_url, w.color_gradient, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w WHERE w.id = $1",
        workspace_id,
    )
    return dict(row) if row else None


async def list_user_workspaces(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT w.id, w.name, w.description, w.creator_id, w.invite_code, "
        "w.created_at, w.updated_at, w.cover_image_url, w.icon_url, w.color_gradient, "
        "wm.is_primary, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w "
        "JOIN workspace_members wm ON wm.workspace_id = w.id "
        "WHERE wm.user_id = $1 ORDER BY wm.is_primary DESC, w.created_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def update_workspace(
    workspace_id: UUID,
    name: str | None = None,
    description: str | None = None,
    cover_image_url: str | None = None,
    icon_url: str | None = None,
    color_gradient: str | None = None,
) -> dict | None:
    pool = get_pool()
    sets, args, idx = [], [], 1
    for col, val in (
        ("name", name),
        ("description", description),
        ("cover_image_url", cover_image_url),
        ("icon_url", icon_url),
        ("color_gradient", color_gradient),
    ):
        if val is not None:
            sets.append(f"{col} = ${idx}")
            args.append(val)
            idx += 1
    if not sets:
        return await get_workspace(workspace_id)
    sets.append("updated_at = now()")
    args.append(workspace_id)
    await pool.execute(
        f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ${idx}",
        *args,
    )
    return await get_workspace(workspace_id)


async def delete_workspace(workspace_id: UUID, user_id: UUID) -> list[str] | None:
    """Delete a workspace (owner only; None when refused). Returns the storage
    keys its rows referenced so the caller can purge the blobs — collected
    before, but purged only after, the DB delete, so a failed delete can never
    leave live rows pointing at destroyed storage objects."""
    pool = get_pool()
    role = await get_member_role(workspace_id, user_id)
    if role != "owner":
        return None

    rows = await pool.fetch(
        """
        SELECT storage_key
        FROM files
        WHERE workspace_id = $1

        UNION

        SELECT sa.storage_key
        FROM session_artifacts sa
        JOIN sessions s ON s.id = sa.session_id
        WHERE s.workspace_id = $1

        ORDER BY storage_key
        """,
        workspace_id,
    )
    result = await pool.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)
    if result != "DELETE 1":
        return None
    return [row["storage_key"] for row in rows]


async def join_workspace(workspace_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    exists = await pool.fetchval(
        "SELECT 1 FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    if exists:
        return await get_workspace(workspace_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        workspace_id,
        user_id,
    )
    return await get_workspace(workspace_id)


async def rotate_invite_code(workspace_id: UUID, user_id: UUID) -> dict | None:
    """Generate a new invite_code, invalidating the previous one. Owner only."""
    role = await get_member_role(workspace_id, user_id)
    if role != "owner":
        return None
    pool = get_pool()
    new_code = ""
    for _ in range(5):
        new_code = secrets.token_urlsafe(6)[:8]
        exists = await pool.fetchval(
            "SELECT 1 FROM workspaces WHERE invite_code = $1",
            new_code,
        )
        if not exists:
            break
    await pool.execute(
        "UPDATE workspaces SET invite_code = $1, updated_at = now() WHERE id = $2",
        new_code,
        workspace_id,
    )
    return await get_workspace(workspace_id)


async def join_by_invite(invite_code: str, user_id: UUID) -> dict | None:
    pool = get_pool()
    ws = await pool.fetchrow(
        "SELECT id FROM workspaces WHERE invite_code = $1",
        invite_code,
    )
    if not ws:
        return None
    return await join_workspace(ws["id"], user_id)


async def leave_workspace(workspace_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2 AND role != 'owner'",
        workspace_id,
        user_id,
    )
    if result == "DELETE 1":
        await pool.execute(
            "DELETE FROM webhooks WHERE workspace_id = $1 AND user_id = $2",
            workspace_id,
            user_id,
        )
        return True
    return False


async def get_members(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT u.id AS user_id, u.name, u.display_name, wm.role, wm.joined_at "
        "FROM workspace_members wm JOIN users u ON u.id = wm.user_id "
        "WHERE wm.workspace_id = $1 ORDER BY wm.joined_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def get_member_role(workspace_id: UUID, user_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT role FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    return row["role"] if row else None


async def is_member(workspace_id: UUID, user_id: UUID) -> bool:
    return await get_member_role(workspace_id, user_id) is not None


async def kick_member(workspace_id: UUID, target_user_id: UUID, kicker_id: UUID) -> bool:
    """Only owners can kick. Owners can't be kicked."""
    pool = get_pool()
    kicker_role = await get_member_role(workspace_id, kicker_id)
    target_role = await get_member_role(workspace_id, target_user_id)
    if not kicker_role or not target_role:
        return False
    if target_role == "owner":
        return False
    if kicker_role != "owner":
        return False
    result = await pool.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        target_user_id,
    )
    if result == "DELETE 1":
        await pool.execute(
            "DELETE FROM webhooks WHERE workspace_id = $1 AND user_id = $2",
            workspace_id,
            target_user_id,
        )
        return True
    return False


# Role-based authorization helpers (PR 7).
ROLES_CAN_READ = {"owner", "editor", "viewer"}
ROLES_CAN_WRITE = {"owner", "editor"}
ROLES_ADMIN = {"owner"}


async def can_read(workspace_id: UUID, user_id: UUID) -> bool:
    role = await get_member_role(workspace_id, user_id)
    return role in ROLES_CAN_READ


async def can_write(workspace_id: UUID, user_id: UUID) -> bool:
    role = await get_member_role(workspace_id, user_id)
    return role in ROLES_CAN_WRITE


async def is_owner(workspace_id: UUID, user_id: UUID) -> bool:
    role = await get_member_role(workspace_id, user_id)
    return role in ROLES_ADMIN


async def set_member_role(
    workspace_id: UUID,
    target_user_id: UUID,
    setter_id: UUID,
    role: str,
) -> bool:
    """Only owners can change roles. Owners cannot demote themselves
    (would lock the workspace if they're the only owner). Role must be
    one of owner/editor/viewer."""
    if role not in ("owner", "editor", "viewer"):
        return False
    if not await is_owner(workspace_id, setter_id):
        return False
    pool = get_pool()
    target_role = await get_member_role(workspace_id, target_user_id)
    if target_role is None:
        return False
    if target_role == "owner" and role != "owner":
        # Prevent demoting the last owner.
        owner_count = await pool.fetchval(
            "SELECT COUNT(*) FROM workspace_members " "WHERE workspace_id = $1 AND role = 'owner'",
            workspace_id,
        )
        if owner_count <= 1:
            return False
    await pool.execute(
        "UPDATE workspace_members SET role = $1 " "WHERE workspace_id = $2 AND user_id = $3",
        role,
        workspace_id,
        target_user_id,
    )
    return True
