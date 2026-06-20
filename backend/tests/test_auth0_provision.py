"""Tests for Auth0 user provisioning.

The `created` flag is the contract the frontend relies on to route first-time
Auth0 sign-ins into onboarding (instead of dropping them on their workspace
like a returning user). If this flag stops distinguishing new from returning
users, new Google-OAuth users silently skip onboarding.
"""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from jose.exceptions import JWTError

from backend.managed.auth0 import jwt as auth0_jwt
from backend.managed.auth0 import router as auth0_router
from backend.managed.auth0 import users as auth0_users
from backend.managed.auth0.jwt import validate_auth0_token
from backend.managed.auth0.users import get_or_create_user_row_from_auth0
from backend.services import user_scope_service

from .conftest import unique_name


@pytest.fixture(autouse=True)
async def _managed_auth0_schema(pool):
    """Auth0 lives in the managed migration chain (backend/managed/migrations),
    which the test DB doesn't apply. Mirror m0001 so users.auth0_sub exists."""
    await pool.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth0_sub VARCHAR(128) UNIQUE")


async def _managed_auth0_headers(monkeypatch, name: str = "Managed User") -> tuple[dict, dict]:
    sub = f"google-oauth2|{unique_name()}"
    user, _created = await get_or_create_user_row_from_auth0(
        auth0_sub=sub,
        email=f"{unique_name('managed')}@example.com",
        name=name,
    )

    async def fake_validate_auth0_token(token: str) -> dict:
        assert token == "auth0-token"
        return {"sub": sub}

    from backend.config import settings

    monkeypatch.setattr(settings, "AUTH0_ENABLED", True)
    monkeypatch.setattr(auth0_jwt, "validate_auth0_token", fake_validate_auth0_token)
    return user, {"Authorization": "Bearer auth0-token"}


@pytest.mark.asyncio
async def test_first_session_provision_reports_created(pool):
    sub = f"google-oauth2|{unique_name()}"
    user, created = await get_or_create_user_row_from_auth0(
        auth0_sub=sub, email=None, name="New Person"
    )
    assert created is True
    # First sign-in provisions the user's scope, so a scope lookup alone can't
    # tell new from returning — only `created` can. The scope is the user.
    scope_id = await user_scope_service.scope_id_for_user(user["id"])
    assert scope_id == user["id"]


@pytest.mark.asyncio
async def test_repeat_session_provision_reports_not_created(pool):
    sub = f"google-oauth2|{unique_name()}"
    first_user, _created = await get_or_create_user_row_from_auth0(
        auth0_sub=sub, email=None, name="Returning Person"
    )
    await pool.execute(
        "UPDATE users SET created_at = now() - interval '1 hour' WHERE id = $1",
        first_user["id"],
    )
    _user, created = await get_or_create_user_row_from_auth0(
        auth0_sub=sub, email=None, name="Returning Person"
    )
    assert created is False


@pytest.mark.asyncio
async def test_immediate_duplicate_session_provision_still_reports_created(pool):
    sub = f"google-oauth2|{unique_name()}"
    await get_or_create_user_row_from_auth0(auth0_sub=sub, email=None, name="Strict Mode Person")
    _user, created = await get_or_create_user_row_from_auth0(
        auth0_sub=sub, email=None, name="Strict Mode Person"
    )
    assert created is True


@pytest.mark.asyncio
async def test_browser_session_provisioning_does_not_mint_api_key(pool):
    sub = f"google-oauth2|{unique_name()}"
    user, created = await get_or_create_user_row_from_auth0(
        auth0_sub=sub,
        email=None,
        name="Browser Session Person",
    )
    assert created is True

    key_count = await pool.fetchval(
        "SELECT count(*) FROM user_api_keys WHERE user_id = $1",
        user["id"],
    )
    assert key_count == 0


@pytest.mark.asyncio
async def test_auth0_exchange_endpoint_does_not_exist():
    """The legacy exchange endpoint minted long-lived API keys for browser
    sessions. It must stay removed — CLI keys come only from explicit
    session approval."""
    app = FastAPI()
    app.include_router(auth0_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth0/exchange",
            headers={"Authorization": "Bearer auth0-token"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_managed_auth0_disables_password_registration_and_login(client, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "AUTH0_ENABLED", True)

    registered = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("managed_password_register"),
            "display_name": "Managed Password Register",
            "password": "securepassword1",
        },
    )
    logged_in = await client.post(
        "/api/v1/users/login",
        json={"name": unique_name("managed_password_login"), "password": "securepassword1"},
    )

    assert registered.status_code == 403
    assert registered.json()["detail"] == "Password auth is disabled; use Auth0"
    assert logged_in.status_code == 403
    assert logged_in.json()["detail"] == "Password auth is disabled; use Auth0"


@pytest.mark.asyncio
async def test_managed_auth0_disables_profile_password_updates(client, pool, monkeypatch):
    user, headers = await _managed_auth0_headers(monkeypatch, name="Managed Password Update")

    updated = await client.patch(
        "/api/v1/users/me",
        json={"password": "newsecurepassword1", "current_password": "oldsecurepassword1"},
        headers=headers,
    )

    assert updated.status_code == 403
    assert updated.json()["detail"] == "Password auth is disabled; use Auth0"
    assert await pool.fetchval("SELECT password_hash FROM users WHERE id = $1", user["id"]) is None


