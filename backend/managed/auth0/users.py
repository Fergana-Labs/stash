"""Provision / rotate users from Auth0 identities."""

import logging
import re

from backend.database import get_pool
from backend.services import share_service, workspace_service
from backend.services.email_service import send_welcome_email

logger = logging.getLogger(__name__)

_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")
_NEW_USER_WINDOW_SQL = "2 minutes"


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


async def get_or_create_user_row_from_auth0(
    auth0_sub: str,
    email: str | None,
    name: str | None,
):
    """Return (user_row, created) for an Auth0 identity.

    `created` is True when this exchange inserted the user, or when the user
    was inserted moments ago and the signup callback exchanged twice. The
    frontend uses it to route first-time sign-ins into onboarding.
    """
    pool = get_pool()

    row = await pool.fetchrow(
        "SELECT id, name, display_name, description, created_at, last_seen, "
        f"created_at >= now() - interval '{_NEW_USER_WINDOW_SQL}' AS is_new_user "
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
            # An invite may have been addressed to this email after the account
            # existed (e.g. before its email was recorded) — convert on login.
            await share_service.convert_pending_invites(row["id"], email)
        else:
            await pool.execute("UPDATE users SET last_seen = now() WHERE id = $1", row["id"])
        user = dict(row)
        is_new_user = bool(user.pop("is_new_user"))
        return user, is_new_user

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

    # Named "Stash" — we don't surface "workspace" terminology in the product.
    await workspace_service.create_workspace(
        name="Stash",
        description="",
        creator_id=user["id"],
    )

    await share_service.convert_pending_invites(user["id"], email)

    if email:
        try:
            first_name = (name or "").split()[0] if name else None
            send_welcome_email(email, first_name=first_name)
        except Exception as exc:
            logger.warning("welcome email failed exception_type=%s", type(exc).__name__)

    return user, True
