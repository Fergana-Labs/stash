"""Slack → slack_messages: one-time backfill + per-event ingest.

`index_slack` backfills recent history for the source's explicit channel
allowlist. Live updates arrive via the Events API webhook, which enqueues
`ingest_slack_message` per message. Each message is a row at `{channel}/{ts}`
(with native channel_id/channel_name/ts and author columns); the *document
projection* over these rows is one transcript per channel per UTC day (see
source_service.list_documents/read_document), so agents read coherent,
attributed conversations instead of one-line files.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

import httpx

from ...database import get_pool
from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

CONVERSATIONS_LIST_URL = "https://slack.com/api/conversations.list"
CONVERSATIONS_HISTORY_URL = "https://slack.com/api/conversations.history"
CONVERSATIONS_MEMBERS_URL = "https://slack.com/api/conversations.members"
CONVERSATIONS_INFO_URL = "https://slack.com/api/conversations.info"
USERS_INFO_URL = "https://slack.com/api/users.info"
AUTH_TEST_URL = "https://slack.com/api/auth.test"

CHANNEL_TYPES = "public_channel,private_channel,im,mpim"
MAX_CHANNELS = 100
MAX_MESSAGES_PER_CHANNEL = 200

# Sorts before any real YYYY-MM-DD transcript, so the cap disclosure is the
# first entry an agent sees when listing a capped channel.
CAP_MARKER_LEAF = "0000-history-cap"


async def _slack_get(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError("Slack API returned ok=false")
    return payload


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


def _name_slug(value: str) -> str:
    """A display name flattened for use in channel_name (which is a path
    segment): lowercase, runs of anything unsafe collapsed to '-'."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-")
    return slug or "unknown"


async def authed_user_id(client: httpx.AsyncClient) -> str:
    """The Slack user id behind this token — excluded from group-DM names so a
    DM is named after the *other* people in it."""
    return (await _slack_get(client, AUTH_TEST_URL, {}))["user_id"]


async def channel_display_name(
    client: httpx.AsyncClient, names: dict[str, str], channel: dict, self_user_id: str
) -> str:
    """A human channel_name. Slack gives channels a name but IMs none at all,
    so a DM is named after its counterpart (dm-jane-doe) and a group DM after
    every member except the token's own user (dm-jane-doe--sam-liu)."""
    if channel.get("is_im"):
        return f"dm-{_name_slug(await _user_display_name(client, names, channel['user']))}"
    if channel.get("is_mpim"):
        payload = await _slack_get(
            client, CONVERSATIONS_MEMBERS_URL, {"channel": channel["id"], "limit": 100}
        )
        members = [m for m in payload.get("members", []) if m != self_user_id]
        slugs = sorted([_name_slug(await _user_display_name(client, names, m)) for m in members])
        return "dm-" + "--".join(slugs)
    return channel["name"]


def _dedupe_channel_names(named: list[tuple[dict, str]]) -> list[tuple[dict, str]]:
    """Two DMs with identically-named counterparts must not share a
    channel_name — the day-transcript projection groups by it, so a collision
    would silently merge two conversations. Colliding names get the channel id
    appended; unique names stay clean."""
    counts: dict[str, int] = {}
    for _, name in named:
        counts[name] = counts.get(name, 0) + 1
    return [
        (channel, f"{name}--{channel['id'].lower()}" if counts[name] > 1 else name)
        for channel, name in named
    ]


async def _rename_channel_rows(source_id: UUID, channel_id: str, channel_name: str) -> None:
    """One-shot migration of rows ingested before this channel's name was
    known (webhook rows stamped with the raw id, DMs indexed pre-name-
    resolution) onto the resolved name. Runs at sync time because names live
    behind per-user tokens — an offline migration can't resolve them. Stale
    notices are deleted, not renamed; _sync_cap_marker recreates them."""
    pool = get_pool()
    await pool.execute(
        "DELETE FROM slack_messages "
        "WHERE source_id = $1 AND channel_id = $2 AND kind = 'notice' AND channel_name <> $3",
        source_id,
        channel_id,
        channel_name,
    )
    await pool.execute(
        "UPDATE slack_messages "
        "SET channel_name = $3, "
        "    path = $3 || substr(path, strpos(path, '/')), "
        "    name = '#' || $3 "
        "WHERE source_id = $1 AND channel_id = $2 AND channel_name <> $3",
        source_id,
        channel_id,
        channel_name,
    )


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
        self_user_id = await authed_user_id(client)
        named = _dedupe_channel_names(
            [
                (channel, await channel_display_name(client, names, channel, self_user_id))
                for channel in channels_payload.get("channels", [])
                if channel["id"] in allowed_channel_ids
            ]
        )
        for channel, channel_name in named:
            channel_id = channel["id"]
            await _rename_channel_rows(source_id, channel_id, channel_name)
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
        self_user_id = await authed_user_id(client)
        named = _dedupe_channel_names(
            [
                (channel, await channel_display_name(client, names, channel, self_user_id))
                for channel in channels
                if channel["id"] in allowed_channel_ids
            ]
        )
        for channel, channel_name in named:
            if len(refs) >= limit:
                break
            channel_id = channel["id"]
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
    owner_user_id: UUID,
    channel_id: str,
    channel_name: str,
    ts: str,
    text: str,
    author_id: str | None,
    author: str,
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
        "SELECT id, owner_user_id, settings FROM user_sources ws "
        "WHERE ws.source_type = 'slack' AND ws.external_ref = $1 "
        "AND ws.sync_enabled",
        team_id,
    )
    # The webhook payload carries no display names, so live messages keep the
    # raw Slack id as their author. The next sync's freshness check sees the
    # resolved name differs and rewrites the row.
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
            channel_name=await _ingest_channel_name(row, channel_id),
            ts=event["ts"],
            text=event.get("text") or "",
            author_id=author_id,
            author=author,
        )
        ingested += 1
    return ingested


async def _ingest_channel_name(source_row: dict, channel_id: str) -> str:
    """The channel_name for a live event. Sync already resolved it for any
    channel with indexed rows; a channel with none yet (first message of a new
    DM) is resolved against Slack with the owner's token, so no row is ever
    written with a raw id as its name."""
    known = await get_pool().fetchval(
        "SELECT channel_name FROM slack_messages "
        "WHERE source_id = $1 AND channel_id = $2 AND channel_name <> channel_id "
        "LIMIT 1",
        source_row["id"],
        channel_id,
    )
    if known:
        return known
    token = await get_valid_token(source_row["owner_user_id"], "slack")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        channel = (await _slack_get(client, CONVERSATIONS_INFO_URL, {"channel": channel_id}))[
            "channel"
        ]
        return await channel_display_name(client, {}, channel, await authed_user_id(client))
