"""Slack → slack_messages: one-time backfill + per-event ingest.

`index_slack` backfills recent history for the source's explicit channel
allowlist, including thread replies (conversations.history omits them, so each
threaded parent gets a conversations.replies fetch). Live updates arrive via
the Events API webhook, which enqueues `ingest_slack_message` per message. Each message is a row at `{channel}/{ts}`
(with native channel_id/channel_name/ts and author columns); the *document
projection* over these rows is one transcript per channel per UTC day (see
source_service.list_documents/read_document), so agents read coherent,
attributed conversations instead of one-line files.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import httpx

from ...database import get_pool
from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

CONVERSATIONS_LIST_URL = "https://slack.com/api/conversations.list"
CONVERSATIONS_HISTORY_URL = "https://slack.com/api/conversations.history"
CONVERSATIONS_REPLIES_URL = "https://slack.com/api/conversations.replies"
USERS_INFO_URL = "https://slack.com/api/users.info"

CHANNEL_TYPES = "public_channel,private_channel,im,mpim"
MAX_CHANNELS = 100
MAX_MESSAGES_PER_CHANNEL = 200
RATE_LIMIT_MAX_RETRIES = 5

# Sorts before any real YYYY-MM-DD transcript, so the cap disclosure is the
# first entry an agent sees when listing a capped channel.
CAP_MARKER_LEAF = "0000-history-cap"


async def _slack_get(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    # conversations.replies is Tier 3 (~50 req/min), so a threaded backfill can
    # legitimately hit 429s; honoring Retry-After keeps the sync alive instead
    # of aborting the channel.
    for _ in range(RATE_LIMIT_MAX_RETRIES):
        resp = await client.get(url, params=params)
        if resp.status_code == 429:
            await asyncio.sleep(float(resp.headers["Retry-After"]))
            continue
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("ok"):
            raise RuntimeError("Slack API returned ok=false")
        return payload
    raise RuntimeError("Slack API kept rate limiting after retries")


async def _author_of(
    client: httpx.AsyncClient, names: dict[str, str], msg: dict
) -> tuple[str | None, str]:
    """(author_id, display name) for a message. Human messages resolve the
    display name via users.info (cached per run); bot messages carry their
    username inline. A message with neither (rare system subtypes) gets no
    author and renders unattributed."""
    user_id = msg.get("user")
    if user_id:
        return user_id, await _user_display_name(client, names, user_id)
    bot_id = msg.get("bot_id")
    if bot_id:
        return bot_id, msg.get("username") or bot_id
    return None, ""


async def _user_display_name(client: httpx.AsyncClient, names: dict[str, str], user_id: str) -> str:
    if user_id in names:
        return names[user_id]
    # One unresolvable user (deleted account, transient API error) must not
    # abort a whole sync — record the raw id so the message stays attributed.
    try:
        payload = await _slack_get(client, USERS_INFO_URL, {"user": user_id})
        profile = payload["user"].get("profile") or {}
        name = profile.get("display_name") or profile.get("real_name") or payload["user"]["name"]
    except (RuntimeError, httpx.HTTPError, KeyError) as e:
        logger.info("slack: users.info failed user=%s exception_type=%s", user_id, type(e).__name__)
        name = user_id
    names[user_id] = name
    return name


async def index_slack(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    allowed_channel_ids = set(source_service.slack_allowed_channel_ids(source))
    await source_service.purge_disallowed_copied_documents(source)
    if not allowed_channel_ids:
        # Fail loudly so the sync records a sync_error instead of reporting a
        # successful sync that ingested nothing.
        raise RuntimeError("no allowed channels configured")

    token = await get_valid_token(owner_user_id, "slack")
    headers = {"Authorization": f"Bearer {token}"}
    names: dict[str, str] = {}

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
                author_id, author = await _author_of(client, names, msg)
                await _upsert_message(
                    source_id=source_id,
                    owner_user_id=owner_user_id,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    ts=msg["ts"],
                    text=msg.get("text") or "",
                    author_id=author_id,
                    author=author,
                    thread_ts=_thread_ts_of(msg),
                )
                if msg.get("reply_count"):
                    await _index_thread_replies(
                        client=client,
                        source_id=source_id,
                        owner_user_id=owner_user_id,
                        channel_id=channel_id,
                        channel_name=channel_name,
                        parent_ts=msg["ts"],
                        names=names,
                    )
            await _sync_cap_marker(
                source_id=source_id,
                owner_user_id=owner_user_id,
                channel_id=channel_id,
                channel_name=channel_name,
                capped=bool(history.get("has_more")),
            )

    logger.info("slack source %s: backfill complete", source_id)
    return None


async def fetch_history(source: dict, since, until, limit: int = 500) -> dict:
    """On-demand: pull messages in [since, until] across allowed channels.
    Caches them (upsert) so they're searchable afterward, and returns refs."""
    source_id = UUID(source["id"])
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
    names: dict[str, str] = {}
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
                author_id, author = await _author_of(client, names, msg)
                await _upsert_message(
                    source_id=source_id,
                    owner_user_id=owner_user_id,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    ts=msg["ts"],
                    text=msg.get("text") or "",
                    author_id=author_id,
                    author=author,
                    thread_ts=_thread_ts_of(msg),
                )
                refs.append(f"{channel_name}/{msg['ts']}")
                if len(refs) >= limit:
                    break
                if msg.get("reply_count"):
                    reply_ts = await _index_thread_replies(
                        client=client,
                        source_id=source_id,
                        owner_user_id=owner_user_id,
                        channel_id=channel_id,
                        channel_name=channel_name,
                        parent_ts=msg["ts"],
                        names=names,
                    )
                    refs.extend(f"{channel_name}/{ts}" for ts in reply_ts)
                    if len(refs) >= limit:
                        break

    return {
        "fetched": len(refs),
        "since": since.isoformat(),
        "until": until.isoformat() if until else None,
        "results": [{"ref": r} for r in refs[:25]],
    }


