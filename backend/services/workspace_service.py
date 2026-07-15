"""Workspaces: an org-owned scope with derived membership.

A workspace's knowledge base is the scope of a dedicated login-less users row
(`workspaces.scope_user_id`). Membership is a pure function of two inputs:
on-domain users (a *verified* email on `workspaces.domain`) are members by
definition — there is nothing to enroll, backfill, or revoke — and
`workspace_members` holds only explicit admin adds for off-domain people
(contractors). `users.email_verified` is the trust anchor for the domain rule:
an unverified `fake@customer.com` signup must never see the customer's KB.
The single SQL predicate is `permission_service.workspace_member_condition`.
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
    """Create a workspace and its login-less scope user. Verified users on the
    domain are members immediately — membership is derived, so there is no
    backfill step and signup order never matters.

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
        "       (SELECT count(*) FROM users u "
        "        WHERE u.email_verified AND lower(split_part(u.email, '@', 2)) = w.domain) "
        "       + (SELECT count(*) FROM workspace_members m WHERE m.workspace_id = w.id) "
        "       AS member_count "
        "FROM workspaces w ORDER BY w.created_at",
    )
    return [dict(row) for row in rows]


async def add_member(workspace_id: UUID, user_id: UUID) -> None:
    """Explicitly add an off-domain member. On-domain users are members by
    the domain rule and must never get a row here — the admin router rejects
    them, keeping this table off-domain-only."""
    pool = get_pool()
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id) VALUES ($1, $2) "
        "ON CONFLICT DO NOTHING",
        workspace_id,
        user_id,
    )


async def remove_member(workspace_id: UUID, user_id: UUID) -> bool:
    """Remove an explicit (off-domain) member. On-domain members have no row,
    so removal correctly reports not-found — their access rides on the domain
    rule and ends only when the account is deactivated."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    return result.endswith(" 1")


async def list_for_user(user_id: UUID) -> list[dict]:
    from . import permission_service

    membership = permission_service.workspace_member_condition("w", 1)
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT w.id, w.name, w.domain, w.scope_user_id FROM workspaces w "
        f"WHERE {membership} ORDER BY w.name",
        user_id,
    )
    return [dict(row) for row in rows]
