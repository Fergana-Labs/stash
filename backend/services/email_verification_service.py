"""Verify a user's email address with a single-use emailed link.

`users.email_verified` gates derived workspace membership. OAuth sign-ins
verify implicitly (the provider vouches for the address); this service is
the path for everyone else — password signups on either auth stack. One
live token per user; requesting a new one replaces the old.
"""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..database import get_pool
from . import email_service

TOKEN_TTL = timedelta(days=7)


async def start(user_id: UUID, email: str) -> None:
    """Issue the user's verification token and email them the link."""
    token = secrets.token_urlsafe(32)
    pool = get_pool()
    await pool.execute(
        "INSERT INTO email_verifications (user_id, token, email, expires_at) "
        "VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (user_id) DO UPDATE SET token = $2, email = $3, expires_at = $4",
        user_id,
        token,
        email,
        datetime.now(UTC) + TOKEN_TTL,
    )
    email_service.send_verification_email(email, token)


async def confirm(token: str) -> bool:
    """Consume a token. True when it verified the user's current email;
    False for unknown, expired, or stale (email since changed) tokens."""
    pool = get_pool()
    row = await pool.fetchrow(
        "DELETE FROM email_verifications WHERE token = $1 AND expires_at > now() "
        "RETURNING user_id, email",
        token,
    )
    if not row:
        return False
    result = await pool.execute(
        "UPDATE users SET email_verified = true WHERE id = $1 AND email = $2",
        row["user_id"],
        row["email"],
    )
    return result.endswith("1")