def _thread_ts_of(msg: dict) -> str | None:
    """The parent ts if `msg` is a thread reply, else None. Slack marks thread
    parents with thread_ts == ts, and `thread_broadcast` copies in history
    carry the real parent's thread_ts."""
    thread_ts = msg.get("thread_ts")
    if not thread_ts or thread_ts == msg.get("ts"):
        return None
    return thread_ts


async def _index_thread_replies(
    *,
    client: httpx.AsyncClient,
    source_id: UUID,
    owner_user_id: UUID,
    channel_id: str,
    channel_name: str,
    parent_ts: str,
    names: dict[str, str],
) -> list[str]:
    """Page conversations.replies for one thread and upsert every reply with
    its parent linkage. Replies beyond MAX_MESSAGES_PER_CHANNEL are dropped;
    a capped thread gets a notice document, an uncapped one gets any stale
    notice removed. Returns the upserted reply ts values."""
    reply_ts: list[str] = []
    capped = False
    cursor = None
    while True:
        params = {"channel": channel_id, "ts": parent_ts, "limit": MAX_MESSAGES_PER_CHANNEL}
        if cursor:
            params["cursor"] = cursor
        payload = await _slack_get(client, CONVERSATIONS_REPLIES_URL, params)
        for msg in payload.get("messages", []):
            # conversations.replies returns the parent as its first message.
            if msg.get("type") != "message" or not msg.get("ts") or msg["ts"] == parent_ts:
                continue
            if len(reply_ts) >= MAX_MESSAGES_PER_CHANNEL:
                capped = True
                break
            author_id, author = await _author_of(client, names, msg)
            await _upsert_message(
                source_id=source_id,
                owner_user_id=owner_user_id,
                channel_id=channel_id,
                channel_name=channel_name,
                ts=msg["ts"],
                text=msg.get("text") or "",
                author_id=author_id,
                author=author,
                thread_ts=parent_ts,
            )
            reply_ts.append(msg["ts"])
        cursor = (payload.get("response_metadata") or {}).get("next_cursor")
        if capped or not cursor:
            break
    await _sync_thread_cap_marker(
        source_id=source_id,
        owner_user_id=owner_user_id,
        channel_id=channel_id,
        channel_name=channel_name,
        parent_ts=parent_ts,
        capped=capped,
    )
    return reply_ts


