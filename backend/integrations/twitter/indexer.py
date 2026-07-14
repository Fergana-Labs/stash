"""Twitter / X source reads and recent search.

Twitter sources are search-driven for public X search: scoped searches run live
against X API v2 recent search, then cache returned post ids so read_source can
open specific results later. Personal account surfaces are read live from the
connected user's OAuth token through stable virtual refs like `bookmarks`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx
from fastapi import HTTPException

from ...services import source_service
from ..storage import get_valid_token
from .provider import API_BASE, ME_URL

RECENT_SEARCH_URL = f"{API_BASE}/2/tweets/search/recent"
TWEET_URL = f"{API_BASE}/2/tweets/{{tweet_id}}"
HOME_TIMELINE_URL = f"{API_BASE}/2/users/{{user_id}}/timelines/reverse_chronological"
USER_TWEETS_URL = f"{API_BASE}/2/users/{{user_id}}/tweets"
BOOKMARKS_URL = f"{API_BASE}/2/users/{{user_id}}/bookmarks"
LIKED_TWEETS_URL = f"{API_BASE}/2/users/{{user_id}}/liked_tweets"
DM_EVENTS_URL = f"{API_BASE}/2/dm_events"
LIKING_USERS_URL = f"{API_BASE}/2/tweets/{{tweet_id}}/liking_users"
RETWEETED_BY_URL = f"{API_BASE}/2/tweets/{{tweet_id}}/retweeted_by"

SEARCH_LIMIT = 25
READ_LIMIT = 25
IDENTITY_LIMIT = 100
CACHE_RETENTION_DAYS = 30

TWEET_FIELDS = "author_id,created_at,public_metrics,conversation_id,lang,note_tweet"
USER_FIELDS = "name,username"
DM_EVENT_FIELDS = "id,text,event_type,created_at,sender_id,participant_ids,dm_conversation_id"
_TWEET_PARAMS = {
    "tweet.fields": TWEET_FIELDS,
    "expansions": "author_id",
    "user.fields": USER_FIELDS,
}
_DM_PARAMS = {
    "max_results": READ_LIMIT,
    "dm_event.fields": DM_EVENT_FIELDS,
    "expansions": "sender_id,participant_ids",
    "user.fields": USER_FIELDS,
}

TWITTER_LIVE_ENTRIES = [
    {"path": "home", "name": "Home timeline", "kind": "feed"},
    {"path": "my-posts", "name": "My posts", "kind": "feed"},
    {"path": "bookmarks", "name": "Bookmarks", "kind": "feed"},
    {"path": "likes", "name": "Liked posts", "kind": "feed"},
    {"path": "dms", "name": "Direct messages", "kind": "feed"},
]
_LIVE_PATHS = {entry["path"] for entry in TWITTER_LIVE_ENTRIES}
_POST_PREFIX = "post:"
_THREAD_PREFIX = "thread:"
_LIKERS_PREFIX = "likers:"
_REPOSTERS_PREFIX = "reposters:"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_x_id(value: str) -> bool:
    return bool(value) and value.isascii() and value.isdigit()


def _prefixed_id(ref: str, prefix: str) -> str | None:
    if not ref.startswith(prefix):
        return None
    value = ref[len(prefix) :]
    return value if _is_x_id(value) else None


def twitter_live_entries(prefix: str = "") -> list[dict]:
    return [entry for entry in TWITTER_LIVE_ENTRIES if entry["path"].startswith(prefix)]


def is_twitter_live_ref(ref: str) -> bool:
    if ref in _LIVE_PATHS or _is_x_id(ref):
        return True
    for prefix in (_POST_PREFIX, _THREAD_PREFIX, _LIKERS_PREFIX, _REPOSTERS_PREFIX):
        if _prefixed_id(ref, prefix):
            return True
    return False


def twitter_ref_name(ref: str) -> str:
    names = {entry["path"]: entry["name"] for entry in TWITTER_LIVE_ENTRIES}
    if ref in names:
        return names[ref]
    if _is_x_id(ref):
        return f"X post {ref}"
    if tweet_id := _prefixed_id(ref, _POST_PREFIX):
        return f"X post {tweet_id}"
    if conversation_id := _prefixed_id(ref, _THREAD_PREFIX):
        return f"Reply thread {conversation_id}"
    if tweet_id := _prefixed_id(ref, _LIKERS_PREFIX):
        return f"People who liked {tweet_id}"
    if tweet_id := _prefixed_id(ref, _REPOSTERS_PREFIX):
        return f"People who reposted {tweet_id}"
    return ref


def _tweet_text(tweet: dict) -> str:
    """A long-form post carries its full body in note_tweet; its `text` field is
    the ~280-char truncation. Standard posts have no note_tweet."""
    note = tweet.get("note_tweet") or {}
    return note.get("text") or tweet.get("text") or ""


def _tweet_name(tweet: dict, users: dict[str, dict]) -> str:
    user = users.get(tweet.get("author_id") or "")
    username = user.get("username") if user else None
    prefix = f"@{username}" if username else "Post"
    created = (tweet.get("created_at") or "")[:10]
    return f"{prefix} - {created}" if created else prefix


def _render_tweet(tweet: dict, user: dict | None = None) -> str:
    # Posts are public, attacker-authorable content headed for agent context.
    # Only the X-constrained username ([A-Za-z0-9_]) may become a heading; the
    # body is blockquoted so it can't masquerade as document structure.
    username = (user or {}).get("username")
    parts: list[str] = [f"# @{username}" if username else "# X post"]

    if tweet.get("created_at"):
        parts.append(f"Created: {tweet['created_at']}")

    metrics = tweet.get("public_metrics") or {}
    if metrics:
        parts.append(
            "Metrics: "
            f"{metrics.get('like_count', 0)} likes, "
            f"{metrics.get('retweet_count', 0)} reposts, "
            f"{metrics.get('reply_count', 0)} replies"
        )

    tweet_id = tweet.get("id")
    if tweet_id:
        parts.append(f"Post ref: post:{tweet_id}")
    conversation_id = tweet.get("conversation_id")
    if conversation_id:
        parts.append(f"Thread ref: thread:{conversation_id}")
    if tweet_id:
        parts.append(f"Likers ref: likers:{tweet_id}")
        parts.append(f"Reposters ref: reposters:{tweet_id}")

    text = _tweet_text(tweet).strip()
    if text:
        quoted = "\n".join(f"> {line}" for line in text.splitlines())
        parts.append(f"\n{quoted}")
    return "\n".join(parts)


def _users_by_id(payload: dict) -> dict[str, dict]:
    return {
        user["id"]: user
        for user in (payload.get("includes") or {}).get("users", [])
        if user.get("id")
    }


def _render_tweets(title: str, payload: dict, *, note: str | None = None) -> str:
    tweets = payload.get("data") or []
    if not tweets:
        return f"# {title}\n\nNo posts were returned by X."

    users = _users_by_id(payload)
    parts = [f"# {title}", f"Returned posts: {len(tweets)}"]
    if note:
        parts.append(note)
    next_token = (payload.get("meta") or {}).get("next_token")
    if next_token:
        parts.append("More posts exist on X; this read shows the first page.")

    for tweet in tweets:
        parts.append(_render_tweet(tweet, users.get(tweet.get("author_id") or "")))
    return "\n\n---\n\n".join(parts)


def _safe_line(value: str | None) -> str:
    return " ".join((value or "").split())


def _render_users(title: str, payload: dict) -> str:
    users = payload.get("data") or []
    if not users:
        return f"# {title}\n\nNo users were returned by X."

    parts = [f"# {title}", f"Returned users: {len(users)}"]
    next_token = (payload.get("meta") or {}).get("next_token")
    if next_token:
        parts.append("More users exist on X; this read shows the first page.")
    for user in users:
        username = _safe_line(user.get("username"))
        name = _safe_line(user.get("name"))
        label = f"@{username}" if username else "Unknown user"
        if name:
            label = f"{label} - {name}"
        parts.append(f"- {label}")
    return "\n".join(parts)


def _render_dm_events(payload: dict) -> str:
    events = payload.get("data") or []
    if not events:
        return "# Direct messages\n\nNo recent DM events were returned by X."

    users = _users_by_id(payload)
    parts = ["# Direct messages", f"Returned events: {len(events)}"]
    next_token = (payload.get("meta") or {}).get("next_token")
    if next_token:
        parts.append("More DM events exist on X; this read shows the first page.")

    for event in events:
        event_parts = [f"## Event {_safe_line(event.get('id'))}"]
        if event.get("event_type"):
            event_parts.append(f"Type: {_safe_line(event['event_type'])}")
        if event.get("created_at"):
            event_parts.append(f"Created: {_safe_line(event['created_at'])}")
        sender = users.get(event.get("sender_id") or "")
        if sender and sender.get("username"):
            event_parts.append(f"Sender: @{_safe_line(sender['username'])}")
        participant_ids = event.get("participant_ids") or []
        participants = [
            f"@{_safe_line(users[p]['username'])}"
            for p in participant_ids
            if p in users and users[p].get("username")
        ]
        if participants:
            event_parts.append(f"Participants: {', '.join(participants)}")
        text = (event.get("text") or "").strip()
        if text:
            quoted = "\n".join(f"> {line}" for line in text.splitlines())
            event_parts.append(f"\n{quoted}")
        parts.append("\n".join(event_parts))
    return "\n\n---\n\n".join(parts)


def _read_error_text(status_code: int, label: str) -> str | None:
    if status_code == 429:
        return f"X rate limit reached while fetching {label} - try again in a few minutes."
    if status_code in (401, 403):
        return f"X rejected the Twitter / X connection while fetching {label} - reconnect it in Settings."
    if status_code == 404:
        return f"{label} is no longer available on X."
    return None


async def fetch_me(token: str) -> dict:
    """Resolve the connected X account (id, username). Called once when the
    source is added: /users/me is X's most rate-limited endpoint (~25/day on
    the free tier), so reads must never depend on it — the id is stored as the
    source's external_ref instead."""
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(ME_URL, params={"user.fields": USER_FIELDS})
    resp.raise_for_status()
    user = resp.json().get("data") or {}
    if not user.get("id"):
        raise RuntimeError("X did not return the connected user id")
    return user


