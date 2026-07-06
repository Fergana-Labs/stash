"""A dead OAuth grant must degrade to needs_reconnect, never a 500.

GET /api/v1/integrations actively refreshes every expired token to compute
needs_reconnect. When the provider's token endpoint rejects the refresh
(revoked grant, expired refresh token), that rejection must be classified as
a dead account — one bad Jira row must not take down the whole integrations
list the settings UI reads.
"""

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient

from backend.integrations import crypto as integration_crypto
from backend.integrations import storage
from backend.integrations.base import AccountInfo, TokenSet
from backend.integrations.jira import provider as jira_provider

from .conftest import unique_name

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture(autouse=True)
def _integration_encryption(monkeypatch):
    monkeypatch.setattr(integration_crypto.settings, "INTEGRATIONS_ENCRYPTION_KEY", TEST_FERNET_KEY)


class _RefreshRejectedClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url, *args, **kwargs):
        return httpx.Response(400, text="invalid_grant", request=httpx.Request("POST", url))


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("jira"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


@pytest.mark.asyncio
async def test_rejected_refresh_surfaces_needs_reconnect_not_500(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(jira_provider.settings, "JIRA_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setattr(jira_provider.settings, "JIRA_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setattr(jira_provider.httpx, "AsyncClient", _RefreshRejectedClient)

    api_key, user_id = await _register(client)
    # Expired access token WITH a refresh token — the list endpoint attempts a
    # refresh, and Atlassian rejects it.
    await storage.store_token(
        user_id,
        "jira",
        TokenSet(
            access_token="token-dead",
            refresh_token="refresh-dead",
            expires_at=datetime(2020, 1, 1, tzinfo=UTC),
            scopes=["read:jira-work"],
        ),
        AccountInfo(email="henry@ferganalabs.com", display_name="Henry"),
    )

    resp = await client.get("/api/v1/integrations", headers={"Authorization": f"Bearer {api_key}"})

    assert resp.status_code == 200
    jira = next(p for p in resp.json()["providers"] if p["provider"] == "jira")
    assert jira["connected"] is True
    assert all(a["needs_reconnect"] is True for a in jira["accounts"])
