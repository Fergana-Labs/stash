"""Provision / rotate users from Auth0 identities."""

import re

from backend.auth import generate_api_key, hash_api_key
from backend.database import get_pool
from backend.services import workspace_service

_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


def _slugify_name(raw: str) -> str:
    slug = _NAME_CHARS.sub("", raw)[:60] or "user"
    return slug


async def _unique_name(base: str) -> str:
    pool = get_pool()
    candidate = base
    suffix = 2
    while await pool.fetchval("SELECT 1 FROM users WHERE name = $1", candidate):
        candidate = f"{base}_{suffix}"[:64]
        suffix += 1
    return candidate


async def get_or_create_user_from_auth0(
    auth0_sub: str,
    email: str | None,
    name: str | None,
) -> tuple[dict, str]:
    """Return (user_row, new_api_key). Rotates api_key on every login."""
    pool = get_pool()
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)

    row = await pool.fetchrow(
        "SELECT id, name, display_name, description, created_at, last_seen "
        "FROM users WHERE auth0_sub = $1",
        auth0_sub,
    )
    if row:
        await pool.execute(
            "UPDATE users SET api_key_hash = $1, last_seen = now() WHERE id = $2",
            key_hash,
            row["id"],
        )
        return dict(row), api_key

    base = _slugify_name((email or "").split("@")[0] or name or "user")
    username = await _unique_name(base)
    display_name = name or username

    row = await pool.fetchrow(
        "INSERT INTO users (name, display_name, api_key_hash, auth0_sub, description) "
        "VALUES ($1, $2, $3, $4, '') "
        "RETURNING id, name, display_name, description, created_at, last_seen",
        username,
        display_name,
        key_hash,
        auth0_sub,
    )
    user = dict(row)

    suffix = "'s Workspace"
    ws_name = f"{user['display_name'][: 128 - len(suffix)]}{suffix}"
    await workspace_service.create_workspace(
        name=ws_name,
        description="",
        creator_id=user["id"],
        is_public=False,
    )
    return user, api_key