@pytest.mark.asyncio
async def test_managed_auth0_disables_manual_api_key_creation(client, monkeypatch):
    _user, headers = await _managed_auth0_headers(monkeypatch, name="Managed Key User")

    created = await client.post(
        "/api/v1/users/me/keys",
        json={"name": "browser-visible key"},
        headers=headers,
    )

    assert created.status_code == 403
    assert created.json()["detail"] == "Manual API key creation is disabled; use CLI sign-in"


@pytest.mark.asyncio
async def test_managed_auth0_rejects_non_cli_api_keys(client, monkeypatch):
    registered = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("managed_legacy_key"),
            "display_name": "Managed Legacy Key User",
            "password": "securepassword1",
        },
    )
    assert registered.status_code == 201
    api_key = registered.json()["api_key"]

    from backend.config import settings

    monkeypatch.setattr(settings, "AUTH0_ENABLED", True)

    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert me.status_code == 401
    assert me.json()["detail"] == "API key is not allowed for managed auth"


@pytest.mark.asyncio
async def test_managed_auth0_allows_approved_cli_device_keys(client, monkeypatch):
    user, headers = await _managed_auth0_headers(monkeypatch, name="Managed CLI User")

    session = await client.post(
        "/api/v1/users/cli-auth/sessions",
        json={"device_name": "webflow-laptop"},
    )
    assert session.status_code == 200
    session_id = session.json()["session_id"]

    approved = await client.post(
        f"/api/v1/users/cli-auth/sessions/{session_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200

    polled = await client.get(f"/api/v1/users/cli-auth/sessions/{session_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "complete"
    assert body["api_key"].startswith("mc_")

    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {body['api_key']}"},
    )
    assert me.status_code == 200
    assert me.json()["id"] == str(user["id"])


@pytest.mark.asyncio
async def test_managed_auth0_cli_key_cannot_approve_cli_sessions(client, monkeypatch):
    """A leaked CLI key must not be able to mint sibling CLI keys via the
    approve endpoint — that would let it outlive its own revocation. Only an
    Auth0 browser session may approve."""
    _user, headers = await _managed_auth0_headers(monkeypatch, name="Managed CLI Sibling User")

    first = await client.post(
        "/api/v1/users/cli-auth/sessions",
        json={"device_name": "victim-laptop"},
    )
    approved = await client.post(
        f"/api/v1/users/cli-auth/sessions/{first.json()['session_id']}/approve",
        headers=headers,
    )
    assert approved.status_code == 200
    polled = await client.get(f"/api/v1/users/cli-auth/sessions/{first.json()['session_id']}")
    cli_key = polled.json()["api_key"]

    second = await client.post(
        "/api/v1/users/cli-auth/sessions",
        json={"device_name": "attacker-box"},
    )
    session_id = second.json()["session_id"]

    sibling_approve = await client.post(
        f"/api/v1/users/cli-auth/sessions/{session_id}/approve",
        headers={"Authorization": f"Bearer {cli_key}"},
    )

    assert sibling_approve.status_code == 403
    assert sibling_approve.json()["detail"] == "CLI approval requires a browser session"
    repolled = await client.get(f"/api/v1/users/cli-auth/sessions/{session_id}")
    assert repolled.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_auth0_invalid_token_errors_are_redacted(monkeypatch):
    monkeypatch.setattr(auth0_jwt.settings, "AUTH0_DOMAIN", "tenant.example.com")
    monkeypatch.setattr(auth0_jwt.settings, "AUTH0_AUDIENCE", "stash-api")
    monkeypatch.setattr(auth0_jwt.jwt, "get_unverified_header", lambda _token: {"kid": "kid-1"})

    async def fake_fetch_jwks():
        return {"keys": [{"kid": "kid-1"}]}

    def fail_decode(*_args, **_kwargs):
        raise JWTError("issuer=https://tenant.example.com raw-token-secret")

    monkeypatch.setattr(auth0_jwt, "_fetch_jwks", fake_fetch_jwks)
    monkeypatch.setattr(auth0_jwt.jwt, "decode", fail_decode)

    with pytest.raises(HTTPException) as exc:
        await validate_auth0_token("bad-token")

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"
    assert "raw-token-secret" not in exc.value.detail


@pytest.mark.asyncio
async def test_welcome_email_failure_logs_only_metadata(monkeypatch):
    captured_logs: list[tuple[str, tuple, dict]] = []

    def fail_welcome_email(email, first_name=None):
        raise RuntimeError(f"email={email} token=secret-token customer transcript")

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args, kwargs))

    monkeypatch.setattr(auth0_users, "send_welcome_email", fail_welcome_email)
    monkeypatch.setattr(auth0_users.logger, "warning", capture_warning)

    await get_or_create_user_row_from_auth0(
        auth0_sub=f"google-oauth2|{unique_name()}",
        email="user@webflow.com",
        name="Webflow User",
    )

    assert captured_logs == [("welcome email failed exception_type=%s", ("RuntimeError",), {})]
    assert "user@webflow.com" not in str(captured_logs)
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
