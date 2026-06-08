"""Slack → slack_messages: one-time backfill + per-event ingest.

`index_slack` backfills recent history for the source's explicit channel
allowlist. Live updates arrive via the Events API webhook, which enqueues
`ingest_slack_message` per message. Each message is a row at `{channel}/{ts}`
(with native channel_id/channel_name/ts columns) so the agent can navigate by
channel and search across allowed channels.
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
        raise RuntimeError("Slack API returned ok=false")
    return payload


async def index_slack(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    allowed_channel_ids = set(source_service.slack_allowed_channel_ids(source))
    if not allowed_channel_ids:
        logger.info("slack source %s: no allowed channels configured", source_id)
        return None

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
            if channel_id not in allowed_channel_ids:
                continue
            channel_name = channel.get("name") or channel_id
            # A channel we can't read (not a member, archived, …) must not abort
            # the whole backfill — skip it and continue. conversations.history
            # returns most-recent-first, so this bootstraps recent messages.
            try:
                history = await _slack_get(
                    client,
                    CONVERSATIONS_HISTORY_URL,
                    {"channel": channel_id, "limit": MAX_MESSAGES_PER_CHANNEL},
                )
            except RuntimeError as e:
                logger.info(
                    "slack: skipping unreadable channel source=%s exception_type=%s",
                    source_id,
                    type(e).__name__,
                )
                continue
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


async def fetch_history(source: dict, since, until, limit: int = 500) -> dict:
    """On-demand: pull messages in [since, until] across allowed channels.
    Caches them (upsert) so they're searchable afterward, and returns refs."""
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    allowed_channel_ids = set(source_service.slack_allowed_channel_ids(source))
    if not allowed_channel_ids:
        return {
            "fetched": 0,
            "since": since.isoformat(),
            "until": until.isoformat() if until else None,
            "results": [],
        }

    token = await get_valid_token(owner_user_id, "slack")
    headers = {"Authorization": f"Bearer {token}"}
    oldest = f"{since.timestamp():.6f}"
    latest = f"{until.timestamp():.6f}" if until else None

    refs: list[str] = []
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        channels = (
            await _slack_get(
                client, CONVERSATIONS_LIST_URL, {"types": CHANNEL_TYPES, "limit": MAX_CHANNELS}
            )
        ).get("channels", [])
        for channel in channels:
            if len(refs) >= limit:
                break
            channel_id = channel["id"]
            if channel_id not in allowed_channel_ids:
                continue
            channel_name = channel.get("name") or channel_id
            params = {"channel": channel_id, "oldest": oldest, "limit": MAX_MESSAGES_PER_CHANNEL}
            if latest:
                params["latest"] = latest
            try:
                history = await _slack_get(client, CONVERSATIONS_HISTORY_URL, params)
            except RuntimeError as e:
                logger.info(
                    "slack history: skipping unreadable channel source=%s exception_type=%s",
                    source_id,
                    type(e).__name__,
                )
                continue
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
                refs.append(f"{channel_name}/{msg['ts']}")
                if len(refs) >= limit:
                    break

    return {
        "fetched": len(refs),
        "since": since.isoformat(),
        "until": until.isoformat() if until else None,
        "results": [{"ref": r} for r in refs[:25]],
    }


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
    """Upsert one Events-API message into matching Slack sources for this team.
    Each source is user-scoped and channel-scoped, so the same message lands
    once per owner who explicitly allowed that channel."""
    channel_id = event.get("channel", "")
    if (
        event.get("type") != "message"
        or event.get("subtype")
        or not event.get("ts")
        or not channel_id
    ):
        return 0
    rows = await get_pool().fetch(
        "SELECT id, workspace_id, settings FROM workspace_sources "
        "WHERE source_type = 'slack' AND external_ref = $1",
        team_id,
    )
    ingested = 0
    for row in rows:
        if channel_id not in source_service.slack_allowed_channel_ids(
            {"settings": row["settings"] or {}}
        ):
            continue
        await _upsert_message(
            source_id=row["id"],
            workspace_id=row["workspace_id"],
            channel_id=channel_id,
            channel_name=channel_id,
            ts=event["ts"],
            text=event.get("text") or "",
        )
        ingested += 1
    return ingested
