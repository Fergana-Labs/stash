"""X (Twitter) saves: OAuth bookmarks + twitterapi.io hydration.

X connects over OAuth. Each sync the indexer pulls bookmark ids from the X API
(with the OAuth token) and the user's own posts/replies/articles from
twitterapi.io by account id, then hydrates every tweet the same way — full
text (long-form body for articles), reply thread root, archived media.
Bookmarks sit behind a paid X API tier, so a 402/403 is best-effort (an
owner-facing warning, never fatal) and must not stop posts/replies/articles.
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.integrations import storage as integration_storage
from backend.integrations.x_saves import indexer as x_indexer
from backend.services import source_service, storage_service

from .conftest import unique_name

# twitterapi.io tweet shape (native Twitter media under extendedEntities); a
# reply carries conversationId = the thread root's id.
_REPLY = {
    "id": "1001",
    "text": "totally agree with this",
    "author": {"userName": "alice", "name": "Alice"},
    "createdAt": "Wed Jul 01 12:00:00 +0000 2025",
    "conversationId": "1000",
    "extendedEntities": {"media": [{"type": "photo", "media_url_https": "https://cdn.x/img.jpg"}]},
}
_ROOT = {
    "id": "1000",
    "text": "here is a hot take",
    "author": {"userName": "bob", "name": "Bob"},
    "createdAt": "Wed Jul 01 11:00:00 +0000 2025",
    "conversationId": "1000",
}
_TIMELINE = {
    "data": {
        "tweets": [
            {"id": "200", "isReply": False, "isRetweet": False},
            {"id": "201", "isReply": True, "isRetweet": False},
            {"id": "202", "isReply": False, "isRetweet": True},  # retweet — skipped
            # An article tweet: last_tweets carries a stub `article` object;
            # the full body comes from the article endpoint at hydration.
            {
                "id": "203",
                "isReply": False,
                "isRetweet": False,
                "article": {"title": "On agents", "preview_text": "For years..."},
            },
        ]
    },
    "has_next_page": False,
}
_BOOKMARKS = {"data": [{"id": "900"}, {"id": "901"}], "meta": {}}
_ARTICLE = {
    "status": "success",
    "article": {
        "id": "203",
        "title": "On agents",
        "preview_text": "For years...",
        "cover_media_img_url": "https://cdn.x/img.jpg",
        "createdAt": "Sat Jul 18 22:20:40 +0000 2026",
        "author": {"userName": "me"},
        "contents": [
            {"type": "unstyled", "text": "For years, tech went one way."},
            {"type": "header-one", "text": "The shift"},
            {"type": "unordered-list-item", "text": "copy the crowd"},
            {"type": "divider"},
        ],
    },
}


class _FakeResponse:
    def __init__(self, payload=None, content=b"", content_type="image/jpeg", status_code=200):
        self._payload = payload
        self.content = content
        self.headers = {"content-type": content_type}
        self.status_code = status_code
        self.text = "{}"

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _generic_tweet(tweet_id: str) -> dict:
    return {
        "id": tweet_id,
        "text": f"tweet {tweet_id}",
        "author": {"userName": "me"},
        "createdAt": "Wed Jul 01 12:00:00 +0000 2025",
        "conversationId": tweet_id,
    }


class _FakeStreamResponse:
    """Streaming media response: the indexer must read it chunk-wise under a
    running byte cap, never `.content`-style all at once."""

    def __init__(self, content: bytes, headers: dict):
        self._content = content
        self.headers = headers
        self.reads = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    async def aiter_bytes(self, chunk_size):
        for i in range(0, len(self._content), chunk_size):
            self.reads += 1
            yield self._content[i : i + chunk_size]


class _FakeApi:
    """One fake for every HTTP the indexer makes: twitterapi.io tweet-by-id +
    user-timeline, the X API bookmarks endpoint, and the CDN media URL."""

    media_bytes = b"fake image bytes"
    media_headers = {"content-type": "image/jpeg"}
    media_streams: list = []

    bookmarks_status = 200
    # cursor/token (None = first page) -> payload; overridable per test.
    timeline_pages: dict = {}
    bookmarks_pages: dict = {}

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        if url == x_indexer.TAPI_TWEETS_URL:
            tid = params["tweet_ids"]
            tweet = {"1001": _REPLY, "1000": _ROOT}.get(tid) or _generic_tweet(tid)
            return _FakeResponse(payload={"tweets": [tweet]})
        if url == x_indexer.TAPI_USER_TWEETS_URL:
            # Replies must be requested explicitly; twitterapi.io omits them
            # from last_tweets by default.
            assert params.get("includeReplies") == "true"
            return _FakeResponse(payload=type(self).timeline_pages[params.get("cursor")])
        if url == x_indexer.TAPI_ARTICLE_URL:
            assert params == {"tweet_id": "203"}
            return _FakeResponse(payload=_ARTICLE)
        if url.startswith("https://api.x.com/2/users/") and url.endswith("/bookmarks"):
            if type(self).bookmarks_status != 200:
                return _FakeResponse(payload={}, status_code=type(self).bookmarks_status)
            return _FakeResponse(payload=type(self).bookmarks_pages[params.get("pagination_token")])
        raise AssertionError(f"unexpected URL {url}")

    def stream(self, method, url):
        assert url == "https://cdn.x/img.jpg", f"unexpected media URL {url}"
        response = _FakeStreamResponse(type(self).media_bytes, dict(type(self).media_headers))
        type(self).media_streams.append(response)
        return response


@pytest.fixture
def fake_sync(monkeypatch):
    uploads: list[tuple[str, str]] = []

    async def _upload(owner, filename, content, content_type):
        uploads.append((filename, content_type))
        return f"store/{filename}"

    async def _url(key):
        return f"https://blob.example/{key}"

    async def _token(user_id, provider, account_key=None):
        return "oauth-token"

    _FakeApi.bookmarks_status = 200
    _FakeApi.bookmarks_pages = {None: _BOOKMARKS}
    _FakeApi.timeline_pages = {None: _TIMELINE}
    _FakeApi.media_bytes = b"fake image bytes"
    _FakeApi.media_headers = {"content-type": "image/jpeg"}
    _FakeApi.media_streams = []
    monkeypatch.setattr(settings, "TWITTERAPI_IO_KEY", "tapi-key")
    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(integration_storage, "get_valid_token", _token)
    monkeypatch.setattr(x_indexer, "httpx", SimpleNamespace(AsyncClient=_FakeApi))
    return uploads


async def _register(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["id"]


async def _x_source(pool, owner_id: str, x_user_id: str | None = None) -> dict:
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="x_saves",
        external_ref=x_user_id or "me",
        display_name="X",
        settings={},
    )
    if x_user_id:
        await pool.execute(
            "UPDATE user_sources SET settings = coalesce(settings, '{}'::jsonb) || $2::jsonb "
            "WHERE id = $1",
            UUID(source["id"]),
            {"x_user_id": x_user_id},
        )
    return await source_service.get_source_for_sync(UUID(source["id"]))


async def _insert_pending(pool, owner_id, source_id, path, kind):
    await pool.execute(
        "INSERT INTO x_save_docs (owner_user_id, source_id, path, name, kind, external_ref) "
        "VALUES ($1, $2, $3, $3, $4, $3)",
        UUID(owner_id),
        UUID(source_id),
        path,
        kind,
    )


@pytest.mark.asyncio
async def test_hydrates_content_thread_root_and_media(client, pool, fake_sync) -> None:
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id)  # no x_user_id -> no backfills, just hydrate
    await _insert_pending(pool, owner_id, source["id"], "1001", "Bookmark")

    await x_indexer.index_x_saves(source)

    row = await pool.fetchrow("SELECT * FROM x_save_docs WHERE source_id = $1", UUID(source["id"]))
    assert row["hydration_status"] == "done"
    assert row["name"] == "@alice - 2025-07-01"
    assert "totally agree with this" in row["content"]
    assert "In reply to @bob" in row["content"]  # thread root kept for context
    assert "here is a hot take" in row["content"]
    assert row["media"] == [{"storage_key": "store/x-1001-0.jpg", "content_type": "image/jpeg"}]
    assert fake_sync == [("x-1001-0.jpg", "image/jpeg")]

    ok, doc = await source_service.source_document(
        UUID(owner_id), UUID(owner_id), str(source["id"]), "1001"
    )
    assert ok
    assert doc["url"] == "https://x.com/i/status/1001"
    assert doc["media"] == [
        {"url": "https://blob.example/store/x-1001-0.jpg", "content_type": "image/jpeg"}
    ]

    # The browse list previews the tweet text (not the raw id).
    entries = await source_service.source_entries(UUID(owner_id), UUID(owner_id), str(source["id"]))
    entry = next(e for e in entries if e["path"] == "1001")
    assert entry["snippet"] == "totally agree with this"


@pytest.mark.asyncio
async def test_media_over_cap_is_skipped_while_streaming(
    client, pool, fake_sync, monkeypatch
) -> None:
    # The cap must abort the download mid-stream. The old code buffered the
    # whole highest-bitrate video into memory before measuring it, which
    # spiked the worker past its 2GB limit and OOM-killed the box.
    monkeypatch.setattr(x_indexer, "MAX_MEDIA_BYTES", 100)
    _FakeApi.media_bytes = b"x" * 100_000  # over the cap; no content-length header
    _FakeApi.media_headers = {"content-type": "video/mp4"}
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id)
    await _insert_pending(pool, owner_id, source["id"], "1001", "Bookmark")

    await x_indexer.index_x_saves(source)

    row = await pool.fetchrow("SELECT * FROM x_save_docs WHERE source_id = $1", UUID(source["id"]))
    assert row["hydration_status"] == "done"  # the save survives, minus the blob
    assert row["media"] == []
    assert fake_sync == []  # nothing uploaded
    # Aborted after the first over-cap chunk, not read to the end.
    assert _FakeApi.media_streams[0].reads == 1


@pytest.mark.asyncio
async def test_media_with_oversized_content_length_is_never_read(
    client, pool, fake_sync, monkeypatch
) -> None:
    # When the CDN declares the size up front, skip without reading any body.
    monkeypatch.setattr(x_indexer, "MAX_MEDIA_BYTES", 100)
    _FakeApi.media_headers = {"content-type": "video/mp4", "content-length": "500000000"}
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id)
    await _insert_pending(pool, owner_id, source["id"], "1001", "Bookmark")

    await x_indexer.index_x_saves(source)

    row = await pool.fetchrow("SELECT * FROM x_save_docs WHERE source_id = $1", UUID(source["id"]))
    assert row["hydration_status"] == "done"
    assert row["media"] == []
    assert fake_sync == []
    assert _FakeApi.media_streams[0].reads == 0


@pytest.mark.asyncio
async def test_hydration_failure_lands_on_the_row(client, pool, fake_sync, monkeypatch) -> None:
    async def boom(client_, tweet_id):
        raise ValueError("twitterapi exploded")

    monkeypatch.setattr(x_indexer, "_fetch_tweet", boom)
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id)
    await _insert_pending(pool, owner_id, source["id"], "1001", "Bookmark")

    await x_indexer.index_x_saves(source)

    row = await pool.fetchrow(
        "SELECT hydration_status, hydration_error, hydration_attempts "
        "FROM x_save_docs WHERE source_id = $1",
        UUID(source["id"]),
    )
    assert row["hydration_status"] == "failed"
    assert "twitterapi exploded" in row["hydration_error"]
    assert row["hydration_attempts"] == 1

    ok, doc = await source_service.source_document(
        UUID(owner_id), UUID(owner_id), str(source["id"]), "1001"
    )
    assert ok and doc["http_status"] == 422


@pytest.mark.asyncio
async def test_backfills_bookmarks_and_own_posts(client, pool, fake_sync) -> None:
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id, x_user_id="999")

    await x_indexer.index_x_saves(source)

    rows = await pool.fetch(
        "SELECT path, kind, hydration_status FROM x_save_docs WHERE source_id = $1 ORDER BY path",
        UUID(source["id"]),
    )
    got = [(r["path"], r["kind"], r["hydration_status"]) for r in rows]
    # bookmarks (900/901) from the X API + own post/reply/article (200/201/203)
    # from the timeline; the retweet (202) is skipped. Each lands under its
    # kind folder, all hydrated in this one pass.
    assert got == [
        ("Articles/203", "Article", "done"),
        ("Bookmarks/900", "Bookmark", "done"),
        ("Bookmarks/901", "Bookmark", "done"),
        ("Posts/200", "Post", "done"),
        ("Replies/201", "Reply", "done"),
    ]


@pytest.mark.asyncio
async def test_article_hydrates_full_body_with_title_name(client, pool, fake_sync) -> None:
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id, x_user_id="999")

    await x_indexer.index_x_saves(source)

    row = await pool.fetchrow(
        "SELECT * FROM x_save_docs WHERE source_id = $1 AND path = 'Articles/203'",
        UUID(source["id"]),
    )
    assert row["hydration_status"] == "done"
    assert row["name"] == "On agents"  # articles are named by title, not @author-date
    assert "For years, tech went one way." in row["content"]
    assert "# The shift" in row["content"]  # heading blocks render as markdown
    assert "- copy the crowd" in row["content"]
    assert "— @me · 2026-07-18" in row["content"]
    # The cover image is archived like tweet media.
    assert row["media"] == [{"storage_key": "store/x-203-0.jpg", "content_type": "image/jpeg"}]


@pytest.mark.asyncio
async def test_article_previously_synced_as_post_is_rekinded(client, pool, fake_sync) -> None:
    # Articles synced before article detection existed landed as Posts; the
    # backfill must replace that row, not duplicate the save under two folders.
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id, x_user_id="999")
    await _insert_pending(pool, owner_id, source["id"], "Posts/203", "Post")

    await x_indexer.index_x_saves(source)

    paths = [
        r["path"]
        for r in await pool.fetch(
            "SELECT path FROM x_save_docs WHERE source_id = $1 AND path LIKE '%/203'",
            UUID(source["id"]),
        )
    ]
    assert paths == ["Articles/203"]


@pytest.mark.asyncio
async def test_bookmark_backfill_stops_at_known_ids(client, pool, fake_sync) -> None:
    # Every bookmarks page read costs paid X API reads. Bookmarks come
    # newest-first, so once a page brings nothing new the rest of the list is
    # already saved — deeper pages must not be fetched.
    _FakeApi.bookmarks_pages = {
        None: {"data": [{"id": "900"}, {"id": "901"}], "meta": {"next_token": "b2"}},
        "b2": {"data": [{"id": "902"}], "meta": {}},
    }
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id, x_user_id="999")
    await _insert_pending(pool, owner_id, source["id"], "Bookmarks/900", "Bookmark")
    await _insert_pending(pool, owner_id, source["id"], "Bookmarks/901", "Bookmark")

    await x_indexer.index_x_saves(source)

    count = await pool.fetchval(
        "SELECT count(*) FROM x_save_docs WHERE source_id = $1 AND path = 'Bookmarks/902'",
        UUID(source["id"]),
    )
    assert count == 0  # page 2 was never fetched


@pytest.mark.asyncio
async def test_timeline_history_walk_resumes_across_syncs(
    client, pool, fake_sync, monkeypatch
) -> None:
    # The whole timeline must be ingested even when one sync's page budget
    # can't cover it: the walk parks its cursor in source settings, the next
    # sync resumes there, and once the end is reached the walk never runs
    # again.
    monkeypatch.setattr(x_indexer, "MAX_USER_TWEET_PAGES", 1)
    monkeypatch.setattr(x_indexer, "MAX_TIMELINE_BACKFILL_PAGES", 1)
    _FakeApi.timeline_pages = {
        None: {
            "data": {"tweets": [{"id": "300", "isReply": False, "isRetweet": False}]},
            "has_next_page": True,
            "next_cursor": "c2",
        },
        "c2": {
            "data": {"tweets": [{"id": "301", "isReply": True, "isRetweet": False}]},
            "has_next_page": False,
        },
    }
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id, x_user_id="999")

    await x_indexer.index_x_saves(source)

    # Sync 1: the fresh pass took page 1; the walk's budget ran out at c2.
    settings_ = await pool.fetchval(
        "SELECT settings FROM user_sources WHERE id = $1", UUID(source["id"])
    )
    assert settings_["x_timeline_cursor"] == "c2"
    assert "x_timeline_complete" not in settings_

    source = await source_service.get_source_for_sync(UUID(source["id"]))
    await x_indexer.index_x_saves(source)

    # Sync 2: the walk resumed at c2 and reached the end of the timeline.
    settings_ = await pool.fetchval(
        "SELECT settings FROM user_sources WHERE id = $1", UUID(source["id"])
    )
    assert settings_["x_timeline_complete"] is True
    paths = [
        r["path"]
        for r in await pool.fetch(
            "SELECT path FROM x_save_docs WHERE source_id = $1 AND kind != 'Bookmark' "
            "ORDER BY path",
            UUID(source["id"]),
        )
    ]
    assert paths == ["Posts/300", "Replies/301"]


@pytest.mark.asyncio
async def test_bookmarks_paid_tier_gate_is_best_effort(client, pool, fake_sync) -> None:
    # A 403 on the bookmarks endpoint (paid X tier) must not stop the user's
    # own posts/replies/articles from syncing — but the owner must be able to
    # see WHY bookmarks stopped, so it lands as a warning on the source.
    _FakeApi.bookmarks_status = 403
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id, x_user_id="999")

    await x_indexer.index_x_saves(source)

    kinds = await pool.fetch(
        "SELECT DISTINCT kind FROM x_save_docs WHERE source_id = $1 ORDER BY kind",
        UUID(source["id"]),
    )
    assert [k["kind"] for k in kinds] == ["Article", "Post", "Reply"]
    status = await pool.fetchrow(
        "SELECT sync_status, sync_error FROM user_sources WHERE id = $1", UUID(source["id"])
    )
    assert status["sync_status"] != "failed"
    assert "paid tier" in status["sync_error"]
