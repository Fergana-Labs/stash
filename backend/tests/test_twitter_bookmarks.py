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
    status_code = 200

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


# --- Connect-time auto-creation + failure surfacing ---


class _FakeTwitterProvider:
    name = "twitter"
    auth_kind = "oauth"

    async def exchange_code(self, code: str):
        from datetime import UTC, datetime, timedelta

        from backend.integrations.base import TokenSet

        return TokenSet(
            access_token="at",
            refresh_token="rt",
            expires_at=datetime.now(UTC) + timedelta(hours=2),
            scopes=["bookmark.read"],
        )

    async def fetch_account(self, access_token: str):
        from backend.integrations.base import AccountInfo

        return AccountInfo(email=None, display_name="@alice")


@pytest.mark.asyncio
async def test_connect_callback_auto_creates_twitter_sources(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """Everything downstream (explorer sidebar, CLI `stash ls`, sources list)
    keys off sources, not integrations — so connecting X must create its
    sources immediately, and bookmarks then syncs on the normal schedule."""
    from backend.integrations import router as integration_router

    monkeypatch.setattr(
        integration_router.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    monkeypatch.setattr(integration_router, "get_provider", lambda name: _FakeTwitterProvider())

    async def fake_me(token):
        return {"id": "9999", "username": "alice"}

    monkeypatch.setattr(twitter_indexer, "fetch_me", fake_me)

    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    user_id = resp.json()["id"]
    state = integration_router._encode_state(UUID(user_id), "twitter", "/settings")

    callback = await client.get(
        f"/api/v1/integrations/twitter/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert callback.status_code == 302

    rows = await pool.fetch(
        "SELECT source_type, external_ref, display_name, sync_enabled, next_sync_at <= now() AS due "
        "FROM user_sources WHERE owner_user_id = $1 ORDER BY source_type",
        UUID(user_id),
    )
    assert [(r["source_type"], r["external_ref"], r["display_name"]) for r in rows] == [
        ("twitter", "9999", "Twitter / X (@alice)"),
        ("twitter_bookmarks", "9999", "X bookmarks (@alice)"),
    ]
    # Bookmarks are extension-fed by default (the browser captures them for
    # $0) — the source exists and shows in the sidebar/CLI, but server-side
    # sync stays off until the owner brings their own paid X app.
    bookmarks = rows[1]
    assert bookmarks["sync_enabled"] is False


@pytest.mark.asyncio
async def test_bookmarks_402_reports_the_tier_problem(client: AsyncClient, fake_x_api) -> None:
    source = await _make_source(client)

    class _PaymentRequired(_FakeResponse):
        status_code = 402

        def raise_for_status(self):
            raise AssertionError("402 must be translated before raise_for_status")

    fake_x_api.payload = {}
    original_get = _FakeAsyncClient.get

    async def get_402(self, url, params=None):
        return _PaymentRequired({})

    _FakeAsyncClient.get = get_402
    try:
        with pytest.raises(source_service.SourceSyncUserError, match="paid X API tier"):
            await twitter_indexer.index_twitter_bookmarks(source)
    finally:
        _FakeAsyncClient.get = original_get


@pytest.mark.asyncio
async def test_user_error_lands_on_the_source_row_verbatim(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """SourceSyncUserError messages are owner-facing and stored as-is; raw
    exceptions stay behind the redacted constant (covered in test_sources)."""
    from backend.tasks import sources as sources_tasks

    source = await _make_source(client)

    async def tier_gated_indexer(src):
        raise source_service.SourceSyncUserError("X returned 402 for the bookmarks API")

    monkeypatch.setitem(sources_tasks.INDEXERS, "twitter_bookmarks", tier_gated_indexer)
    result = await sources_tasks._sync_source(UUID(source["id"]))
    assert result == {"status": "failed"}

    sync_error = await pool.fetchval(
        "SELECT sync_error FROM user_sources WHERE id = $1", UUID(source["id"])
    )
    assert sync_error == "X returned 402 for the bookmarks API"


# --- Extension capture push ---


async def _connect_twitter(client: AsyncClient, monkeypatch) -> tuple[dict, str]:
    """Register + run the OAuth callback so both twitter sources exist."""
    from backend.integrations import router as integration_router

    monkeypatch.setattr(
        integration_router.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    monkeypatch.setattr(integration_router, "get_provider", lambda name: _FakeTwitterProvider())

    async def fake_me(token):
        return {"id": "9999", "username": "alice"}

    monkeypatch.setattr(twitter_indexer, "fetch_me", fake_me)

    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = resp.json()
    headers = {"Authorization": f"Bearer {body['api_key']}"}
    state = integration_router._encode_state(UUID(body["id"]), "twitter", "/settings")
    await client.get(
        f"/api/v1/integrations/twitter/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    return headers, body["id"]


@pytest.mark.asyncio
async def test_extension_push_stores_bookmarks(client: AsyncClient, pool, monkeypatch) -> None:
    headers, owner_id = await _connect_twitter(client, monkeypatch)

    resp = await client.post(
        "/api/v1/me/twitter-bookmarks",
        json={
            "items": [
                {
                    "id": "111",
                    "text": "the first bookmarked post",
                    "author_username": "alice",
                    "created_at": "2026-07-01T12:00:00+00:00",
                },
                {"id": "222", "text": "second", "author_username": "bob"},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 2, "stored": 2}

    rows = await pool.fetch(
        "SELECT path, name, content FROM twitter_bookmark_docs WHERE owner_user_id = $1 "
        "ORDER BY path",
        UUID(owner_id),
    )
    assert [r["path"] for r in rows] == ["111", "222"]
    assert rows[0]["name"] == "@alice - 2026-07-01"
    assert "the first bookmarked post" in rows[0]["content"]


@pytest.mark.asyncio
async def test_extension_push_is_idempotent(client: AsyncClient, pool, monkeypatch) -> None:
    headers, owner_id = await _connect_twitter(client, monkeypatch)
    item = {"items": [{"id": "111", "text": "hi", "author_username": "alice"}]}

    await client.post("/api/v1/me/twitter-bookmarks", json=item, headers=headers)
    await client.post("/api/v1/me/twitter-bookmarks", json=item, headers=headers)

    count = await pool.fetchval(
        "SELECT count(*) FROM twitter_bookmark_docs WHERE owner_user_id = $1", UUID(owner_id)
    )
    assert count == 1


@pytest.mark.asyncio
async def test_extension_push_requires_connected_x(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['api_key']}"}

    push = await client.post(
        "/api/v1/me/twitter-bookmarks",
        json={"items": [{"id": "1", "text": "x"}]},
        headers=headers,
    )
    assert push.status_code == 400
    assert "Connect Twitter" in push.json()["detail"]


# --- Bring-your-own X app (BYOA) ---


@pytest.mark.asyncio
async def test_byoa_store_then_connect_enables_server_sync(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """A user who pastes their own X app credentials BEFORE connecting: the
    connect flow uses their client id, and server-side bookmark sync turns
    on (they pay for the reads)."""
    from backend.integrations import router as integration_router
    from backend.integrations.twitter import app_credentials

    monkeypatch.setattr(
        integration_router.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    monkeypatch.setattr(integration_router, "get_provider", lambda name: _FakeTwitterProvider())

    async def fake_me(token):
        return {"id": "9999", "username": "alice"}

    monkeypatch.setattr(twitter_indexer, "fetch_me", fake_me)

    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = resp.json()
    headers = {"Authorization": f"Bearer {body['api_key']}"}

    # Store BYOA app creds — X not connected yet, so reconnect is required.
    stored = await client.post(
        "/api/v1/integrations/twitter/app",
        json={"client_id": "my-client", "client_secret": "my-secret"},
        headers=headers,
    )
    assert stored.status_code == 200
    assert stored.json()["reconnect_required"] is True

    # The secret is retrievable server-side (encrypted at rest) but never
    # returned by the GET.
    creds = await app_credentials.get(UUID(body["id"]))
    assert creds == {"client_id": "my-client", "client_secret": "my-secret"}
    got = await client.get("/api/v1/integrations/twitter/app", headers=headers)
    assert got.json() == {"configured": True, "client_id": "my-client"}

    # Now connect X; the auto-create sees BYOA creds and enables server sync.
    state = integration_router._encode_state(UUID(body["id"]), "twitter", "/settings")
    await client.get(
        f"/api/v1/integrations/twitter/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    sync_enabled = await pool.fetchval(
        "SELECT sync_enabled FROM user_sources "
        "WHERE owner_user_id = $1 AND source_type = 'twitter_bookmarks'",
        UUID(body["id"]),
    )
    assert sync_enabled is True


@pytest.mark.asyncio
async def test_byoa_after_connect_flips_sync_on_and_off(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, owner_id = await _connect_twitter(client, monkeypatch)

    # Default: extension-fed, server sync off.
    assert (
        await pool.fetchval(
            "SELECT sync_enabled FROM user_sources "
            "WHERE owner_user_id = $1 AND source_type = 'twitter_bookmarks'",
            UUID(owner_id),
        )
        is False
    )

    # Add BYOA creds after connecting → sync flips on immediately.
    added = await client.post(
        "/api/v1/integrations/twitter/app",
        json={"client_id": "c", "client_secret": "s"},
        headers=headers,
    )
    assert added.json()["reconnect_required"] is False
    assert (
        await pool.fetchval(
            "SELECT sync_enabled FROM user_sources "
            "WHERE owner_user_id = $1 AND source_type = 'twitter_bookmarks'",
            UUID(owner_id),
        )
        is True
    )

    # Remove BYOA creds → back to extension-fed.
    await client.delete("/api/v1/integrations/twitter/app", headers=headers)
    assert (
        await pool.fetchval(
            "SELECT sync_enabled FROM user_sources "
            "WHERE owner_user_id = $1 AND source_type = 'twitter_bookmarks'",
            UUID(owner_id),
        )
        is False
    )
    assert await client.get("/api/v1/integrations/twitter/app", headers=headers) is not None


@pytest.mark.asyncio
async def test_byoa_client_id_used_in_connect_authorize_url(
    client: AsyncClient, monkeypatch
) -> None:
    """The authorize URL must carry the user's own client_id when BYOA is set."""
    from backend.integrations import router as integration_router
    from backend.integrations.twitter.provider import TwitterIntegration

    monkeypatch.setattr(
        integration_router.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    monkeypatch.setattr(integration_router.settings, "TWITTER_OAUTH_CLIENT_ID", "stash-app")
    monkeypatch.setattr(
        integration_router.settings, "TWITTER_OAUTH_REDIRECT_URI", "https://api.example/cb"
    )
    monkeypatch.setattr(integration_router, "get_provider", lambda name: TwitterIntegration())
    monkeypatch.setattr(integration_router.billing_service, "ensure_can_connect", _noop_async)

    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['api_key']}"}

    # Shared app first.
    shared = await client.get("/api/v1/integrations/twitter/connect", headers=headers)
    assert "client_id=stash-app" in shared.json()["authorize_url"]

    # Then BYOA.
    await client.post(
        "/api/v1/integrations/twitter/app",
        json={"client_id": "user-app", "client_secret": "s"},
        headers=headers,
    )
    byoa = await client.get("/api/v1/integrations/twitter/connect", headers=headers)
    assert "client_id=user-app" in byoa.json()["authorize_url"]


async def _noop_async(*args, **kwargs):
    return None
