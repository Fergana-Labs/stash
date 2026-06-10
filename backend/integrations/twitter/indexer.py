"""Twitter / X recent-search source.

Twitter sources are index-only and search-driven: search runs live against
X API v2 recent search, then caches returned post ids and titles so
read_source can open a specific result later. There is no background sync —
the cache is pruned by age instead (see search_twitter).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx
from fastapi import HTTPException

from ...services import source_service
from ..storage import get_valid_token
from .provider import API_BASE

RECENT_SEARCH_URL = f"{API_BASE}/2/tweets/search/recent"
TWEET_URL = f"{API_BASE}/2/tweets/{{tweet_id}}"
DEFAULT_SOURCE_REF = "recent"
SEARCH_LIMIT = 25
SNIPPET_CHARS = 300
CACHE_RETENTION_DAYS = 30
TWEET_FIELDS = "author_id,created_at,public_metrics,conversation_id,lang"
USER_FIELDS = "name,username"
# Shared by search and single-tweet fetch so the two render identically.
_TWEET_PARAMS = {
    "tweet.fields": TWEET_FIELDS,
    "expansions": "author_id",
    "user.fields": USER_FIELDS,
}


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

    text = (tweet.get("text") or "").strip()
    if text:
        quoted = "\n".join(f"> {line}" for line in text.splitlines())
        parts.append(f"\n{quoted}")
    return "\n".join(parts)


async def search_twitter(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    query = query.strip()
    if not query or limit <= 0:
        return []
    limit = min(limit, 100)

    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "twitter")
    # X requires max_results between 10 and 100; over-fetch, then slice to limit.
    max_results = max(limit, 10)
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(
            RECENT_SEARCH_URL,
            params={"query": query, "max_results": max_results, **_TWEET_PARAMS},
        )
        resp.raise_for_status()
        payload = resp.json()

    users = {
        user["id"]: user
        for user in (payload.get("includes") or {}).get("users", [])
        if user.get("id")
    }
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    hits: list[dict] = []
    # Sequential on purpose: a gather here would grab up to `limit` pool
    # connections at once on the user-facing search path.
    for tweet in payload.get("data", [])[:limit]:
        tweet_id = tweet.get("id")
        if not tweet_id:
            continue
        name = _tweet_name(tweet, users)
        await source_service.upsert_index_row(
            table="twitter_posts",
            source_id=source_id,
            workspace_id=workspace_id,
            path=tweet_id,
            name=name,
            kind="post",
            external_ref=tweet_id,
            external_updated_at=_parse_time(tweet.get("created_at")),
        )
        # Snippet is attacker-authorable text headed for agent context — cap it
        # like native sources do (they truncate snippets to 300 chars).
        hits.append(
            {"ref": tweet_id, "name": name, "snippet": (tweet.get("text") or "")[:SNIPPET_CHARS]}
        )
    await source_service.prune_index_rows(
        "twitter_posts", source_id, max_age_days=CACHE_RETENTION_DAYS
    )
    return hits


async def fetch_twitter_content(owner_user_id: UUID, tweet_id: str) -> str:
    # Refs only ever come from twitter_posts rows we populated with X's own
    # ids; the digit check pins that invariant at the request boundary.
    # isascii() too: str.isdigit() alone accepts Unicode digits like "٤٢".
    if not (tweet_id.isascii() and tweet_id.isdigit()):
        raise ValueError(f"invalid tweet id {tweet_id!r}")
    try:
        token = await get_valid_token(owner_user_id, "twitter")
    except HTTPException:
        # Cached posts outlive a disconnect; reads must say so, not 401.
        return "The Twitter / X connection is gone — reconnect it in Settings to read posts."
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(TWEET_URL.format(tweet_id=tweet_id), params=_TWEET_PARAMS)
        # X volatility is routine for cached results, not a failure: posts get
        # deleted, tokens get revoked, and lookup quotas are tiny on lower
        # plans. Degrade to readable text so agent reads never 500.
        if resp.status_code == 429:
            return "X rate limit reached while fetching this post — try again in a few minutes."
        if resp.status_code in (401, 403):
            return (
                "X rejected the Twitter / X connection for this post — "
                "reconnect it in Settings."
            )
        if resp.status_code == 404:
            return "This post is no longer available on X (deleted or protected)."
        resp.raise_for_status()
        payload = resp.json()

    # X answers 200 with an `errors` array and no `data` for deleted, protected,
    # or withheld posts.
    tweet = payload.get("data")
    if not tweet:
        return "This post is no longer available on X (deleted or protected)."

    users = (payload.get("includes") or {}).get("users") or []
    author = next((u for u in users if u.get("id") == tweet.get("author_id")), None)
    return _render_tweet(tweet, author)
