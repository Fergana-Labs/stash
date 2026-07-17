"""Hydrate X (Twitter) saves via twitterapi.io.

Skeleton rows arrive from the extension push (routers/sources.py
x_items_router) as tweet ids + a kind (Bookmark/Post/Reply/Article). Each
sync pass fills a bounded batch: the full tweet text + author from
twitterapi.io, the conversation root for reply context, and the tweet's
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
from ...integrations import storage as integration_storage
from ...services import source_service, storage_service

logger = logging.getLogger(__name__)

TAPI_TWEETS_URL = "https://api.twitterapi.io/twitter/tweets"
TAPI_USER_TWEETS_URL = "https://api.twitterapi.io/twitter/user/last_tweets"
X_BOOKMARKS_URL = "https://api.x.com/2/users/{user_id}/bookmarks"
TAPI_TIMEOUT = 60
MAX_MEDIA_BYTES = 100 * 1024 * 1024
MAX_MEDIA_PER_TWEET = 4
# Hydration is per-tweet (each commits on its own), and a sync can be killed
# mid-run by a worker redeploy — so keep the batch small enough that a sync
# usually finishes before that happens; the reconciler re-runs for the rest.
HYDRATION_BATCH = 50
MAX_HYDRATION_ATTEMPTS = 3
# Pages of the user's own timeline pulled per sync (20 tweets/page). Bounded so
# one sync doesn't run away; older tweets keep arriving over subsequent syncs.
MAX_USER_TWEET_PAGES = 5
# Pages of bookmarks pulled per sync (100/page via the X API).
MAX_BOOKMARK_PAGES = 5


def tweet_url(tweet_id: str) -> str:
    return f"https://x.com/i/status/{tweet_id}"


# Saves are foldered by kind in the VFS: path = "<Folder>/<tweet id>".
KIND_FOLDER = {"Bookmark": "Bookmarks", "Post": "Posts", "Reply": "Replies", "Article": "Articles"}


def save_path(kind: str, tweet_id: str) -> str:
    return f"{KIND_FOLDER.get(kind, 'Other')}/{tweet_id}"


def _tweet_id_from_path(path: str) -> str:
    return path.rsplit("/", 1)[-1]


async def index_x_saves(source: dict) -> str | None:
    if not settings.TWITTERAPI_IO_KEY:
        raise RuntimeError("TWITTERAPI_IO_KEY is not set")
    if not storage_service.is_configured():
        raise RuntimeError("File storage is not configured; cannot archive save media")

    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    pool = get_pool()
    x_user_id = (source.get("settings") or {}).get("x_user_id")

    async with httpx.AsyncClient(
        timeout=TAPI_TIMEOUT, headers={"X-API-Key": settings.TWITTERAPI_IO_KEY}
    ) as client:
        # Enqueue newly-saved ids first: bookmarks from the X API (OAuth token),
        # the user's own posts/replies from twitterapi.io. Both just insert
        # pending skeleton rows — the hydration pass below fills them in.
        if x_user_id:
            await _backfill_bookmarks(source_id, owner_user_id, str(x_user_id))
            await _backfill_user_tweets(client, source_id, owner_user_id, str(x_user_id))

        # Hydrate a bounded batch of pending rows. Bounding the batch is what
        # lets a stuck account keep making progress across syncs even when the
        # worker is under load — each sync clears HYDRATION_BATCH more.
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


async def _backfill_bookmarks(source_id: UUID, owner_user_id: UUID, x_user_id: str) -> None:
    """Insert pending Bookmark rows from the X API (OAuth token). Best-effort:
    the bookmarks endpoint sits behind a paid X API tier, so a 402/403/429 is
    expected and logged rather than fatal — it must not stop the user's
    posts/replies from syncing. Idempotent per tweet."""
    token = await integration_storage.get_valid_token(owner_user_id, "x")
    pool = get_pool()
    next_token: str | None = None
    async with httpx.AsyncClient(
        timeout=30.0, headers={"Authorization": f"Bearer {token}"}
    ) as client:
        for _ in range(MAX_BOOKMARK_PAGES):
            params = {"max_results": 100}
            if next_token:
                params["pagination_token"] = next_token
            response = await client.get(X_BOOKMARKS_URL.format(user_id=x_user_id), params=params)
            if response.status_code in (401, 402, 403, 429):
                logger.warning(
                    "x bookmarks unavailable status=%s (X API tier/quota) source=%s",
                    response.status_code,
                    source_id,
                )
                return
            response.raise_for_status()
            payload = response.json()
            for tweet in payload.get("data") or []:
                tweet_id = tweet.get("id")
                if not tweet_id:
                    continue
                await pool.execute(
                    "INSERT INTO x_save_docs "
                    "(owner_user_id, source_id, path, name, kind, external_ref) "
                    "VALUES ($1, $2, $3, $4, 'Bookmark', $4) "
                    "ON CONFLICT (source_id, path) DO NOTHING",
                    owner_user_id,
                    source_id,
                    save_path("Bookmark", tweet_id),
                    tweet_id,
                )
            next_token = (payload.get("meta") or {}).get("next_token")
            if not next_token:
                break


async def _backfill_user_tweets(
    client: httpx.AsyncClient, source_id: UUID, owner_user_id: UUID, x_user_id: str
) -> None:
    """Insert pending rows for the user's own posts + replies (from their
    timeline), which then hydrate through the same path as bookmarks. Retweets
    are skipped — they aren't the user's own writing. Idempotent per tweet."""
    pool = get_pool()
    cursor: str | None = None
    for _ in range(MAX_USER_TWEET_PAGES):
        params = {"userId": x_user_id}
        if cursor:
            params["cursor"] = cursor
        response = await client.get(TAPI_USER_TWEETS_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        tweets = (payload.get("data") or {}).get("tweets") or []
        for tweet in tweets:
            tweet_id = tweet.get("id")
            if not tweet_id or tweet.get("isRetweet"):
                continue
            kind = "Reply" if tweet.get("isReply") else "Post"
            await pool.execute(
                "INSERT INTO x_save_docs "
                "(owner_user_id, source_id, path, name, kind, external_ref) "
                "VALUES ($1, $2, $3, $4, $5, $4) "
                "ON CONFLICT (source_id, path) DO NOTHING",
                owner_user_id,
                source_id,
                save_path(kind, tweet_id),
                tweet_id,
                kind,
            )
        if not payload.get("has_next_page"):
            break
        cursor = payload.get("next_cursor")
        if not cursor:
            break


async def _hydrate_one(
    client: httpx.AsyncClient,
    source_id: UUID,
    owner_user_id: UUID,
    path: str,
    kind: str,
) -> None:
    tweet_id = _tweet_id_from_path(path)
    tweet = await _fetch_tweet(client, tweet_id)

    # A reply shows only its own text out of context, so pull the root of the
    # conversation and keep it as "In reply to:" above the reply.
    root = None
    root_id = tweet.get("conversation_id")
    if root_id and root_id != tweet_id:
        try:
            root = await _fetch_tweet(client, root_id)
        except Exception:
            root = None  # thread context is best-effort; the reply itself matters

    media = await _archive_media(owner_user_id, tweet_id, tweet["media"])

    content = _render(tweet, root)
    posted = tweet["created_at"]
    await source_service.upsert_content_document(
        table="x_save_docs",
        source_id=source_id,
        owner_user_id=owner_user_id,
        path=path,
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
        path,
        media,
    )


def _render(tweet: dict, root: dict | None) -> str:
    # Tweet text first so the listing's preview (first paragraph of content) is
    # the tweet itself, not metadata. Everything after the blank line is the
    # byline, reply context, and link.
    parts: list[str] = [tweet["text"] or "", ""]
    byline = f"— @{tweet['author']}"
    if tweet["created_at"]:
        byline += f" · {tweet['created_at'].date().isoformat()}"
    parts.append(byline)
    if root is not None:
        parts.append(f"In reply to @{root['author']}: {root['text']}")
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


async def _archive_media(owner_user_id: UUID, tweet_id: str, media: list[dict]) -> list[dict]:
    """Download each image/video and store it; returns [{storage_key, content_type}]."""
    stored: list[dict] = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for i, item in enumerate(media):
            async with client.stream("GET", item["url"]) as response:
                response.raise_for_status()
                # The cap must hold WHILE downloading. The old code buffered
                # the whole highest-bitrate video into memory just to measure
                # it — a long 1080p MP4 is hundreds of MB, which spiked the
                # celery worker past its 2GB limit in seconds and OOM-killed
                # the box mid-hydration.
                declared = response.headers.get("content-length")
                if declared is not None and int(declared) > MAX_MEDIA_BYTES:
                    continue  # skip an oversized blob rather than fail the whole save
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(64 * 1024):
                    total += len(chunk)
                    if total > MAX_MEDIA_BYTES:
                        break
                    chunks.append(chunk)
                if total > MAX_MEDIA_BYTES:
                    continue  # skip an oversized blob rather than fail the whole save
                content = b"".join(chunks)
                content_type = response.headers.get(
                    "content-type", "video/mp4" if item["is_video"] else "image/jpeg"
                )
                ext = "mp4" if item["is_video"] else "jpg"
                key = await storage_service.upload_file(
                    str(owner_user_id), f"x-{tweet_id}-{i}.{ext}", content, content_type
                )
                stored.append({"storage_key": key, "content_type": content_type})
    return stored
