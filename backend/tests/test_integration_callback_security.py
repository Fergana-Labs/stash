"""Security checks for integration OAuth callbacks."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.integrations import router as integration_router
from backend.integrations.base import TokenSet

from .conftest import unique_name

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
PUBLIC_URL = "https://app.example.com"


async def _register(client: AsyncClient) -> UUID:
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("oauth"), "password": "securepassword1"},
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


class FailingExchangeProvider:
    name = "leaky"
    auth_kind = "oauth"

    async def exchange_code(self, code: str):
        raise RuntimeError("upstream returned client_secret=shh access_token=tok")


class FailingProfileProvider:
    name = "profile"
    auth_kind = "oauth"

    async def exchange_code(self, code: str):
        return TokenSet(
            access_token="at_should_not_be_logged",
            refresh_token="rt_should_not_be_logged",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=["read"],
        )

    async def fetch_account(self, access_token: str):
        raise RuntimeError(f"profile failure for access_token={access_token}")


def _configure_callback(monkeypatch, provider):
    monkeypatch.setattr(
        integration_router.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        TEST_FERNET_KEY,
    )
    monkeypatch.setattr(integration_router.settings, "PUBLIC_URL", PUBLIC_URL)
    monkeypatch.setattr(integration_router, "get_provider", lambda name: provider)


@pytest.mark.asyncio
async def test_oauth_callback_failure_does_not_redirect_or_log_secrets(
    client: AsyncClient,
    monkeypatch,
    caplog,
):
    provider = FailingExchangeProvider()
    _configure_callback(monkeypatch, provider)
    user_id = await _register(client)
    state = integration_router._encode_state(user_id, provider.name, "/settings")

    response = await client.get(
        f"/api/v1/integrations/{provider.name}/callback",
        params={"code": "bad", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    assert location == f"{PUBLIC_URL}/settings?integration_error=leaky&reason=connection_failed"
    assert "client_secret" not in location
    assert "access_token" not in location
    assert "client_secret" not in caplog.text
    assert "access_token" not in caplog.text


@pytest.mark.asyncio
async def test_oauth_profile_failure_does_not_log_tokens(
    client: AsyncClient,
    monkeypatch,
    caplog,
):
    provider = FailingProfileProvider()
    _configure_callback(monkeypatch, provider)
    user_id = await _register(client)
    state = integration_router._encode_state(user_id, provider.name, "/settings")

    response = await client.get(
        f"/api/v1/integrations/{provider.name}/callback",
        params={"code": "ok", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == f"{PUBLIC_URL}/settings?connected=profile"
    assert "at_should_not_be_logged" not in caplog.text
    assert "rt_should_not_be_logged" not in caplog.text
