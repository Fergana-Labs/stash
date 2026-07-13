"""Workspaces: an org-owned scope with stored membership.

A workspace's knowledge base is the scope of a dedicated login-less users row
(`workspaces.scope_user_id`). `workspace_members` is the single source of
truth for membership; the permission predicate grants members read+write on
the workspace scope's content. Rows arrive two ways: domain auto-enroll (a
user whose *verified* email domain matches `workspaces.domain`) and explicit
admin adds (any user, any domain).
"""

import re
from uuid import UUID

from ..database import get_pool

_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[1].lower()


async def _unique_scope_user_name(domain: str) -> str:
    pool = get_pool()
    base = ("ws-" + _NAME_CHARS.sub("-", domain))[:60]
    candidate = base
    suffix = 2
    while await pool.fetchval("SELECT 1 FROM users WHERE name = $1", candidate):
        candidate = f"{base}-{suffix}"[:64]
        suffix += 1
    return candidate


async def create_workspace(name: str, domain: str) -> dict:
    """Create a workspace: its login-less scope user, the workspaces row, and
    membership backfill for existing verified users on the domain.

    The scope user has no password and no auth0_sub, so nobody can log in as
    it — it is reached only through API keys minted by the admin endpoints.
    """
    from . import user_scope_service

    pool = get_pool()
    scope_user = await pool.fetchrow(
        "INSERT INTO users (name, display_name, description, plan) "
        "VALUES ($1, $2, 'Workspace scope user', 'enterprise') RETURNING id",
        await _unique_scope_user_name(domain),
        name,
    )
    workspace = await pool.fetchrow(
        "INSERT INTO workspaces (name, domain, scope_user_id) VALUES ($1, $2, $3) "
        "RETURNING id, name, domain, scope_user_id, created_at",
        name,
        domain,
        scope_user["id"],
    )
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id) "
        "SELECT $1, u.id FROM users u "
        "WHERE u.email_verified AND lower(split_part(u.email, '@', 2)) = $2 "
        "ON CONFLICT DO NOTHING",
        workspace["id"],
        domain,
    )
    await user_scope_service.seed_user_scope(scope_user["id"])
    return dict(workspace)


async def get_workspace(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, domain, scope_user_id, created_at FROM workspaces WHERE id = $1",
        workspace_id,
    )
    return dict(row) if row else None


async def list_workspaces() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT w.id, w.name, w.domain, w.scope_user_id, w.created_at, "
        "       count(m.user_id) AS member_count "
        "FROM workspaces w LEFT JOIN workspace_members m ON m.workspace_id = w.id "
        "GROUP BY w.id ORDER BY w.created_at",
    )
    return [dict(row) for row in rows]


async def add_member(workspace_id: UUID, user_id: UUID) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id) VALUES ($1, $2) "
        "ON CONFLICT DO NOTHING",
        workspace_id,
        user_id,
    )


async def remove_member(workspace_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    return result.endswith(" 1")


async def enroll_by_domain(user_id: UUID, email: str) -> None:
    """Enroll a user into the workspace matching their email domain, if any.

    Callers must only pass verified emails — verification is the trust anchor
    that keeps `fake@customer.com` signups out of the customer's KB.
    """
    pool = get_pool()
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id) "
        "SELECT w.id, $1 FROM workspaces w WHERE w.domain = $2 "
        "ON CONFLICT DO NOTHING",
        user_id,
        email_domain(email),
    )


async def list_for_user(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT w.id, w.name, w.domain, w.scope_user_id FROM workspaces w "
        "JOIN workspace_members m ON m.workspace_id = w.id "
        "WHERE m.user_id = $1 ORDER BY w.name",
        user_id,
    )
    return [dict(row) for row in rows]
