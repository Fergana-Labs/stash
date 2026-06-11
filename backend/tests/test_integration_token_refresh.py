"""get_valid_token refresh-on-use under concurrency.

Some providers (X) rotate refresh tokens single-use: redeeming the same
refresh token twice answers invalid_grant and can revoke the whole token
family, permanently breaking the connection. Concurrent reads of an expired
token are routine (an agent turn issuing parallel read_source calls), so the
refresh must be single-flight.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.integrations import storage
from backend.integrations.base import AccountInfo, TokenSet

from .conftest import unique_name

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture(autouse=True)
def _integration_encryption(monkeypatch):
    monkeypatch.setattr(storage.settings, "INTEGRATIONS_ENCRYPTION_KEY", TEST_FERNET_KEY)
    monkeypatch.setattr(storage, "_fernet", None)


async def _register(client: AsyncClient) -> UUID:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("tok"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


class _OneShotRefreshProvider:
    """Refuses to redeem a refresh token twice, like X does."""

    def __init__(self):
        self.refreshes = 0

    async def refresh(self, refresh_token: str) -> TokenSet:
        assert refresh_token == "rt-old", "consumed refresh token redeemed again"
        self.refreshes += 1
        # Hold the refresh long enough that the other callers pile up on it.
        await asyncio.sleep(0.05)
        return TokenSet(
            access_token="at-new",
            refresh_token="rt-new",
            expires_at=datetime.now(UTC) + timedelta(hours=2),
            scopes=["tweet.read"],
        )


@pytest.mark.asyncio
async def test_concurrent_reads_of_expired_token_refresh_exactly_once(client, monkeypatch):
    user_id = await _register(client)
    await storage.store_token(
        user_id,
        "twitter",
        TokenSet(
            access_token="at-old",
            refresh_token="rt-old",
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
            scopes=["tweet.read"],
        ),
        AccountInfo(email=None, display_name="@stash"),
    )

    provider = _OneShotRefreshProvider()
    monkeypatch.setattr(storage, "get_provider", lambda name: provider)

    tokens = await asyncio.gather(*(storage.get_valid_token(user_id, "twitter") for _ in range(4)))

    assert provider.refreshes == 1
    assert tokens == ["at-new"] * 4