async def _fetch_tweets_page(
    client: httpx.AsyncClient,
    url: str,
    title: str,
    *,
    params: dict | None = None,
    note: str | None = None,
) -> str:
    resp = await client.get(
        url,
        params={"max_results": READ_LIMIT, **_TWEET_PARAMS, **(params or {})},
    )
    if message := _read_error_text(resp.status_code, title):
        return message
    resp.raise_for_status()
    return _render_tweets(title, resp.json(), note=note)


async def _fetch_post(client: httpx.AsyncClient, tweet_id: str) -> str:
    resp = await client.get(TWEET_URL.format(tweet_id=tweet_id), params=_TWEET_PARAMS)
    if message := _read_error_text(resp.status_code, "this post"):
        return message
    resp.raise_for_status()
    payload = resp.json()

    tweet = payload.get("data")
    if not tweet:
        return "This post is no longer available on X (deleted or protected)."

    users = (payload.get("includes") or {}).get("users") or []
    author = next((u for u in users if u.get("id") == tweet.get("author_id")), None)
    return _render_tweet(tweet, author)


async def search_twitter(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    query = query.strip()
    if not query or limit <= 0:
        return []
    limit = min(limit, 100)

    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "twitter")
    max_results = max(limit, 10)
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(
            RECENT_SEARCH_URL,
            params={"query": query, "max_results": max_results, **_TWEET_PARAMS},
        )
        resp.raise_for_status()
        payload = resp.json()

    users = _users_by_id(payload)
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    hits: list[dict] = []
    for tweet in payload.get("data", [])[:limit]:
        tweet_id = tweet.get("id")
        if not tweet_id:
            continue
        name = _tweet_name(tweet, users)
        await source_service.upsert_index_row(
            table="twitter_posts",
            source_id=source_id,
            owner_user_id=owner_user_id,
            path=tweet_id,
            name=name,
            kind="post",
            external_ref=tweet_id,
            external_updated_at=_parse_time(tweet.get("created_at")),
        )
        hits.append({"ref": tweet_id, "name": name, "snippet": _tweet_text(tweet)})
    await source_service.prune_index_rows(
        "twitter_posts", source_id, max_age_days=CACHE_RETENTION_DAYS
    )
    return hits


