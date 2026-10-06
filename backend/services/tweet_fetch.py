"""Fetch one tweet as markdown via twitterapi.io.

The fetch behind web clips of x.com status URLs: the full tweet text, the
author's whole thread, and the reply's direct parent for context.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

TAPI_TWEETS_URL = "https://api.twitterapi.io/twitter/tweets"
TAPI_THREAD_URL = "https://api.twitterapi.io/twitter/tweet/thread_context"
TAPI_TIMEOUT = 60
MAX_MEDIA_PER_TWEET = 4
# Thread context pages fetched per tweet. A page carries the ancestors plus a
# slice of the replies; on a viral tweet the author's own continuation sits
# early, so a small cap finds real self-threads without walking whole reply
# storms.
MAX_THREAD_PAGES = 3


def tweet_url(tweet_id: str) -> str:
    return f"https://x.com/i/status/{tweet_id}"


async def fetch_tweet_markdown(tweet_id: str) -> dict:
    """One tweet rendered as markdown, with its author thread and reply
    parent — the standalone fetch behind web clips of x.com status URLs.
    No user_source or media archiving involved. Returns {title, markdown}."""
    if not settings.TWITTERAPI_IO_KEY:
        raise RuntimeError("TWITTERAPI_IO_KEY is not set")
    async with httpx.AsyncClient(
        timeout=TAPI_TIMEOUT, headers={"X-API-Key": settings.TWITTERAPI_IO_KEY}
    ) as client:
        tweet = await _fetch_tweet(client, tweet_id)
        thread = [tweet]
        parent = None
        if _in_conversation(tweet):
            # Best-effort — the tweet itself matters.
            try:
                context = await _fetch_thread_context(client, tweet_id)
                thread = _author_chain(tweet, context)
                parent = _direct_parent(tweet, context)
            except Exception as exc:
                logger.warning(
                    "x thread context fetch failed tweet=%s exception_type=%s",
                    tweet_id,
                    type(exc).__name__,
                )
    posted = tweet["created_at"]
    title = f"@{tweet['author']} - {posted.date().isoformat()}" if posted else f"@{tweet['author']}"
    return {"title": title, "markdown": _render(tweet, thread, parent)}


def _in_conversation(tweet: dict) -> bool:
    is_reply = bool(tweet["conversation_id"]) and tweet["conversation_id"] != tweet["id"]
    return is_reply or tweet["reply_count"] > 0


async def _fetch_thread_context(client: httpx.AsyncClient, tweet_id: str) -> list[dict]:
    """The saved tweet's conversation from twitterapi.io: ancestors plus a
    bounded number of reply pages, normalized."""
    tweets: list[dict] = []
    cursor: str | None = None
    for _ in range(MAX_THREAD_PAGES):
        params: dict = {"tweetId": tweet_id}
        if cursor:
            params["cursor"] = cursor
        response = await client.get(TAPI_THREAD_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        tweets.extend(_normalize(t) for t in payload.get("tweets") or [] if t.get("id"))
        cursor = payload.get("next_cursor")
        if not payload.get("has_next_page") or not cursor:
            break
    return tweets


def _author_chain(tweet: dict, context: list[dict]) -> list[dict]:
    """The author's own connected run of posts (the self-thread) containing
    the saved tweet, chronological. Other users' replies never enter the
    chain. Tweet ids are snowflakes, so numeric id order is time order."""
    own = {t["id"]: t for t in context if t["author"] == tweet["author"]}
    own[tweet["id"]] = tweet

    # Walk up to the top of the author's chain (visited-guard against
    # malformed reply cycles), then collect every own post chained under it.
    top = tweet
    visited = {tweet["id"]}
    while (parent_id := top.get("in_reply_to_id")) in own and parent_id not in visited:
        top = own[parent_id]
        visited.add(parent_id)

    chain = [top]
    included = {top["id"]}
    for t in sorted(own.values(), key=lambda t: int(t["id"])):
        if t["id"] not in included and t.get("in_reply_to_id") in included:
            chain.append(t)
            included.add(t["id"])
    return chain


def _direct_parent(tweet: dict, context: list[dict]) -> dict | None:
    """The other-author tweet the save replies to; the author's own parents
    are already covered by the thread chain."""
    parent_id = tweet.get("in_reply_to_id")
    if not parent_id:
        return None
    parent = next((t for t in context if t["id"] == parent_id), None)
    if parent is None or parent["author"] == tweet["author"]:
        return None
    return parent


def _render(tweet: dict, thread: list[dict], parent: dict | None) -> str:
    # Tweet text first so the listing's preview (first paragraph of content) is
    # the tweet itself, not metadata. Everything after the blank line is the
    # byline, reply context, thread, and link.
    parts: list[str] = [tweet["text"] or "", ""]
    byline = f"— @{tweet['author']}"
    if tweet["created_at"]:
        byline += f", {tweet['created_at'].date().isoformat()}"
    parts.append(byline)
    if parent is not None:
        parts.append(f"In reply to @{parent['author']}: {parent['text']}")
    if len(thread) > 1:
        parts.append("")
        parts.append(f"## Thread by @{tweet['author']} ({len(thread)} posts)")
        for t in thread:
            parts.append("")
            parts.append(t["text"] or "")
    parts.append(tweet_url(tweet["id"]))
    return "\n".join(parts)


async def _fetch_tweet(client: httpx.AsyncClient, tweet_id: str) -> dict:
    response = await client.get(TAPI_TWEETS_URL, params={"tweet_ids": tweet_id})
    response.raise_for_status()
    tweets = response.json().get("tweets") or []
    # twitterapi.io returns an object with empty fields (rather than 404) for a
    # deleted / suspended / protected tweet — treat that as unavailable so it
    # fails loud onto the row instead of archiving a blank save.
    if not tweets or not tweets[0].get("id"):
        raise RuntimeError(f"tweet {tweet_id} is unavailable (deleted, private, or suspended)")
    return _normalize(tweets[0])


def _normalize(t: dict) -> dict:
    """Pull the fields we need out of a twitterapi.io tweet object."""
    return {
        "id": t.get("id") or "",
        "text": t.get("text") or "",
        "author": (t.get("author") or {}).get("userName") or "unknown",
        "created_at": _parse_time(t.get("createdAt")),
        "conversation_id": t.get("conversationId"),
        "in_reply_to_id": t.get("inReplyToId"),
        "reply_count": t.get("replyCount") or 0,
        "media": _media_urls(t),
    }


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    for fmt in ("%a %b %d %H:%M:%S %z %Y",):  # classic Twitter format
        try:
            return datetime.strptime(value, fmt).astimezone(UTC)
        except (ValueError, TypeError):
            pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _media_urls(tweet: dict) -> list[dict]:
    """[{url, is_video}] for each image/video on the tweet (best variant).
    twitterapi.io carries the native Twitter media shape under extendedEntities."""
    entities = tweet.get("extendedEntities") or tweet.get("entities") or {}
    out: list[dict] = []
    for m in (entities.get("media") or [])[:MAX_MEDIA_PER_TWEET]:
        if m.get("type") in ("video", "animated_gif"):
            variants = [v for v in (m.get("video_info") or {}).get("variants", []) if v.get("url")]
            mp4 = [v for v in variants if v.get("content_type") == "video/mp4"]
            best = max(mp4 or variants, key=lambda v: v.get("bitrate", 0), default=None)
            if best:
                out.append({"url": best["url"], "is_video": True})
        elif m.get("media_url_https"):
            out.append({"url": m["media_url_https"], "is_video": False})
    return out
