"""Workspace service: CRUD, membership, invite codes."""

import secrets
from uuid import UUID

from ..database import get_pool


async def create_workspace(
    name: str,
    description: str,
    creator_id: UUID,
    is_public: bool = False,
) -> dict:
    """Create a workspace with the creator as owner."""
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
        "INSERT INTO workspaces (name, description, creator_id, invite_code, is_public) "
        "VALUES ($1, $2, $3, $4, $5) "
        "RETURNING id, name, description, creator_id, invite_code, is_public, "
        "created_at, updated_at, summary, tags, category, featured, "
        "cover_image_url, fork_count, forked_from_workspace_id",
        name,
        description,
        creator_id,
        invite_code,
        is_public,
    )
    ws = dict(row)
    # Auto-add creator as owner
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
        ws["id"],
        creator_id,
    )
    ws["member_count"] = 1
    return ws


async def get_workspace(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT w.id, w.name, w.description, w.creator_id, w.invite_code, w.is_public, "
        "w.created_at, w.updated_at, w.summary, w.tags, w.category, w.featured, "
        "w.cover_image_url, w.fork_count, w.forked_from_workspace_id, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w WHERE w.id = $1",
        workspace_id,
    )
    return dict(row) if row else None


async def list_public_workspaces() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT w.id, w.name, w.description, w.creator_id, w.invite_code, w.is_public, "
        "w.created_at, w.updated_at, w.summary, w.tags, w.category, w.featured, "
        "w.cover_image_url, w.fork_count, w.forked_from_workspace_id, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w WHERE w.is_public = true ORDER BY w.created_at DESC",
    )
    return [dict(r) for r in rows]


async def list_user_workspaces(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT w.id, w.name, w.description, w.creator_id, w.invite_code, w.is_public, "
        "w.created_at, w.updated_at, w.summary, w.tags, w.category, w.featured, "
        "w.cover_image_url, w.fork_count, w.forked_from_workspace_id, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w "
        "JOIN workspace_members wm ON wm.workspace_id = w.id "
        "WHERE wm.user_id = $1 ORDER BY w.created_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def update_workspace(
    workspace_id: UUID,
    name: str | None = None,
    description: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
    cover_image_url: str | None = None,
) -> dict | None:
    pool = get_pool()
    sets, args, idx = [], [], 1
    for col, val in (
        ("name", name),
        ("description", description),
        ("summary", summary),
        ("tags", tags),
        ("category", category),
        ("cover_image_url", cover_image_url),
    ):
        if val is not None:
            sets.append(f"{col} = ${idx}")
            args.append(val)
            idx += 1
    if not sets:
        return await get_workspace(workspace_id)
    sets.append("updated_at = now()")
    args.append(workspace_id)
    row = await pool.fetchrow(
        f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ${idx} "
        "RETURNING id, name, description, creator_id, invite_code, is_public, "
        "created_at, updated_at, summary, tags, category, featured, "
        "cover_image_url, fork_count, forked_from_workspace_id, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = id) AS member_count",
        *args,
    )
    return dict(row) if row else None


async def delete_workspace(workspace_id: UUID, user_id: UUID) -> bool:
    """Delete workspace. Only owner can delete."""
    pool = get_pool()
    role = await get_member_role(workspace_id, user_id)
    if role != "owner":
        return False
    result = await pool.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)
    return result == "DELETE 1"


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
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'member')",
        workspace_id,
        user_id,
    )
    return await get_workspace(workspace_id)


async def rotate_invite_code(workspace_id: UUID, user_id: UUID) -> dict | None:
    """Generate a new invite_code, invalidating the previous one. Owner/admin only."""
    role = await get_member_role(workspace_id, user_id)
    if role not in ("owner", "admin"):
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
    row = await pool.fetchrow(
        "UPDATE workspaces SET invite_code = $1, updated_at = now() WHERE id = $2 "
        "RETURNING id, name, description, creator_id, invite_code, is_public, "
        "created_at, updated_at, summary, tags, category, featured, "
        "cover_image_url, fork_count, forked_from_workspace_id, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = id) AS member_count",
        new_code,
        workspace_id,
    )
    return dict(row) if row else None


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
    pool = get_pool()
    kicker_role = await get_member_role(workspace_id, kicker_id)
    target_role = await get_member_role(workspace_id, target_user_id)
    if not kicker_role or not target_role:
        return False
    if target_role == "owner":
        return False
    if kicker_role == "member":
        return False
    if kicker_role == "admin" and target_role == "admin":
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
