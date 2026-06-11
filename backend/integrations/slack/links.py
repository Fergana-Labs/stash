"""Slack agent (talk-to-Stash bot) — Slack user ↔ Stash user linking.

The robust identity map: when a Stash user connects Slack, we capture their
Slack user_id (from auth.test on the user token) and store
(team_id, slack_user_id) → stash_user_id. Inbound mentions then resolve by
that id, no email matching required. Part of the removable Slack-agent feature.
"""

from __future__ import annotations

from uuid import UUID

from ...database import get_pool
from .provider import SlackIntegration


async def store_link(team_id: str, slack_user_id: str, user_id: UUID) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO slack_user_links (team_id, slack_user_id, user_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (team_id, slack_user_id) DO UPDATE SET user_id = EXCLUDED.user_id
        """,
        team_id,
        slack_user_id,
        user_id,
    )


async def get_linked_user_id(team_id: str, slack_user_id: str) -> UUID | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT user_id FROM slack_user_links WHERE team_id = $1 AND slack_user_id = $2",
        team_id,
        slack_user_id,
    )
    return row["user_id"] if row else None


async def capture_from_user_token(user_id: UUID, user_token: str) -> None:
    """Called at connect time: resolve the connecting user's Slack identity from
    their user token (auth.test → team_id, user_id) and persist the link."""
    info = await SlackIntegration().team_info(user_token)
    team_id = info.get("team_id")
    slack_user_id = info.get("user_id")
    if team_id and slack_user_id:
        await store_link(team_id, slack_user_id, user_id)
