"""Security checks for integration OAuth callbacks."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.integrations import router as integration_router
from backend.integrations.base import AccountInfo, TokenSet

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


async def _register_with_key(client: AsyncClient) -> tuple[UUID, str]:
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("oauth"), "password": "securepassword1"},
    )
    assert response.status_code == 201
    body = response.json()
    return UUID(body["id"]), body["api_key"]


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


class SlackProvider:
    name = "slack"
    auth_kind = "oauth"

    async def exchange_code(self, code: str):
        return TokenSet(
            access_token="xoxp-should-not-be-logged",
            refresh_token=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=["read"],
        )

    async def fetch_account(self, access_token: str):
        return AccountInfo(email=None, display_name=None)


class FailingCredentialProvider:
    name = "leakycredentials"
    display_name = "Leaky Credentials"
    auth_kind = "api_key"

    def __init__(self, exc_type):
        self.exc_type = exc_type

    async def connect_with_credentials(self, values: dict[str, str]):
        raise self.exc_type(f"upstream failed with token={values['token']} and customer transcript")


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


# The callback is always a top-window navigation: every failure must end in a
# redirect the UI renders as a banner — a JSON error body (422 for a missing
# code, 400 for a stale state) strands the user on the API host with no UI.
@pytest.mark.asyncio
async def test_consent_denial_redirects_with_access_denied(
    client: AsyncClient,
    monkeypatch,
):
    provider = FailingExchangeProvider()
    _configure_callback(monkeypatch, provider)

    response = await client.get(
        f"/api/v1/integrations/{provider.name}/callback",
        params={"error": "access_denied", "state": "opaque"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        response.headers["location"]
        == f"{PUBLIC_URL}/settings?integration_error=leaky&reason=access_denied"
    )


@pytest.mark.asyncio
async def test_missing_code_redirects_instead_of_422(
    client: AsyncClient,
    monkeypatch,
):
    provider = FailingExchangeProvider()
    _configure_callback(monkeypatch, provider)

    response = await client.get(
        f"/api/v1/integrations/{provider.name}/callback",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        response.headers["location"]
        == f"{PUBLIC_URL}/settings?integration_error=leaky&reason=connection_failed"
    )


@pytest.mark.asyncio
async def test_invalid_state_redirects_instead_of_400(
    client: AsyncClient,
    monkeypatch,
):
    provider = FailingExchangeProvider()
    _configure_callback(monkeypatch, provider)

    response = await client.get(
        f"/api/v1/integrations/{provider.name}/callback",
        params={"code": "ok", "state": "not-a-valid-fernet-token"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        response.headers["location"]
        == f"{PUBLIC_URL}/settings?integration_error=leaky&reason=connection_failed"
    )


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


@pytest.mark.asyncio
async def test_slack_user_link_capture_failure_logs_only_exception_type(
    client: AsyncClient,
    monkeypatch,
):
    """Slack auth.test failures raise with raw provider error text; the
    best-effort user-link capture must not break the connection and must
    log only the exception class."""
    from backend.integrations.slack import links

    provider = SlackProvider()
    _configure_callback(monkeypatch, provider)
    user_id = await _register(client)
    state = integration_router._encode_state(user_id, provider.name, "/settings")

    async def fail_capture(uid, access_token):
        raise RuntimeError("Slack auth.test error: invalid_auth token=xoxp-secret")

    captured_logs: list[tuple[str, tuple]] = []

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(links, "capture_from_user_token", fail_capture)
    monkeypatch.setattr(integration_router.logger, "warning", capture_warning)

    response = await client.get(
        "/api/v1/integrations/slack/callback",
        params={"code": "ok", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == f"{PUBLIC_URL}/settings?connected=slack"
    assert captured_logs == [
        ("slack: failed to capture user link exception_type=%s", ("RuntimeError",))
    ]
    assert "invalid_auth" not in str(captured_logs)
    assert "xoxp-secret" not in str(captured_logs)


# Bad credentials (ValueError) are the caller's fault (400); anything else —
# upstream outage, provider bug — must surface as a server-side 502, not blame
# the user's credentials. Both paths must redact the raw exception message.
@pytest.mark.parametrize(
    ("exc_type", "expected_status", "expected_detail"),
    [
        (ValueError, 400, "Could not connect Leaky Credentials; check credentials"),
        (RuntimeError, 502, "Could not connect Leaky Credentials; upstream unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_credential_connect_failure_does_not_return_or_log_secrets(
    client: AsyncClient,
    monkeypatch,
    caplog,
    exc_type,
    expected_status,
    expected_detail,
):
    provider = FailingCredentialProvider(exc_type)
    _configure_callback(monkeypatch, provider)
    _user_id, api_key = await _register_with_key(client)

    response = await client.post(
        f"/api/v1/integrations/{provider.name}/credentials",
        json={"token": "secret-token"},
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert "secret-token" not in response.text
    assert "customer transcript" not in response.text
    assert "secret-token" not in caplog.text
    assert "customer transcript" not in caplog.text
