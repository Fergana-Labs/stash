"""Telegram user ↔ Stash account linking via a short-lived connect code.

The user mints a code in settings and opens t.me/<bot>?start=<code>; the bot's
/start handler resolves the code and binds their Telegram id. No email fallback
— Telegram exposes no verified email, so the deep-link code is the only trusted
identity path."""

from __future__ import annotations

import secrets
from uuid import UUID

from ...database import get_pool


async def mint_connect_code(user_id: UUID) -> str:
    code = secrets.token_urlsafe(9)
    await get_pool().execute(
        "INSERT INTO telegram_connect_codes (code, user_id) VALUES ($1, $2)", code, user_id
    )
    return code


async def redeem_connect_code(code: str, telegram_user_id: str) -> UUID | None:
    """Bind a Telegram id to the account that minted `code`. Codes are
    single-use and expire after 15 minutes."""
    pool = get_pool()
    row = await pool.fetchrow(
        "DELETE FROM telegram_connect_codes "
        "WHERE code = $1 AND created_at > now() - interval '15 minutes' "
        "RETURNING user_id",
        code,
    )
    if row is None:
        return None
    user_id = row["user_id"]
    await pool.execute(
        "INSERT INTO telegram_user_links (telegram_user_id, user_id) VALUES ($1, $2) "
        "ON CONFLICT (telegram_user_id) DO UPDATE SET user_id = EXCLUDED.user_id",
        telegram_user_id,
        user_id,
    )
    return user_id


async def get_linked_user_id(telegram_user_id: str) -> UUID | None:
    row = await get_pool().fetchrow(
        "SELECT user_id FROM telegram_user_links WHERE telegram_user_id = $1", telegram_user_id
    )
    return row["user_id"] if row else None
