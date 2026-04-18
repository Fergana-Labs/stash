"""Workspace invite tokens: mint, list, revoke, redeem.

Tokens are stored as sha256 hashes (raw token returned only at mint time),
TTL-bounded, and usage-counted. This is the magic-link path — distinct from
the forever-secret workspaces.invite_code used by `stash workspaces join`.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..auth import create_api_key
from ..database import get_pool
from . import workspace_service

TOKEN_PREFIX = "stash_inv_"


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


async def create_token(
    workspace_id: UUID,
    creator_id: UUID,
    max_uses: int = 1,
    ttl_days: int = 7,
) -> tuple[dict, str]:
    """Mint a new invite token. Returns (row, raw_token). Raw is only seen once."""
    pool = get_pool()
    raw = _generate_token()
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
    row = await pool.fetchrow(
        "INSERT INTO workspace_invite_tokens "
        "  (workspace_id, token_hash, max_uses, expires_at, created_by) "
        "VALUES ($1, $2, $3, $4, $5) "
        "RETURNING id, workspace_id, max_uses, uses_count, expires_at, created_at, revoked_at",
        workspace_id,
        _hash_token(raw),
        max_uses,
        expires_at,
        creator_id,
    )
    return dict(row), raw


async def list_tokens(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, max_uses, uses_count, expires_at, created_at, revoked_at "
        "FROM workspace_invite_tokens "
        "WHERE workspace_id = $1 "
        "ORDER BY created_at DESC",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def revoke_token(token_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE workspace_invite_tokens SET revoked_at = now() "
        "WHERE id = $1 AND workspace_id = $2 AND revoked_at IS NULL",
        token_id,
        workspace_id,
    )
    return result.endswith(" 1")


async def _lookup_valid_token(raw: str) -> dict | None:
    """Return the token row if it's usable, else None."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, max_uses, uses_count, expires_at, revoked_at "
        "FROM workspace_invite_tokens "
        "WHERE token_hash = $1",
        _hash_token(raw),
    )
    if not row:
        return None
    if row["revoked_at"] is not None:
        return None
    if row["uses_count"] >= row["max_uses"]:
        return None
    if row["expires_at"] <= datetime.now(UTC):
        return None
    return dict(row)


async def _pick_unique_username(base: str) -> str:
    """Find a unique `users.name` by suffixing -2, -3, ... on collision."""
    pool = get_pool()
    # Users.name is [a-zA-Z0-9_-]+, 1-64 chars. Sanitize the caller's display name.
    import re

    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", base).strip("-") or "teammate"
    cleaned = cleaned[:60]  # leave room for a suffix
    candidate = cleaned
    for i in range(2, 1000):
        exists = await pool.fetchval("SELECT 1 FROM users WHERE name = $1", candidate)
        if not exists:
            return candidate
        candidate = f"{cleaned}-{i}"
    # Fallback: append random suffix
    return f"{cleaned}-{secrets.token_hex(3)}"


async def redeem_as_new_user(raw_token: str, display_name: str) -> dict | None:
    """Unauthenticated redeem: create a user, join workspace, return API key.

    Returns None if the token is invalid/expired/exhausted/revoked.
    """
    token_row = await _lookup_valid_token(raw_token)
    if not token_row:
        return None

    pool = get_pool()
    username = await _pick_unique_username(display_name)

    async with pool.acquire() as conn:
        async with conn.transaction():
            user_row = await conn.fetchrow(
                "INSERT INTO users (name, display_name, description) "
                "VALUES ($1, $2, '') "
                "RETURNING id, name, display_name",
                username,
                display_name[:128],
            )
            # Mark token as consumed first — if the join/member insert somehow fails
            # we don't want the token to stay usable.
            consumed = await conn.execute(
                "UPDATE workspace_invite_tokens SET uses_count = uses_count + 1 "
                "WHERE id = $1 AND uses_count < max_uses "
                "  AND revoked_at IS NULL AND expires_at > now()",
                token_row["id"],
            )
            if not consumed.endswith(" 1"):
                raise RuntimeError("invite token was consumed concurrently")
            await conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES ($1, $2, 'member')",
                token_row["workspace_id"],
                user_row["id"],
            )
    api_key = await create_api_key(user_row["id"], name="invite redeem")

    ws = await workspace_service.get_workspace(token_row["workspace_id"])
    return {
        "api_key": api_key,
        "user_id": user_row["id"],
        "username": user_row["name"],
        "display_name": user_row["display_name"],
        "workspace_id": ws["id"],
        "workspace_name": ws["name"],
    }


async def redeem_as_existing_user(raw_token: str, user_id: UUID) -> dict | None:
    """Authenticated redeem: join the existing user to the workspace.

    Returns the workspace dict, or None if the token is invalid/exhausted.
    If the user is already a member, we still consume a use but return success.
    """
    token_row = await _lookup_valid_token(raw_token)
    if not token_row:
        return None

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            consumed = await conn.execute(
                "UPDATE workspace_invite_tokens SET uses_count = uses_count + 1 "
                "WHERE id = $1 AND uses_count < max_uses "
                "  AND revoked_at IS NULL AND expires_at > now()",
                token_row["id"],
            )
            if not consumed.endswith(" 1"):
                raise RuntimeError("invite token was consumed concurrently")
            # Idempotent membership insert.
            await conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES ($1, $2, 'member') "
                "ON CONFLICT (workspace_id, user_id) DO NOTHING",
                token_row["workspace_id"],
                user_id,
            )

    return await workspace_service.get_workspace(token_row["workspace_id"])
