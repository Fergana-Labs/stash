"""Hydrate X (Twitter) saves via ScrapeCreators.

Skeleton rows arrive from the extension push (routers/sources.py
x_items_router) as tweet URLs + a kind (Bookmark/Post/Reply/Article). Each
sync pass fills a bounded batch: the full tweet text + author from
ScrapeCreators, the conversation root for reply context, and the tweet's
images/video archived into object storage — so the save survives the tweet
being deleted or the account going private. Per-item failures land on the
row, loudly; rows are never deleted by sync (archive semantics).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx

from ...config import settings
from ...database import get_pool
from ...services import source_service, storage_service

logger = logging.getLogger(__name__)

SC_TWEET_URL = "https://api.scrapecreators.com/v1/twitter/tweet"
SC_TIMEOUT = 60
MAX_MEDIA_BYTES = 100 * 1024 * 1024
MAX_MEDIA_PER_TWEET = 4
HYDRATION_BATCH = 25
MAX_HYDRATION_ATTEMPTS = 3


def tweet_url(tweet_id: str) -> str:
    return f"https://x.com/i/status/{tweet_id}"


async def index_x_saves(source: dict) -> str | None:
    if not settings.SCRAPECREATORS_API_KEY:
        raise RuntimeError("SCRAPECREATORS_API_KEY is not set")
    if not storage_service.is_configured():
        raise RuntimeError("File storage is not configured; cannot archive save media")

    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    pool = get_pool()
    rows = await pool.fetch(
        f"""
        SELECT id, path, kind FROM x_save_docs
        WHERE source_id = $1 AND (
              hydration_status = 'pending'
           OR (hydration_status = 'failed' AND hydration_attempts < {MAX_HYDRATION_ATTEMPTS})
        )
        ORDER BY created_at
        LIMIT {HYDRATION_BATCH}
        """,
        source_id,
    )

    async with httpx.AsyncClient(
        timeout=SC_TIMEOUT, headers={"x-api-key": settings.SCRAPECREATORS_API_KEY}
    ) as client:
        for row in rows:
            try:
                await _hydrate_one(client, source_id, owner_user_id, row["path"], row["kind"])
            except Exception as exc:
                logger.warning(
                    "x save hydration failed source=%s path=%s exception_type=%s",
                    source_id,
                    row["path"],
                    type(exc).__name__,
                )
                await pool.execute(
                    "UPDATE x_save_docs SET hydration_status = 'failed', "
                    "hydration_error = $3, hydration_attempts = hydration_attempts + 1, "
                    "updated_at = now() WHERE source_id = $1 AND path = $2",
                    source_id,
                    row["path"],
                    f"{type(exc).__name__}: {exc}"[:2000],
                )
    return None


async def _hydrate_one(
    client: httpx.AsyncClient,
    source_id: UUID,
    owner_user_id: UUID,
    tweet_id: str,
    kind: str,
) -> None:
    tweet = await _fetch_tweet(client, tweet_url(tweet_id))

    # A reply shows only its own text out of context, so pull the root of the
    # conversation and keep it as "In reply to:" above the reply.
    root = None
    root_id = tweet.get("conversation_id")
    if root_id and root_id != tweet_id:
        try:
            root = await _fetch_tweet(client, tweet_url(root_id))
        except Exception:
            root = None  # thread context is best-effort; the reply itself matters

    media = await _archive_media(owner_user_id, tweet_id, tweet["media"])

    content = _render(tweet, root)
    posted = tweet["created_at"]
    await source_service.upsert_content_document(
        table="x_save_docs",
        source_id=source_id,
        owner_user_id=owner_user_id,
        path=tweet_id,
        name=f"@{tweet['author']} - {posted.date().isoformat()}"
        if posted
        else f"@{tweet['author']}",
        kind=kind,
        content=content,
        external_ref=tweet_id,
        external_updated_at=posted,
    )
    await get_pool().execute(
        "UPDATE x_save_docs SET media = $3, hydration_status = 'done', "
        "hydration_error = NULL, updated_at = now() WHERE source_id = $1 AND path = $2",
        source_id,
        tweet_id,
        media,
    )


def _render(tweet: dict, root: dict | None) -> str:
    parts: list[str] = []
    if root is not None:
        parts.append(f"# In reply to @{root['author']}")
        parts.append(_quote(root["text"]))
        parts.append("\n---\n")
    parts.append(f"# @{tweet['author']}")
    if tweet["created_at"]:
        parts.append(f"Posted: {tweet['created_at'].isoformat()}")
    parts.append(f"URL: {tweet_url(tweet['id'])}")
    parts.append("")
    parts.append(_quote(tweet["text"]))
    return "\n".join(parts)


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" for line in (text or "").splitlines())


async def _fetch_tweet(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(SC_TWEET_URL, params={"url": url})
    response.raise_for_status()
    return _normalize(response.json())


def _normalize(payload: dict) -> dict:
    """Pull the fields we need out of ScrapeCreators' tweet response, tolerant
    of the exact envelope (data/tweet wrapper, legacy shape)."""
    t = payload.get("data") or payload.get("tweet") or payload
    t = t.get("tweet") or t
    legacy = t.get("legacy") or t
    tweet_id = t.get("rest_id") or legacy.get("id_str") or str(legacy.get("id") or "")
    user = (
        (t.get("core") or {}).get("user_results", {}).get("result", {}).get("legacy")
        or t.get("user")
        or legacy.get("user")
        or {}
    )
    created = legacy.get("created_at")
    return {
        "id": tweet_id,
        "text": legacy.get("full_text") or legacy.get("text") or "",
        "author": user.get("screen_name") or user.get("username") or "unknown",
        "created_at": _parse_time(created),
        "conversation_id": legacy.get("conversation_id_str") or legacy.get("conversation_id"),
        "media": _media_urls(legacy),
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


def _media_urls(legacy: dict) -> list[dict]:
    """[{url, is_video}] for each image/video on the tweet (best variant)."""
    entities = legacy.get("extended_entities") or legacy.get("entities") or {}
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


async def _archive_media(owner_user_id: UUID, tweet_id: str, media: list[dict]) -> list[dict]:
    """Download each image/video and store it; returns [{storage_key, content_type}]."""
    stored: list[dict] = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for i, item in enumerate(media):
            response = await client.get(item["url"])
            response.raise_for_status()
            content = response.content
            if len(content) > MAX_MEDIA_BYTES:
                continue  # skip an oversized blob rather than fail the whole save
            content_type = response.headers.get(
                "content-type", "video/mp4" if item["is_video"] else "image/jpeg"
            )
            ext = "mp4" if item["is_video"] else "jpg"
            key = await storage_service.upload_file(
                str(owner_user_id), f"x-{tweet_id}-{i}.{ext}", content, content_type
            )
            stored.append({"storage_key": key, "content_type": content_type})
    return stored
