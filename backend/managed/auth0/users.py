"""Provision / rotate users from Auth0 identities."""

import re

import logging

from backend.auth import create_api_key
from backend.database import get_pool
from backend.services import workspace_service
from backend.services.email_service import send_welcome_email

logger = logging.getLogger(__name__)

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
    key_name: str = "Auth0 login",
) -> tuple[dict, str]:
    """Return (user_row, new_api_key). Mints a fresh key per exchange; prior keys stay valid.

    Multi-device sign-in must keep both devices working, so we don't touch
    prior keys here. Users clean up stale sessions from the settings page,
    and signing out now revokes the calling key server-side so keys don't
    silently accumulate.
    """
    pool = get_pool()

    row = await pool.fetchrow(
        "SELECT id, name, display_name, description, created_at, last_seen "
        "FROM users WHERE auth0_sub = $1",
        auth0_sub,
    )
    if row:
        if email:
            await pool.execute(
                "UPDATE users SET last_seen = now(), email = $2 WHERE id = $1",
                row["id"],
                email,
            )
        else:
            await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", row["id"])
        api_key = await create_api_key(row["id"], name=key_name)
        return dict(row), api_key

    base = _slugify_name((email or "").split("@")[0] or name or "user")
    username = await _unique_name(base)
    display_name = name or username

    row = await pool.fetchrow(
        "INSERT INTO users (name, display_name, auth0_sub, description, email) "
        "VALUES ($1, $2, $3, '', $4) "
        "RETURNING id, name, display_name, description, created_at, last_seen",
        username,
        display_name,
        auth0_sub,
        email,
    )
    user = dict(row)
    api_key = await create_api_key(user["id"], name=key_name)

    suffix = "'s Workspace"
    ws_name = f"{user['display_name'][: 128 - len(suffix)]}{suffix}"
    await workspace_service.create_workspace(
        name=ws_name,
        description="",
        creator_id=user["id"],
        is_public=False,
    )

    if email:
        try:
            first_name = (name or "").split()[0] if name else None
            send_welcome_email(email, first_name=first_name)
        except Exception:
            logger.exception("Failed to send welcome email to %s", email)

    return user, api_key
