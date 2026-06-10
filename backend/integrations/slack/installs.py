"""Slack agent (talk-to-Stash bot) — team bot-token storage.

One row per Slack team in `slack_bot_installs`. The bot token lets the agent
post replies (chat.postMessage) and resolve user emails (users.info). Tokens
are encrypted at rest with the same Fernet key as user_integrations.

This module is part of the removable Slack-agent feature: delete the
slack/ agent files + the slack_bot_installs table to drop it entirely.
"""

from __future__ import annotations

from ...database import get_pool
from ..storage import _decrypt, _encrypt


async def store_install(
    *,
    team_id: str,
    bot_token: str,
    bot_user_id: str | None = None,
    installed_by_user_id=None,
) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO slack_bot_installs (
            team_id, bot_token_encrypted, bot_user_id, installed_by_user_id, updated_at
        )
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (team_id) DO UPDATE SET
            bot_token_encrypted = EXCLUDED.bot_token_encrypted,
            bot_user_id = EXCLUDED.bot_user_id,
            installed_by_user_id = COALESCE(EXCLUDED.installed_by_user_id, slack_bot_installs.installed_by_user_id),
            updated_at = now()
        """,
        team_id,
        _encrypt(bot_token),
        bot_user_id,
        installed_by_user_id,
    )


async def get_install(team_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT team_id, bot_token_encrypted, bot_user_id FROM slack_bot_installs WHERE team_id = $1",
        team_id,
    )
    if row is None:
        return None
    return {
        "team_id": row["team_id"],
        "bot_token": _decrypt(row["bot_token_encrypted"]),
        "bot_user_id": row["bot_user_id"],
    }
