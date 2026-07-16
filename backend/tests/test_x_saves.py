"""X (Twitter) saves: extension push + twitterapi.io hydration.

The push endpoint get-or-creates the source, parses tweet ids from links
loudly, and dedupes. The indexer hydrates the full text from the link, pulls
the conversation root so a reply reads in context, archives the tweet's
images/video (the point is surviving deletion), records per-item failures on
the row, and never deletes rows.
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.integrations.x_saves import indexer as x_indexer
from backend.services import source_service, storage_service

from .conftest import unique_name

# twitterapi.io returns tweets in the native Twitter media shape under
# extendedEntities; a reply carries conversationId = the thread root's id.
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


class _FakeResponse:
    def __init__(self, payload=None, content=b"", content_type="image/jpeg"):
        self._payload = payload
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeTwitterApi:
    """Answers the twitterapi.io tweets endpoint (keyed by ?tweet_ids=) and the
    CDN media URL for _archive_media's separate client."""

    media_bytes = b"fake image bytes"

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        if url == x_indexer.TAPI_TWEETS_URL:
            tweet = _REPLY if params["tweet_ids"] == "1001" else _ROOT
            return _FakeResponse(payload={"tweets": [tweet], "status": "success"})
        if url == "https://cdn.x/img.jpg":
            return _FakeResponse(content=type(self).media_bytes)
        raise AssertionError(f"unexpected URL {url}")


@pytest.fixture
def fake_hydration(monkeypatch):
    uploads: list[tuple[str, str]] = []

    async def _upload(owner, filename, content, content_type):
        uploads.append((filename, content_type))
        return f"store/{filename}"

    async def _url(key):
        return f"https://blob.example/{key}"

    monkeypatch.setattr(settings, "TWITTERAPI_IO_KEY", "tapi-key")
    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(x_indexer, "httpx", SimpleNamespace(AsyncClient=_FakeTwitterApi))
    return uploads