async def _upsert_message(
    *,
    source_id: UUID,
    owner_user_id: UUID,
    channel_id: str,
    channel_name: str,
    ts: str,
    text: str,
    author_id: str | None,
    author: str,
    thread_ts: str | None,
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
        owner_user_id=owner_user_id,
        path=path,
        name=name,
        kind="message",
        content=text,
        external_ref=f"{channel_id}:{ts}",
        extra={
            "channel_id": channel_id,
            "channel_name": channel_name,
            "ts": ts,
            "thread_ts": thread_ts,
            "author_id": author_id,
            "author": author,
        },
    )


async def _sync_cap_marker(
    *,
    source_id: UUID,
    owner_user_id: UUID,
    channel_id: str,
    channel_name: str,
    capped: bool,
) -> None:
    """Keep the channel's history-cap disclosure in step with reality. A capped
    channel gets a notice document that lists first in its directory; a channel
    whose full history fit gets any stale notice removed."""
    path = f"{channel_name}/{CAP_MARKER_LEAF}"
    if not capped:
        await get_pool().execute(
            "DELETE FROM slack_messages WHERE source_id = $1 AND path = $2",
            source_id,
            path,
        )
        return
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        owner_user_id=owner_user_id,
        path=path,
        name=f"#{channel_name} older history is NOT indexed",
        kind="notice",
        content=(
            f"Only the {MAX_MESSAGES_PER_CHANNEL} most recent messages of #{channel_name} "
            "are indexed. Older messages exist in Slack but are not searchable here — "
            "an empty search result does not mean the topic was never discussed. "
            "Pull a specific time range into the index with "
            "POST /api/v1/me/sources/{source_id}/history {since, until}."
        ),
        external_ref=None,
        extra={"channel_id": channel_id, "channel_name": channel_name, "ts": None},
    )


async def _sync_thread_cap_marker(
    *,
    source_id: UUID,
    owner_user_id: UUID,
    channel_id: str,
    channel_name: str,
    parent_ts: str,
    capped: bool,
) -> None:
    """Per-thread analogue of _sync_cap_marker: a thread whose replies exceeded
    the per-thread cap gets a notice document; one that fit gets any stale
    notice removed."""
    path = f"{channel_name}/{parent_ts}-thread-cap"
    if not capped:
        await get_pool().execute(
            "DELETE FROM slack_messages WHERE source_id = $1 AND path = $2",
            source_id,
            path,
        )
        return
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        owner_user_id=owner_user_id,
        path=path,
        name=f"#{channel_name} thread {parent_ts} is NOT fully indexed",
        kind="notice",
        content=(
            f"Only the {MAX_MESSAGES_PER_CHANNEL} oldest replies of the thread started at "
            f"{parent_ts} in #{channel_name} are indexed. Later replies exist in Slack "
            "but are not searchable here."
        ),
        external_ref=None,
        extra={"channel_id": channel_id, "channel_name": channel_name, "ts": None},
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
            "DELETE FROM slack_messages d USING user_sources s "
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
        # Edits of subtyped messages (bot_message, ...) carry the subtype inside
        # the nested message; drop them like fresh ones — except thread_broadcast,
        # which is just a reply that was also sent to the channel.
        if message.get("subtype") not in (None, "thread_broadcast"):
            return 0
        event = {**message, "channel": channel_id, "type": "message"}
    elif subtype not in (None, "thread_broadcast"):
        return 0

    if not event.get("ts"):
        return 0

    rows = await get_pool().fetch(
        "SELECT id, owner_user_id, settings FROM user_sources ws "
        "WHERE ws.source_type = 'slack' AND ws.external_ref = $1 "
        "AND ws.sync_enabled",
        team_id,
    )
    # The webhook has no user token to resolve a display name with, so live
    # messages carry the raw Slack id as their author. The next sync's
    # freshness check sees the resolved name differs and rewrites the row.
    author_id = event.get("user") or event.get("bot_id")
    author = event.get("username") or author_id or ""

    ingested = 0
    for row in rows:
        if channel_id not in source_service.slack_allowed_channel_ids(
            {"settings": row["settings"] or {}}
        ):
            continue
        await _upsert_message(
            source_id=row["id"],
            owner_user_id=row["owner_user_id"],
            channel_id=channel_id,
            channel_name=channel_id,
            ts=event["ts"],
            text=event.get("text") or "",
            author_id=author_id,
            author=author,
            thread_ts=_thread_ts_of(event),
        )
        ingested += 1
    return ingested
