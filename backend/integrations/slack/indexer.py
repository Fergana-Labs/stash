"""Slack → slack_messages: one-time backfill + per-event ingest.

`index_slack` backfills recent history across the user's channels (also the
periodic safety re-sync). Live updates arrive via the Events API webhook, which
enqueues `ingest_slack_message` per message. Each message is a row at
`{channel}/{ts}` (with native channel_id/channel_name/ts columns) so the agent
can navigate by channel and search across them.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ...database import get_pool
from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

CONVERSATIONS_LIST_URL = "https://slack.com/api/conversations.list"
CONVERSATIONS_HISTORY_URL = "https://slack.com/api/conversations.history"

CHANNEL_TYPES = "public_channel,private_channel,im,mpim"
MAX_CHANNELS = 100
MAX_MESSAGES_PER_CHANNEL = 200


async def _slack_get(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Slack API error ({url}): {payload.get('error')}")
    return payload


async def index_slack(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])

    token = await get_valid_token(owner_user_id, "slack")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        channels_payload = await _slack_get(
            client,
            CONVERSATIONS_LIST_URL,
            {"types": CHANNEL_TYPES, "limit": MAX_CHANNELS},
        )
        for channel in channels_payload.get("channels", []):
            channel_id = channel["id"]
            channel_name = channel.get("name") or channel_id
            history = await _slack_get(
                client,
                CONVERSATIONS_HISTORY_URL,
                {"channel": channel_id, "limit": MAX_MESSAGES_PER_CHANNEL},
            )
            for msg in history.get("messages", []):
                if msg.get("type") != "message" or not msg.get("ts"):
                    continue
                await _upsert_message(
                    source_id=source_id,
                    workspace_id=workspace_id,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    ts=msg["ts"],
                    text=msg.get("text") or "",
                )

    logger.info("slack source %s: backfill complete", source_id)
    return None


async def _upsert_message(
    *,
    source_id: UUID,
    workspace_id: UUID,
    channel_id: str,
    channel_name: str,
    ts: str,
    text: str,
) -> None:
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        workspace_id=workspace_id,
        path=f"{channel_name}/{ts}",
        name=f"#{channel_name}",
        kind="message",
        content=text,
        external_ref=f"{channel_id}:{ts}",
        extra={"channel_id": channel_id, "channel_name": channel_name, "ts": ts},
    )


async def ingest_slack_message(team_id: str, event: dict) -> int:
    """Upsert one Events-API message into every Slack source for this team.
    Each source is user-scoped, so the same message lands once per owner who
    connected the team — and stays visible only to them."""
    if event.get("type") != "message" or event.get("subtype") or not event.get("ts"):
        return 0
    rows = await get_pool().fetch(
        "SELECT id, workspace_id FROM workspace_sources "
        "WHERE source_type = 'slack' AND external_ref = $1",
        team_id,
    )
    for row in rows:
        await _upsert_message(
            source_id=row["id"],
            workspace_id=row["workspace_id"],
            channel_id=event.get("channel", ""),
            channel_name=event.get("channel", ""),
            ts=event["ts"],
            text=event.get("text") or "",
        )
    return len(rows)
