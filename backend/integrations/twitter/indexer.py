"""Twitter / X recent-search source.

Twitter sources are index-only. Search runs live against X API v2 recent search,
then caches returned post ids and titles so read_source can open a specific
result later.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

API_BASE = "https://api.x.com"
RECENT_SEARCH_URL = f"{API_BASE}/2/tweets/search/recent"
TWEET_URL = f"{API_BASE}/2/tweets/{{tweet_id}}"
USER_URL = f"{API_BASE}/2/users/{{user_id}}"
DEFAULT_SOURCE_REF = "recent"
SEARCH_LIMIT = 25
TWEET_FIELDS = "author_id,created_at,public_metrics,conversation_id,lang"
USER_FIELDS = "name,username"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _tweet_name(tweet: dict, users: dict[str, dict]) -> str:
    user = users.get(tweet.get("author_id") or "")
    username = user.get("username") if user else None
    prefix = f"@{username}" if username else "Post"
    created = tweet.get("created_at", "")[:10]
    return f"{prefix} - {created}" if created else prefix


def _render_tweet(tweet: dict, user: dict | None = None) -> str:
    parts: list[str] = []
    if user:
        username = user.get("username")
        name = user.get("name") or username
        if username:
            parts.append(f"# @{username}")
        elif name:
            parts.append(f"# {name}")
    else:
        parts.append("# X post")

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

    text = (tweet.get("text") or "").strip()
    if text:
        parts.append(f"\n{text}")
    return "\n".join(parts)


async def index_twitter(source: dict) -> str | None:
    default_query = source.get("external_ref")
    if not default_query or default_query == DEFAULT_SOURCE_REF:
        return None
    await search_twitter(source, default_query)
    return None


async def search_twitter(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    query = query.strip()
    if not query:
        return []

    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "twitter")
    max_results = min(max(limit, 10), 100)
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(
            RECENT_SEARCH_URL,
            params={
                "query": query,
                "max_results": max_results,
                "tweet.fields": TWEET_FIELDS,
                "expansions": "author_id",
                "user.fields": USER_FIELDS,
            },
        )
        resp.raise_for_status()
        payload = resp.json()

    users = {
        user["id"]: user
        for user in (payload.get("includes") or {}).get("users", [])
        if user.get("id")
    }
    hits: list[dict] = []
    for tweet in payload.get("data", [])[:limit]:
        tweet_id = tweet.get("id")
        if not tweet_id:
            continue
        name = _tweet_name(tweet, users)
        await source_service.upsert_index_row(
            table="twitter_posts",
            source_id=UUID(source["id"]),
            workspace_id=UUID(source["workspace_id"]),
            path=tweet_id,
            name=name,
            kind="post",
            external_ref=tweet_id,
            external_updated_at=_parse_time(tweet.get("created_at")),
        )
        hits.append({"ref": tweet_id, "name": name, "snippet": tweet.get("text") or ""})
    return hits


async def fetch_twitter_content(owner_user_id: UUID, tweet_id: str) -> str:
    token = await get_valid_token(owner_user_id, "twitter")
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        tweet_resp = await client.get(
            TWEET_URL.format(tweet_id=tweet_id),
            params={"tweet.fields": TWEET_FIELDS},
        )
        tweet_resp.raise_for_status()
        tweet = tweet_resp.json().get("data") or {}

        user = None
        if tweet.get("author_id"):
            user_resp = await client.get(
                USER_URL.format(user_id=tweet["author_id"]),
                params={"user.fields": USER_FIELDS},
            )
            user_resp.raise_for_status()
            user = user_resp.json().get("data")

    return _render_tweet(tweet, user)