async def _register(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["id"]


def _push_body(items: list[dict]) -> dict:
    return {"items": items}


@pytest.mark.asyncio
async def test_push_creates_source_and_skeleton_rows(
    client: AsyncClient, pool, monkeypatch
) -> None:
    sent: list = []
    from backend.routers import sources as sources_router

    monkeypatch.setattr(settings, "TWITTERAPI_IO_KEY", "tapi-key")
    monkeypatch.setattr(
        sources_router.celery, "send_task", lambda name, args: sent.append((name, args))
    )
    headers, owner_id = await _register(client)

    resp = await client.post(
        "/api/v1/me/x-items",
        json=_push_body(
            [
                {"url": "https://x.com/alice/status/1001", "kind": "Reply"},
                {"url": "https://twitter.com/bob/status/1000", "kind": "Bookmark"},
            ]
        ),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"accepted": 2, "new": 2, "existing": 0}
    assert sent and sent[0][0] == "backend.tasks.sources.sync_source"

    rows = await pool.fetch(
        "SELECT path, kind, hydration_status FROM x_save_docs WHERE owner_user_id = $1 "
        "ORDER BY path",
        UUID(owner_id),
    )
    assert [(r["path"], r["kind"], r["hydration_status"]) for r in rows] == [
        ("1000", "Bookmark", "pending"),
        ("1001", "Reply", "pending"),
    ]

    # Re-push is idempotent and does not re-kick a sync.
    again = await client.post(
        "/api/v1/me/x-items",
        json=_push_body([{"url": "https://x.com/alice/status/1001", "kind": "Reply"}]),
        headers=headers,
    )
    assert again.json() == {"accepted": 1, "new": 0, "existing": 1}
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_push_rejects_non_x_urls(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "TWITTERAPI_IO_KEY", "tapi-key")
    headers, _ = await _register(client)
    resp = await client.post(
        "/api/v1/me/x-items",
        json=_push_body([{"url": "https://example.com/not-x"}]),
        headers=headers,
    )
    assert resp.status_code == 400
    assert "example.com/not-x" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_push_refused_until_twitterapi_key_is_configured(
    client: AsyncClient, pool, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "TWITTERAPI_IO_KEY", None)
    headers, owner_id = await _register(client)

    resp = await client.post(
        "/api/v1/me/x-items",
        json=_push_body([{"url": "https://x.com/alice/status/1001"}]),
        headers=headers,
    )
    assert resp.status_code == 503
    assert "TWITTERAPI_IO_KEY" in resp.json()["detail"]

    count = await pool.fetchval(
        "SELECT count(*) FROM user_sources WHERE owner_user_id = $1", UUID(owner_id)
    )
    assert count == 0


@pytest.mark.asyncio
async def test_indexer_hydrates_content_thread_root_and_media(
    client: AsyncClient, pool, fake_hydration, monkeypatch
) -> None:
    from backend.routers import sources as sources_router

    monkeypatch.setattr(sources_router.celery, "send_task", lambda name, args: None)
    headers, owner_id = await _register(client)
    await client.post(
        "/api/v1/me/x-items",
        json=_push_body([{"url": "https://x.com/alice/status/1001", "kind": "Reply"}]),
        headers=headers,
    )
    source = await pool.fetchrow(
        "SELECT id FROM user_sources WHERE owner_user_id = $1 AND source_type = 'x_saves'",
        UUID(owner_id),
    )
    await x_indexer.index_x_saves(await source_service.get_source_for_sync(source["id"]))

    row = await pool.fetchrow("SELECT * FROM x_save_docs WHERE source_id = $1", source["id"])
    assert row["hydration_status"] == "done"
    assert row["name"] == "@alice - 2025-07-01"
    assert "totally agree with this" in row["content"]
    # The conversation root is kept above the reply for context.
    assert "In reply to @bob" in row["content"]
    assert "here is a hot take" in row["content"]
    assert row["media"] == [{"storage_key": "store/x-1001-0.jpg", "content_type": "image/jpeg"}]
    assert fake_hydration == [("x-1001-0.jpg", "image/jpeg")]

    # The doc read serves fresh presigned media URLs.
    ok, doc = await source_service.source_document(
        UUID(owner_id), UUID(owner_id), str(source["id"]), "1001"
    )
    assert ok
    assert doc["media"] == [
        {"url": "https://blob.example/store/x-1001-0.jpg", "content_type": "image/jpeg"}
    ]


@pytest.mark.asyncio
async def test_hydration_failure_lands_on_the_row(
    client: AsyncClient, pool, fake_hydration, monkeypatch
) -> None:
    async def boom(client_, url):
        raise ValueError("scrapecreators exploded")

    monkeypatch.setattr(x_indexer, "_fetch_tweet", boom)
    from backend.routers import sources as sources_router

    monkeypatch.setattr(sources_router.celery, "send_task", lambda name, args: None)
    headers, owner_id = await _register(client)
    await client.post(
        "/api/v1/me/x-items",
        json=_push_body([{"url": "https://x.com/alice/status/1001", "kind": "Reply"}]),
        headers=headers,
    )
    source = await pool.fetchrow(
        "SELECT id FROM user_sources WHERE owner_user_id = $1 AND source_type = 'x_saves'",
        UUID(owner_id),
    )
    await x_indexer.index_x_saves(await source_service.get_source_for_sync(source["id"]))

    row = await pool.fetchrow(
        "SELECT hydration_status, hydration_error, hydration_attempts "
        "FROM x_save_docs WHERE source_id = $1",
        source["id"],
    )
    assert row["hydration_status"] == "failed"
    assert "scrapecreators exploded" in row["hydration_error"]
    assert row["hydration_attempts"] == 1

    # Reading an unhydrated doc fails loud, not blank.
    ok, doc = await source_service.source_document(
        UUID(owner_id), UUID(owner_id), str(source["id"]), "1001"
    )
    assert ok and doc["http_status"] == 422
    assert "scrapecreators exploded" in doc["error"]
