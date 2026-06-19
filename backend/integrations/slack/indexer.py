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
    await source_service.purge_disallowed_copied_documents(source)
    if not allowed_channel_ids:
        # Fail loudly so the sync records a sync_error instead of reporting a
        # successful sync that ingested nothing.
        raise RuntimeError("no allowed channels configured")

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
    existing = await get_pool().fetchrow(
        "SELECT path, name FROM slack_messages "
        "WHERE source_id = $1 AND channel_id = $2 AND ts = $3",
        source_id,
        channel_id,
        ts,
    )
    path = existing["path"] if existing else f"{channel_name}/{ts}"
    name = existing["name"] if existing else f"#{channel_name}"
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        workspace_id=workspace_id,
        path=path,
        name=name,
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
    if event.get("type") != "message" or not channel_id:
        return 0

    subtype = event.get("subtype")
    if subtype == "message_deleted":
        deleted_ts = event.get("deleted_ts")
        if not deleted_ts:
            return 0
        result = await get_pool().execute(
            "DELETE FROM slack_messages d USING workspace_sources s "
            "WHERE d.source_id = s.id "
            "AND s.source_type = 'slack' "
            "AND s.external_ref = $1 "
            "AND d.channel_id = $2 "
            "AND d.ts = $3",
            team_id,
            channel_id,
            deleted_ts,
        )
        return int(result.rsplit(" ", 1)[-1])

    if subtype == "message_changed":
        message = event.get("message") or {}
        if message.get("type") != "message" or not message.get("ts"):
            return 0
        # Edits of subtyped messages (bot_message, thread_broadcast, ...) carry
        # the subtype inside the nested message; drop them like fresh ones.
        if message.get("subtype"):
            return 0
        event = {**message, "channel": channel_id, "type": "message"}
    elif subtype:
        return 0

    if not event.get("ts"):
        return 0

    rows = await get_pool().fetch(
        "SELECT id, workspace_id, settings FROM workspace_sources ws "
        "WHERE ws.source_type = 'slack' AND ws.external_ref = $1 "
        "AND ws.sync_enabled "
        "AND EXISTS ("
        "  SELECT 1 FROM workspaces w "
        "  WHERE w.id = ws.workspace_id AND w.creator_id = ws.owner_user_id"
        ")",
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