async def fetch_twitter_content(owner_user_id: UUID, account_id: str, ref: str) -> str:
    """Read one live ref. `account_id` is the connected X user id stored as the
    source's external_ref — personal feeds are addressed by id, and resolving
    it per-read via /users/me would hit that endpoint's own (much tighter)
    rate limit."""
    if not is_twitter_live_ref(ref):
        raise ValueError(f"invalid twitter ref {ref!r}")
    try:
        token = await get_valid_token(owner_user_id, "twitter")
    except HTTPException:
        return "The Twitter / X connection is gone - reconnect it in Settings to read posts."

    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        if ref == "home":
            return await _fetch_tweets_page(
                client,
                HOME_TIMELINE_URL.format(user_id=account_id),
                "Home timeline",
            )
        if ref == "my-posts":
            return await _fetch_tweets_page(
                client,
                USER_TWEETS_URL.format(user_id=account_id),
                "My posts",
            )
        if ref == "bookmarks":
            return await _fetch_tweets_page(
                client,
                BOOKMARKS_URL.format(user_id=account_id),
                "Bookmarks",
            )
        if ref == "likes":
            return await _fetch_tweets_page(
                client,
                LIKED_TWEETS_URL.format(user_id=account_id),
                "Liked posts",
            )
        if ref == "dms":
            resp = await client.get(DM_EVENTS_URL, params=_DM_PARAMS)
            if message := _read_error_text(resp.status_code, "direct messages"):
                return message
            resp.raise_for_status()
            return _render_dm_events(resp.json())
        if _is_x_id(ref):
            return await _fetch_post(client, ref)
        if tweet_id := _prefixed_id(ref, _POST_PREFIX):
            return await _fetch_post(client, tweet_id)
        if conversation_id := _prefixed_id(ref, _THREAD_PREFIX):
            return await _fetch_tweets_page(
                client,
                RECENT_SEARCH_URL,
                f"Reply thread {conversation_id}",
                params={"query": f"conversation_id:{conversation_id}"},
                note="Thread expansion uses the X recent-search window available to this app.",
            )
        if tweet_id := _prefixed_id(ref, _LIKERS_PREFIX):
            resp = await client.get(
                LIKING_USERS_URL.format(tweet_id=tweet_id),
                params={"max_results": IDENTITY_LIMIT, "user.fields": USER_FIELDS},
            )
            if message := _read_error_text(resp.status_code, f"people who liked {tweet_id}"):
                return message
            resp.raise_for_status()
            return _render_users(f"People who liked {tweet_id}", resp.json())
        if tweet_id := _prefixed_id(ref, _REPOSTERS_PREFIX):
            resp = await client.get(
                RETWEETED_BY_URL.format(tweet_id=tweet_id),
                params={"max_results": IDENTITY_LIMIT, "user.fields": USER_FIELDS},
            )
            if message := _read_error_text(resp.status_code, f"people who reposted {tweet_id}"):
                return message
            resp.raise_for_status()
            return _render_users(f"People who reposted {tweet_id}", resp.json())

    raise ValueError(f"invalid twitter ref {ref!r}")
