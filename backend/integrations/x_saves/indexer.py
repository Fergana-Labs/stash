"""Hydrate X (Twitter) saves via twitterapi.io.

Each sync enqueues skeleton rows (tweet ids + a kind): Bookmarks from the X
API with the OAuth token, the user's own Posts/Replies/Articles from
twitterapi.io by account id. A bounded hydration batch then fills them in:
the full tweet text + author (or, for an Article, the full long-form body)
from twitterapi.io, the author's whole thread + the reply's direct parent
for context, and the tweet's images/video archived into object storage — so
the save survives the tweet being deleted or the account going private.
Per-item failures land on the row, loudly; rows are never deleted by sync
(archive semantics).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx

from ...config import settings
from ...database import get_pool
from ...integrations import storage as integration_storage
from ...services import source_service, storage_service

logger = logging.getLogger(__name__)

TAPI_TWEETS_URL = "https://api.twitterapi.io/twitter/tweets"
TAPI_USER_TWEETS_URL = "https://api.twitterapi.io/twitter/user/last_tweets"
TAPI_ARTICLE_URL = "https://api.twitterapi.io/twitter/article"
TAPI_THREAD_URL = "https://api.twitterapi.io/twitter/tweet/thread_context"
X_BOOKMARKS_URL = "https://api.x.com/2/users/{user_id}/bookmarks"
TAPI_TIMEOUT = 60
MAX_MEDIA_BYTES = 100 * 1024 * 1024
MAX_MEDIA_PER_TWEET = 4
# Thread context pages fetched per save. A page carries the ancestors plus a
# slice of the replies; on a viral tweet the author's own continuation sits
# early, so a small cap finds real self-threads without walking whole reply
# storms.
MAX_THREAD_PAGES = 3
# Media archived per save across the whole thread (the saved tweet's own
# media is archived first and can never be squeezed out by thread posts).
MAX_MEDIA_PER_SAVE = 12
# Hydration is per-tweet (each commits on its own), and a sync can be killed
# mid-run by a worker redeploy — so keep the batch small enough that a sync
# usually finishes before that happens; the reconciler re-runs for the rest.
HYDRATION_BATCH = 50
MAX_HYDRATION_ATTEMPTS = 3
# Pages of the user's own timeline pulled from the top each sync (20/page),
# catching activity since the last sync. Stops early once a page brings
# nothing new; the page cap bounds a burst.
MAX_USER_TWEET_PAGES = 5
# Pages per sync spent walking the rest of the timeline history. The walk
# resumes from a cursor stored in source settings and runs until the entire
# reachable timeline has been ingested once (x_timeline_complete).
MAX_TIMELINE_BACKFILL_PAGES = 25
# The X API bills per post returned (unlike twitterapi.io, which is cheap),
# and most checks find no new bookmark — so bookmarks are checked at most
# once a day, starting with one small probe page. Backlog and history pages
# use the full size, capped per check. Posts/replies/articles are unaffected:
# they ride twitterapi.io on the source's normal sync cadence.
BOOKMARK_CHECK_INTERVAL = timedelta(days=1)
BOOKMARK_PROBE_SIZE = 10
BOOKMARK_PAGE_SIZE = 100
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
            await _backfill_bookmarks(
                source_id, owner_user_id, str(x_user_id), source.get("settings") or {}
            )
            await _backfill_user_tweets(
                client, source_id, owner_user_id, str(x_user_id), source.get("settings") or {}
            )

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


async def _backfill_bookmarks(
    source_id: UUID, owner_user_id: UUID, x_user_id: str, source_settings: dict
) -> None:
    """Insert pending Bookmark rows from the X API (OAuth token). Runs at most
    once a day (x_bookmarks_checked_at) — every returned post costs paid X API
    credits. Best-effort: the endpoint sits behind those paid credits, so a
    402/403/429 is expected and surfaced as a warning rather than fatal — it
    must not stop the user's posts/replies/articles from syncing.

    Same two passes as the timeline, both idempotent per tweet:
    - a probe pass from the top (small first page — most syncs find nothing
      new) that stops once a page brings nothing new;
    - a history walk that resumes from a pagination token stored in source
      settings until the whole reachable list has been ingested once
      (x_bookmarks_complete)."""
    checked_at = source_settings.get("x_bookmarks_checked_at")
    if checked_at and datetime.fromisoformat(checked_at) > datetime.now(UTC) - (
        BOOKMARK_CHECK_INTERVAL
    ):
        return
    await _merge_source_settings(
        source_id, {"x_bookmarks_checked_at": datetime.now(UTC).isoformat()}
    )

    token = await integration_storage.get_valid_token(owner_user_id, "x")
    async with httpx.AsyncClient(
        timeout=30.0, headers={"Authorization": f"Bearer {token}"}
    ) as client:
        page_token: str | None = None
        for page in range(MAX_BOOKMARK_PAGES):
            size = BOOKMARK_PROBE_SIZE if page == 0 else BOOKMARK_PAGE_SIZE
            payload = await _fetch_bookmarks_page(client, source_id, x_user_id, size, page_token)
            if payload is None:
                return
            inserted, considered = await _insert_bookmarks_page(payload, source_id, owner_user_id)
            page_token = (payload.get("meta") or {}).get("next_token")
            # Bookmarks come newest-first, so a page of already-known ids
            # means everything below is known too (history is the walk's job).
            if (considered and not inserted) or not page_token:
                break

        if source_settings.get("x_bookmarks_complete"):
            return
        page_token = source_settings.get("x_bookmarks_cursor")
        for _ in range(MAX_BOOKMARK_PAGES):
            payload = await _fetch_bookmarks_page(
                client, source_id, x_user_id, BOOKMARK_PAGE_SIZE, page_token
            )
            if payload is None:
                return
            await _insert_bookmarks_page(payload, source_id, owner_user_id)
            page_token = (payload.get("meta") or {}).get("next_token")
            if not page_token:
                await _merge_source_settings(source_id, {"x_bookmarks_complete": True})
                return
        await _merge_source_settings(source_id, {"x_bookmarks_cursor": page_token})


async def _fetch_bookmarks_page(
    client: httpx.AsyncClient,
    source_id: UUID,
    x_user_id: str,
    max_results: int,
    page_token: str | None,
) -> dict | None:
    """One page of the user's bookmarks, or None when the paid-credits gate
    (401/402/403/429) is closed — logged and surfaced on the source."""
    params: dict = {"max_results": max_results}
    if page_token:
        params["pagination_token"] = page_token
    response = await client.get(X_BOOKMARKS_URL.format(user_id=x_user_id), params=params)
    if response.status_code in (401, 402, 403, 429):
        # The body carries X's actual reason (e.g. UsageCapExceeded vs no
        # enrolled credits) — the status alone can't distinguish.
        logger.warning(
            "x bookmarks unavailable status=%s (X API tier/quota) source=%s body=%s",
            response.status_code,
            source_id,
            response.text[:300],
        )
        await source_service.set_sync_warning(
            source_id,
            f"X bookmarks are unavailable (HTTP {response.status_code}): the X API "
            "bookmarks endpoint needs a paid tier with remaining monthly quota. "
            "Posts, replies, and articles still sync.",
        )
        return None
    response.raise_for_status()
    return response.json()


async def _insert_bookmarks_page(
    payload: dict, source_id: UUID, owner_user_id: UUID
) -> tuple[int, int]:
    """Insert a skeleton Bookmark row per tweet on the page; returns (newly
    inserted, total considered)."""
    pool = get_pool()
    inserted = 0
    considered = 0
    for tweet in payload.get("data") or []:
        tweet_id = tweet.get("id")
        if not tweet_id:
            continue
        considered += 1
        status = await pool.execute(
            "INSERT INTO x_save_docs "
            "(owner_user_id, source_id, path, name, kind, external_ref) "
            "VALUES ($1, $2, $3, $4, 'Bookmark', $4) "
            "ON CONFLICT (source_id, path) DO NOTHING",
            owner_user_id,
            source_id,
            save_path("Bookmark", tweet_id),
            tweet_id,
        )
        if status == "INSERT 0 1":
            inserted += 1
    return inserted, considered


async def _backfill_user_tweets(
    client: httpx.AsyncClient,
    source_id: UUID,
    owner_user_id: UUID,
    x_user_id: str,
    source_settings: dict,
) -> None:
    """Insert pending rows for the user's own posts + replies + articles (from
    their timeline), which then hydrate through the same path as bookmarks.
    Two passes, both idempotent per tweet:
    - a fresh pass from the top of the timeline that stops once a page brings
      nothing new, catching activity since the last sync;
    - a history walk that resumes from a cursor stored in source settings, a
      bounded number of pages per sync, until the whole reachable timeline has
      been ingested once — then never runs again (x_timeline_complete)."""
    cursor: str | None = None
    for _ in range(MAX_USER_TWEET_PAGES):
        payload = await _fetch_timeline_page(client, x_user_id, cursor)
        inserted, considered = await _insert_timeline_page(payload, source_id, owner_user_id)
        cursor = payload.get("next_cursor")
        # A page of already-known tweets means we've reached familiar
        # territory. An all-retweet page proves nothing — keep going.
        if (considered and not inserted) or not payload.get("has_next_page") or not cursor:
            break

    if source_settings.get("x_timeline_complete"):
        return
    cursor = source_settings.get("x_timeline_cursor")
    for _ in range(MAX_TIMELINE_BACKFILL_PAGES):
        payload = await _fetch_timeline_page(client, x_user_id, cursor)
        await _insert_timeline_page(payload, source_id, owner_user_id)
        cursor = payload.get("next_cursor")
        if not payload.get("has_next_page") or not cursor:
            await _merge_source_settings(source_id, {"x_timeline_complete": True})
            return
    await _merge_source_settings(source_id, {"x_timeline_cursor": cursor})


async def _fetch_timeline_page(
    client: httpx.AsyncClient, x_user_id: str, cursor: str | None
) -> dict:
    # `includeReplies` is required: twitterapi.io omits replies from
    # last_tweets by default.
    params = {"userId": x_user_id, "includeReplies": "true"}
    if cursor:
        params["cursor"] = cursor
    response = await client.get(TAPI_USER_TWEETS_URL, params=params)
    response.raise_for_status()
    return response.json()


async def _insert_timeline_page(
    payload: dict, source_id: UUID, owner_user_id: UUID
) -> tuple[int, int]:
    """Insert a skeleton row per tweet on the page; returns (newly inserted,
    total considered). Retweets are skipped — they aren't the user's own
    writing — and don't count as considered."""
    pool = get_pool()
    inserted = 0
    considered = 0
    for tweet in (payload.get("data") or {}).get("tweets") or []:
        tweet_id = tweet.get("id")
        if not tweet_id or tweet.get("isRetweet"):
            continue
        considered += 1
        if tweet.get("article"):
            kind = "Article"
            # Articles synced before article detection existed landed as
            # Posts; drop the stale row so the save doesn't appear twice.
            await pool.execute(
                "DELETE FROM x_save_docs WHERE source_id = $1 AND path = $2",
                source_id,
                save_path("Post", tweet_id),
            )
        elif tweet.get("isReply"):
            kind = "Reply"
        else:
            kind = "Post"
        status = await pool.execute(
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
        if status == "INSERT 0 1":
            inserted += 1
    return inserted, considered


async def _merge_source_settings(source_id: UUID, patch: dict) -> None:
    await get_pool().execute(
        "UPDATE user_sources SET settings = coalesce(settings, '{}'::jsonb) || $2::jsonb, "
        "updated_at = now() WHERE id = $1",
        source_id,
        patch,
    )


async def _hydrate_one(
    client: httpx.AsyncClient,
    source_id: UUID,
    owner_user_id: UUID,
    path: str,
    kind: str,
) -> None:
    tweet_id = _tweet_id_from_path(path)
    if kind == "Article":
        await _hydrate_article(client, source_id, owner_user_id, path)
        return
    tweet = await _fetch_tweet(client, tweet_id)

    # A saved tweet is often one post of a thread: pull the conversation and
    # keep the author's whole chain, plus the direct parent when the save is
    # a reply to someone else. Best-effort — the save itself matters.
    thread = [tweet]
    parent = None
    if _in_conversation(tweet):
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

    media = await _archive_thread_media(owner_user_id, tweet, thread)

    content = _render(tweet, thread, parent)
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


async def _hydrate_article(
    client: httpx.AsyncClient, source_id: UUID, owner_user_id: UUID, path: str
) -> None:
    """Articles are long-form X posts. The regular tweet lookup only carries a
    title + preview, so the full body comes from twitterapi.io's article
    endpoint; the cover image and any body images are archived like tweet
    media."""
    tweet_id = _tweet_id_from_path(path)
    response = await client.get(TAPI_ARTICLE_URL, params={"tweet_id": tweet_id})
    response.raise_for_status()
    payload = response.json()
    article = payload.get("article") or {}
    if payload.get("status") != "success" or not article.get("title"):
        raise RuntimeError(f"article {tweet_id} is unavailable (deleted, private, or suspended)")

    author = (article.get("author") or {}).get("userName") or "unknown"
    posted = _parse_time(article.get("createdAt"))
    media = await _archive_media(owner_user_id, tweet_id, _article_media(article))

    byline = f"— @{author}"
    if posted:
        byline += f" · {posted.date().isoformat()}"
    content = "\n".join(
        [
            article["title"],
            "",
            _render_article_blocks(article.get("contents") or []),
            "",
            byline,
            tweet_url(tweet_id),
        ]
    )
    await source_service.upsert_content_document(
        table="x_save_docs",
        source_id=source_id,
        owner_user_id=owner_user_id,
        path=path,
        name=article["title"],
        kind="Article",
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
            # Best-effort, like the saves indexer — the tweet itself matters.
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


# Draft.js-style block types twitterapi.io uses for article bodies.
_ARTICLE_HEADINGS = {"header-one": "# ", "header-two": "## ", "header-three": "### "}
_ARTICLE_LIST_ITEMS = ("unordered-list-item", "ordered-list-item")


def _render_article_blocks(blocks: list[dict]) -> str:
    lines: list[str] = []
    for block in blocks:
        block_type = block.get("type") or ""
        text = (block.get("text") or "").strip()
        if block_type in _ARTICLE_HEADINGS and text:
            lines.append(_ARTICLE_HEADINGS[block_type] + text)
        elif block_type in _ARTICLE_LIST_ITEMS and text:
            lines.append("- " + text)
        elif block_type == "divider":
            lines.append("---")
        elif text:
            lines.append(text)
    return "\n\n".join(lines)


def _article_media(article: dict) -> list[dict]:
    """Cover image + any image/gif blocks in the body, in _archive_media shape."""
    urls: list[str] = []
    if article.get("cover_media_img_url"):
        urls.append(article["cover_media_img_url"])
    for block in article.get("contents") or []:
        if block.get("type") in ("image", "gif") and block.get("url"):
            urls.append(block["url"])
    return [{"url": u, "is_video": False} for u in urls]


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


async def _archive_thread_media(owner_user_id: UUID, tweet: dict, thread: list[dict]) -> list[dict]:
    """Archive the saved tweet's media first, then the rest of the thread's,
    up to MAX_MEDIA_PER_SAVE total."""
    stored: list[dict] = []
    ordered = [tweet] + [t for t in thread if t["id"] != tweet["id"]]
    for t in ordered:
        room = MAX_MEDIA_PER_SAVE - len(stored)
        if room <= 0:
            break
        if t["media"]:
            stored.extend(await _archive_media(owner_user_id, t["id"], t["media"][:room]))
    return stored


def _render(tweet: dict, thread: list[dict], parent: dict | None) -> str:
    # Tweet text first so the listing's preview (first paragraph of content) is
    # the tweet itself, not metadata. Everything after the blank line is the
    # byline, reply context, thread, and link.
    parts: list[str] = [tweet["text"] or "", ""]
    byline = f"— @{tweet['author']}"
    if tweet["created_at"]:
        byline += f" · {tweet['created_at'].date().isoformat()}"
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
