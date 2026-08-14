"""Stashes: extra isolated scopes owned by one user.

A stash's content lives under a dedicated login-less `users` row
(`stashes.scope_user_id`) — the same recipe workspaces use — so pages, files,
sessions, memory, sources, and integration tokens are hermetically per-stash
with no changes to the content tables. Ownership IS membership: the human in
`owner_user_id` has full owner powers in the scope (unlike workspace members,
who are deliberately second-class). A user's first stash is their own account
and has no `stashes` row.

Billing note: scope users are created on the 'free' plan and mean nothing for
billing — plan checks and connection limits apply to the human actor.
"""

import re
from uuid import UUID

from ..database import get_pool

# Hard cap per user. Each stash seeds its own curator and memory, so this is
# a cost guardrail, not a technical limit.
MAX_STASHES = 20

_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


async def _unique_scope_user_name(stash_name: str) -> str:
    pool = get_pool()
    base = ("stash-" + _NAME_CHARS.sub("-", stash_name.lower()))[:60]
    candidate = base
    suffix = 2
    while await pool.fetchval("SELECT 1 FROM users WHERE name = $1", candidate):
        candidate = f"{base}-{suffix}"[:64]
        suffix += 1
    return candidate


async def create_stash(owner_user_id: UUID, name: str) -> dict:
    """Create a stash and its login-less scope user, seeded like any new
    account (memory folder, curator). The scope user has no password and no
    auth0_sub, so nobody can log in as it — it is reached via the scope
    header or API keys minted on it."""
    from . import user_scope_service

    pool = get_pool()
    count = await pool.fetchval(
        "SELECT count(*) FROM stashes WHERE owner_user_id = $1", owner_user_id
    )
    if count >= MAX_STASHES:
        raise ValueError(f"stash limit reached ({MAX_STASHES})")

    scope_user = await pool.fetchrow(
        "INSERT INTO users (name, display_name, description) "
        "VALUES ($1, $2, 'Stash scope user') RETURNING id",
        await _unique_scope_user_name(name),
        name,
    )
    stash = await pool.fetchrow(
        "INSERT INTO stashes (name, owner_user_id, scope_user_id) VALUES ($1, $2, $3) "
        "RETURNING id, name, owner_user_id, scope_user_id, created_at",
        name,
        owner_user_id,
        scope_user["id"],
    )
    await user_scope_service.seed_user_scope(scope_user["id"])
    return dict(stash)


async def list_for_user(owner_user_id: UUID) -> list[dict]:
    """Owned stashes with the activity facts the channel-style sidebar shows:
    how much lives in each, and when anything last changed."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT s.id, s.name, s.owner_user_id, s.scope_user_id, s.created_at,
               (SELECT count(*) FROM pages p
                WHERE p.owner_user_id = s.scope_user_id AND p.deleted_at IS NULL)
               + (SELECT count(*) FROM files f
                  WHERE f.owner_user_id = s.scope_user_id AND f.deleted_at IS NULL)
               AS item_count,
               GREATEST(
                   (SELECT max(p.updated_at) FROM pages p
                    WHERE p.owner_user_id = s.scope_user_id AND p.deleted_at IS NULL),
                   (SELECT max(se.started_at) FROM sessions se
                    WHERE se.owner_user_id = s.scope_user_id AND se.deleted_at IS NULL)
               ) AS last_activity_at
        FROM stashes s WHERE s.owner_user_id = $1 ORDER BY s.created_at
        """,
        owner_user_id,
    )
    return [dict(row) for row in rows]


async def rename_stash(stash_id: UUID, owner_user_id: UUID, name: str) -> dict | None:
    """Rename a stash you own. The scope user's display name follows so agent
    surfaces (share dialogs, session attribution) show the new name too."""
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE stashes SET name = $3 WHERE id = $1 AND owner_user_id = $2 "
        "RETURNING id, name, owner_user_id, scope_user_id, created_at",
        stash_id,
        owner_user_id,
        name,
    )
    if row is None:
        return None
    await pool.execute(
        "UPDATE users SET display_name = $2 WHERE id = $1", row["scope_user_id"], name
    )
    return dict(row)


async def get_owned_stash(stash_id: UUID, owner_user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, owner_user_id, scope_user_id, created_at "
        "FROM stashes WHERE id = $1 AND owner_user_id = $2",
        stash_id,
        owner_user_id,
    )
    return dict(row) if row else None
