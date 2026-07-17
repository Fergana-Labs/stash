"""Instagram saves: extension push + ScrapeCreators hydration.

The push endpoint must get-or-create the source (either order with the
connector card works), parse shortcodes loudly, and dedupe. The indexer
must archive content AND media (the point is surviving post deletion),
record per-item failures on the row, and never delete rows.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.integrations.social_saves import indexer as ig_indexer
from backend.services import source_service, storage_service

from .conftest import unique_name

_POST_PAYLOAD = {
    "data": {
        "xdt_shortcode_media": {
            "owner": {"username": "chefkim"},
            "edge_media_to_caption": {"edges": [{"node": {"text": "60-second focaccia"}}]},
            "taken_at_timestamp": 1751371200,  # 2025-07-01T12:00:00Z
            "is_video": True,
            "video_url": "https://cdn.example/reel.mp4",
            "display_url": "https://cdn.example/thumb.jpg",
        }
    }
}

_TRANSCRIPT_PAYLOAD = {
    "success": True,
    "transcripts": [{"id": "1", "shortcode": "ABC123xyz", "text": "mix the flour and water"}],
}


class _FakeResponse:
    def __init__(self, payload=None, content=b"", content_type="video/mp4"):
        self._payload = payload
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeScrapeCreators:
    """Answers the SC post + transcript endpoints and the CDN media URL."""

    media_bytes = b"fake video bytes"

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        if url == ig_indexer.SC_POST_URL:
            return _FakeResponse(payload=_POST_PAYLOAD)
        if url == ig_indexer.SC_TRANSCRIPT_URL:
            return _FakeResponse(payload=_TRANSCRIPT_PAYLOAD)
        if url == "https://cdn.example/reel.mp4":
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

    monkeypatch.setattr(settings, "SCRAPECREATORS_API_KEY", "sc-key")
    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(ig_indexer, "httpx", SimpleNamespace(AsyncClient=_FakeScrapeCreators))
    return uploads


async def _register(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["id"]


def _push_body(urls: list[str]) -> dict:
    return {"platform": "instagram", "items": [{"url": u} for u in urls]}


@pytest.mark.asyncio
async def test_push_creates_source_and_skeleton_rows(
    client: AsyncClient, pool, monkeypatch
) -> None:
    sent: list = []
    from backend.routers import sources as sources_router

    monkeypatch.setattr(settings, "SCRAPECREATORS_API_KEY", "sc-key")
    monkeypatch.setattr(
        sources_router.celery, "send_task", lambda name, args: sent.append((name, args))
    )
    headers, owner_id = await _register(client)

    resp = await client.post(
        "/api/v1/me/saved-items",
        json=_push_body(
            ["https://www.instagram.com/reel/ABC123xyz/", "https://instagram.com/p/DEF456uvw/"]
        ),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"accepted": 2, "new": 2, "existing": 0}
    assert sent and sent[0][0] == "backend.tasks.sources.sync_source"

    rows = await pool.fetch(
        "SELECT path, hydration_status FROM instagram_save_docs WHERE owner_user_id = $1 "
        "ORDER BY path",
        UUID(owner_id),
    )
    assert [(r["path"], r["hydration_status"]) for r in rows] == [
        ("ABC123xyz", "pending"),
        ("DEF456uvw", "pending"),
    ]

    # Re-push is idempotent and does not re-kick a sync.
    again = await client.post(
        "/api/v1/me/saved-items",
        json=_push_body(["https://www.instagram.com/reel/ABC123xyz/"]),
        headers=headers,
    )
    assert again.json() == {"accepted": 1, "new": 0, "existing": 1}
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_push_rejects_non_instagram_urls(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SCRAPECREATORS_API_KEY", "sc-key")
    headers, _ = await _register(client)
    resp = await client.post(
        "/api/v1/me/saved-items",
        json=_push_body(["https://example.com/not-instagram"]),
        headers=headers,
    )
    assert resp.status_code == 400
    assert "example.com/not-instagram" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_push_refused_until_scrapecreators_key_is_configured(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """No key → no source ever gets created, so Instagram saves stay
    invisible everywhere until the server can actually hydrate them."""
    monkeypatch.setattr(settings, "SCRAPECREATORS_API_KEY", None)
    headers, owner_id = await _register(client)

    resp = await client.post(
        "/api/v1/me/saved-items",
        json=_push_body(["https://www.instagram.com/reel/ABC123xyz/"]),
        headers=headers,
    )
    assert resp.status_code == 503
    assert "SCRAPECREATORS_API_KEY" in resp.json()["detail"]

    count = await pool.fetchval(
        "SELECT count(*) FROM user_sources WHERE owner_user_id = $1", UUID(owner_id)
    )
    assert count == 0


@pytest.mark.asyncio
async def test_indexer_hydrates_content_transcript_and_media(
    client: AsyncClient, pool, fake_hydration, monkeypatch
) -> None:
    monkeypatch.setattr(
        __import__("backend.routers.sources", fromlist=["celery"]).celery,
        "send_task",
        lambda name, args: None,
    )
    headers, owner_id = await _register(client)
    await client.post(
        "/api/v1/me/saved-items",
        json=_push_body(["https://www.instagram.com/reel/ABC123xyz/"]),
        headers=headers,
    )
    source = await pool.fetchrow(
        "SELECT id FROM user_sources WHERE owner_user_id = $1 AND source_type = 'instagram_saves'",
        UUID(owner_id),
    )
    await ig_indexer.index_instagram_saves(await source_service.get_source_for_sync(source["id"]))

    row = await pool.fetchrow(
        "SELECT * FROM instagram_save_docs WHERE source_id = $1", source["id"]
    )
    assert row["hydration_status"] == "done"
    assert row["name"] == "@chefkim - 2025-07-01"
    assert "60-second focaccia" in row["content"]
    assert "mix the flour and water" in row["content"]
    assert row["media_storage_key"] == "store/instagram-ABC123xyz.mp4"
    assert row["media_content_type"] == "video/mp4"
    assert row["embed_stale"] is True
    assert fake_hydration == [("instagram-ABC123xyz.mp4", "video/mp4")]
    assert row["external_updated_at"] == datetime.fromtimestamp(1751371200, UTC)

    # The doc read serves a fresh presigned media URL.
    ok, doc = await source_service.source_document(
        UUID(owner_id), UUID(owner_id), str(source["id"]), "ABC123xyz"
    )
    assert ok and doc["media_url"] == "https://blob.example/store/instagram-ABC123xyz.mp4"


@pytest.mark.asyncio
async def test_hydration_failure_lands_on_the_row(
    client: AsyncClient, pool, fake_hydration, monkeypatch
) -> None:
    async def boom(client_, url):
        raise ValueError("scrapecreators exploded")

    monkeypatch.setattr(ig_indexer, "_fetch_post", boom)
    monkeypatch.setattr(
        __import__("backend.routers.sources", fromlist=["celery"]).celery,
        "send_task",
        lambda name, args: None,
    )
    headers, owner_id = await _register(client)
    await client.post(
        "/api/v1/me/saved-items",
        json=_push_body(["https://www.instagram.com/reel/ABC123xyz/"]),
        headers=headers,
    )
    source = await pool.fetchrow(
        "SELECT id FROM user_sources WHERE owner_user_id = $1 AND source_type = 'instagram_saves'",
        UUID(owner_id),
    )
    await ig_indexer.index_instagram_saves(await source_service.get_source_for_sync(source["id"]))

    row = await pool.fetchrow(
        "SELECT hydration_status, hydration_error, hydration_attempts "
        "FROM instagram_save_docs WHERE source_id = $1",
        source["id"],
    )
    assert row["hydration_status"] == "failed"
    assert "scrapecreators exploded" in row["hydration_error"]
    assert row["hydration_attempts"] == 1

    # Reading an unhydrated doc fails loud, not blank.
    ok, doc = await source_service.source_document(
        UUID(owner_id), UUID(owner_id), str(source["id"]), "ABC123xyz"
    )
    assert ok and doc["http_status"] == 422
    assert "scrapecreators exploded" in doc["error"]
