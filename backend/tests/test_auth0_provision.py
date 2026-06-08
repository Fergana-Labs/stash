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

from .conftest import unique_name


@pytest.fixture(autouse=True)
async def _managed_auth0_schema(pool):
    """Auth0 lives in the managed migration chain (backend/managed/migrations),
    which the test DB doesn't apply. Mirror m0001 so users.auth0_sub exists."""
    await pool.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth0_sub VARCHAR(128) UNIQUE")


@pytest.mark.asyncio
async def test_first_session_provision_reports_created(pool):
    sub = f"google-oauth2|{unique_name()}"
    user, created = await get_or_create_user_row_from_auth0(
        auth0_sub=sub, email=None, name="New Person"
    )
    assert created is True
    # First sign-in provisions a workspace, so a workspace lookup alone can't
    # tell new from returning — only `created` can.
    ws_count = await pool.fetchval(
        "SELECT count(*) FROM workspace_members WHERE user_id = $1", user["id"]
    )
    assert ws_count == 1


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
async def test_auth0_exchange_endpoint_does_not_mint_api_keys():
    app = FastAPI()
    app.include_router(auth0_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth0/exchange",
            headers={"Authorization": "Bearer auth0-token"},
        )

    assert resp.status_code == 410
    assert "API key exchange is disabled" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_managed_auth0_disables_manual_api_key_creation(client, monkeypatch):
    registered = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("managed_key"),
            "display_name": "Managed Key User",
            "password": "securepassword1",
        },
    )
    assert registered.status_code == 201
    api_key = registered.json()["api_key"]

    from backend.routers import users as users_router

    monkeypatch.setattr(users_router.settings, "AUTH0_ENABLED", True)

    created = await client.post(
        "/api/v1/users/me/keys",
        json={"name": "browser-visible key"},
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert created.status_code == 403
    assert created.json()["detail"] == "Manual API key creation is disabled; use CLI sign-in"


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
