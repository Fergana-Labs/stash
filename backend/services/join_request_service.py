"""Workspace join requests: create, list, approve, deny."""

from uuid import UUID

from ..database import get_pool
from . import workspace_service


async def get_workspace_public_info(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT w.id, w.name, "
        "(SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count "
        "FROM workspaces w WHERE w.id = $1",
        workspace_id,
    )
    return dict(row) if row else None


async def create_request(workspace_id: UUID, user_id: UUID) -> dict:
    pool = get_pool()

    already_member = await workspace_service.is_member(workspace_id, user_id)
    if already_member:
        raise ValueError("already_member")

    row = await pool.fetchrow(
        "INSERT INTO workspace_join_requests (workspace_id, user_id) "
        "VALUES ($1, $2) "
        "ON CONFLICT (workspace_id, user_id) WHERE status = 'pending' DO NOTHING "
        "RETURNING id, workspace_id, user_id, status, created_at, resolved_at, resolved_by",
        workspace_id,
        user_id,
    )
    if not row:
        existing = await pool.fetchrow(
            "SELECT id, workspace_id, user_id, status, created_at, resolved_at, resolved_by "
            "FROM workspace_join_requests "
            "WHERE workspace_id = $1 AND user_id = $2 AND status = 'pending'",
            workspace_id,
            user_id,
        )
        if existing:
            return dict(existing)
        raise ValueError("request_failed")
    return dict(row)


async def list_pending(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT jr.id, jr.workspace_id, jr.user_id, jr.status, jr.created_at, "
        "u.name AS user_name, u.display_name AS user_display_name "
        "FROM workspace_join_requests jr "
        "JOIN users u ON u.id = jr.user_id "
        "WHERE jr.workspace_id = $1 AND jr.status = 'pending' "
        "ORDER BY jr.created_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def approve_request(request_id: UUID, approver_id: UUID) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE workspace_join_requests "
                "SET status = 'approved', resolved_at = now(), resolved_by = $2 "
                "WHERE id = $1 AND status = 'pending' "
                "RETURNING id, workspace_id, user_id, status, created_at, resolved_at, resolved_by",
                request_id,
                approver_id,
            )
            if not row:
                return None
            await conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES ($1, $2, 'member') "
                "ON CONFLICT (workspace_id, user_id) DO NOTHING",
                row["workspace_id"],
                row["user_id"],
            )
    return dict(row)


async def deny_request(request_id: UUID, denier_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE workspace_join_requests "
        "SET status = 'denied', resolved_at = now(), resolved_by = $2 "
        "WHERE id = $1 AND status = 'pending' "
        "RETURNING id, workspace_id, user_id, status, created_at, resolved_at, resolved_by",
        request_id,
        denier_id,
    )
    return dict(row) if row else None


async def get_user_request_status(workspace_id: UUID, user_id: UUID) -> dict | None:
    """Get the most recent join request for a user in a workspace."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, user_id, status, created_at, resolved_at, resolved_by "
        "FROM workspace_join_requests "
        "WHERE workspace_id = $1 AND user_id = $2 "
        "ORDER BY created_at DESC LIMIT 1",
        workspace_id,
        user_id,
    )
    return dict(row) if row else None


async def get_admin_emails(workspace_id: UUID) -> list[str]:
    """Get email addresses of workspace owners and admins."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT u.email FROM users u "
        "JOIN workspace_members wm ON wm.user_id = u.id "
        "WHERE wm.workspace_id = $1 AND wm.role IN ('owner', 'admin') "
        "AND u.email IS NOT NULL",
        workspace_id,
    )
    return [r["email"] for r in rows]


async def get_user_email(user_id: UUID) -> str | None:
    pool = get_pool()
    return await pool.fetchval("SELECT email FROM users WHERE id = $1", user_id)
