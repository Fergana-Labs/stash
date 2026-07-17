"""X (Twitter) saves: OAuth bookmarks + twitterapi.io hydration.

X connects over OAuth. Each sync the indexer pulls bookmark ids from the X API
(with the OAuth token) and the user's own posts/replies from twitterapi.io by
account id, then hydrates every tweet the same way — full text, reply thread
root, archived media. Bookmarks sit behind a paid X API tier, so a 402/403 is
best-effort (logged, never fatal) and must not stop posts/replies.
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
        ]
    },
    "has_next_page": False,
}
_BOOKMARKS = {"data": [{"id": "900"}, {"id": "901"}], "meta": {}}


class _FakeResponse:
    def __init__(self, payload=None, content=b"", content_type="image/jpeg", status_code=200):
        self._payload = payload
        self.content = content
        self.headers = {"content-type": content_type}
        self.status_code = status_code

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


class _FakeApi:
    """One fake for every HTTP the indexer makes: twitterapi.io tweet-by-id +
    user-timeline, the X API bookmarks endpoint, and the CDN media URL."""

    bookmarks_status = 200

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
            return _FakeResponse(payload=_TIMELINE)
        if url.startswith("https://api.x.com/2/users/") and url.endswith("/bookmarks"):
            if type(self).bookmarks_status != 200:
                return _FakeResponse(payload={}, status_code=type(self).bookmarks_status)
            return _FakeResponse(payload=_BOOKMARKS)
        if url == "https://cdn.x/img.jpg":
            return _FakeResponse(content=b"fake image bytes")
        raise AssertionError(f"unexpected URL {url}")


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
    # bookmarks (900/901) from the X API + own post/reply (200/201) from the
    # timeline; the retweet (202) is skipped. All hydrated in this one pass.
    assert got == [
        ("200", "Post", "done"),
        ("201", "Reply", "done"),
        ("900", "Bookmark", "done"),
        ("901", "Bookmark", "done"),
    ]


@pytest.mark.asyncio
async def test_bookmarks_paid_tier_gate_is_best_effort(client, pool, fake_sync) -> None:
    # A 403 on the bookmarks endpoint (paid X tier) must not stop the user's
    # own posts/replies from syncing.
    _FakeApi.bookmarks_status = 403
    headers, owner_id = await _register(client)
    source = await _x_source(pool, owner_id, x_user_id="999")

    await x_indexer.index_x_saves(source)

    kinds = await pool.fetch(
        "SELECT DISTINCT kind FROM x_save_docs WHERE source_id = $1 ORDER BY kind",
        UUID(source["id"]),
    )
    assert [k["kind"] for k in kinds] == ["Post", "Reply"]  # no bookmarks, but posts/replies landed
