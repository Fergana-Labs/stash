"""X bookmarks synced source.

The indexer must archive bookmarks (upsert-only — a post un-bookmarked or
aged past the API's first page stays stored) and copy rendered content so
FTS/embeddings work without further X API calls.
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.integrations.twitter import indexer as twitter_indexer
from backend.services import source_service

from .conftest import unique_name

_PAYLOAD_TWO = {
    "data": [
        {
            "id": "111",
            "author_id": "u1",
            "created_at": "2026-07-01T12:00:00.000Z",
            "text": "the first bookmarked post",
            "public_metrics": {"like_count": 5, "retweet_count": 1, "reply_count": 0},
        },
        {
            "id": "222",
            "author_id": "u2",
            "created_at": "2026-07-02T12:00:00.000Z",
            "text": "the second bookmarked post",
        },
    ],
    "includes": {
        "users": [
            {"id": "u1", "username": "alice", "name": "Alice"},
            {"id": "u2", "username": "bob", "name": "Bob"},
        ]
    },
}

_PAYLOAD_ONE = {
    "data": [_PAYLOAD_TWO["data"][1]],
    "includes": {"users": [_PAYLOAD_TWO["includes"]["users"][1]]},
}


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    payload: dict = {}
    requests: list = []

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        type(self).requests.append((url, params))
        return _FakeResponse(type(self).payload)


@pytest.fixture
def fake_x_api(monkeypatch):
    _FakeAsyncClient.requests = []

    async def fake_token(owner_user_id, provider):
        assert provider == "twitter"
        return "token"

    monkeypatch.setattr(twitter_indexer, "get_valid_token", fake_token)
    monkeypatch.setattr(twitter_indexer, "httpx", SimpleNamespace(AsyncClient=_FakeAsyncClient))
    return _FakeAsyncClient


async def _make_source(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    owner_id = UUID(resp.json()["id"])
    created = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="twitter_bookmarks",
        external_ref="9999",
        display_name="X bookmarks (@alice)",
        settings={},
    )
    return await source_service.get_source_for_sync(UUID(created["id"]))


@pytest.mark.asyncio
async def test_indexer_archives_bookmarks_with_content(
    client: AsyncClient, pool, fake_x_api
) -> None:
    source = await _make_source(client)
    fake_x_api.payload = _PAYLOAD_TWO

    await twitter_indexer.index_twitter_bookmarks(source)

    url, params = fake_x_api.requests[0]
    assert url.endswith("/2/users/9999/bookmarks")
    assert params["max_results"] == twitter_indexer.BOOKMARKS_SYNC_PAGE_SIZE

    rows = await pool.fetch(
        "SELECT path, name, content, embed_stale FROM twitter_bookmark_docs "
        "WHERE source_id = $1 ORDER BY path",
        UUID(source["id"]),
    )
    assert [r["path"] for r in rows] == ["111", "222"]
    assert rows[0]["name"] == "@alice - 2026-07-01"
    assert "the first bookmarked post" in rows[0]["content"]
    assert rows[0]["embed_stale"] is True


@pytest.mark.asyncio
async def test_unbookmarked_posts_stay_archived(client: AsyncClient, pool, fake_x_api) -> None:
    source = await _make_source(client)
    fake_x_api.payload = _PAYLOAD_TWO
    await twitter_indexer.index_twitter_bookmarks(source)

    # The user un-bookmarks post 111; the next sync only returns 222.
    fake_x_api.payload = _PAYLOAD_ONE
    await twitter_indexer.index_twitter_bookmarks(source)

    rows = await pool.fetch(
        "SELECT path FROM twitter_bookmark_docs "
        "WHERE source_id = $1 AND deleted_at IS NULL ORDER BY path",
        UUID(source["id"]),
    )
    assert [r["path"] for r in rows] == ["111", "222"]


@pytest.mark.asyncio
async def test_add_source_resolves_account_and_names_bookmarks(
    client: AsyncClient, monkeypatch
) -> None:
    async def fake_resolve(user_id):
        return "9999", "alice"

    from backend.routers import sources as sources_router

    monkeypatch.setattr(sources_router, "_resolve_twitter_source", fake_resolve)

    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['api_key']}"}

    created = await client.post(
        "/api/v1/me/sources",
        json={"source_type": "twitter_bookmarks"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    listed = await client.get("/api/v1/me/sources", headers=headers)
    source = next(s for s in listed.json()["sources"] if s["type"] == "twitter_bookmarks")
    assert source["display_name"] == "X bookmarks (@alice)"
