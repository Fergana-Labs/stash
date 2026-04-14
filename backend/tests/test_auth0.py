"""Tests for the Auth0 JWT authentication path.

These tests mock _verify_auth0_token so no real Auth0 tenant is needed.
They cover:
  - Username derivation from email / display name / sub
  - JIT provisioning: first Auth0 login creates a user row
  - Idempotency: second login returns the same user
  - Username collision resolution
  - /users/me returns the correct user for an Auth0 session
  - Expired token → 401
  - Invalid (non-mc_) token when Auth0 is not configured → 501
"""

import secrets
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from backend.auth import _make_auth0_username, _get_or_create_auth0_user
from .conftest import unique_name


# ---------------------------------------------------------------------------
# Pure unit tests — no database, no HTTP
# ---------------------------------------------------------------------------

class TestMakeAuth0Username:
    def test_derives_from_email_prefix(self):
        assert _make_auth0_username("auth0|abc", "alice@example.com", "Alice Smith") == "alice"

    def test_falls_back_to_name(self):
        assert _make_auth0_username("auth0|abc", None, "Bob Jones") == "Bob_Jones"

    def test_falls_back_to_sub_suffix(self):
        result = _make_auth0_username("auth0|abc123def", None, None)
        assert result == "abc123def"

    def test_strips_unsafe_chars(self):
        result = _make_auth0_username("auth0|x", "hello+world@example.com", None)
        assert result == "hello_world"

    def test_truncates_long_names(self):
        long_email = "a" * 60 + "@example.com"
        result = _make_auth0_username("auth0|x", long_email, None)
        assert len(result) <= 48

    def test_empty_fallback(self):
        result = _make_auth0_username("auth0|", None, None)
        assert result == "user"


# ---------------------------------------------------------------------------
# Database integration tests — require live Postgres (via conftest fixtures)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_jit_provision_creates_user(pool):
    """First Auth0 login creates a new user row with the correct fields."""
    sub = f"auth0|{secrets.token_hex(8)}"
    payload = {"sub": sub, "email": f"{unique_name()}@example.com", "name": "Test User"}

    user = await _get_or_create_auth0_user(payload)

    assert user["id"] is not None
    # Username is derived from email prefix
    assert user["name"] == payload["email"].split("@")[0]
    assert user["display_name"] == "Test User"


@pytest.mark.asyncio
async def test_jit_provision_is_idempotent(pool):
    """Second call with the same sub returns the same user, not a duplicate."""
    sub = f"auth0|{secrets.token_hex(8)}"
    payload = {"sub": sub, "email": f"{unique_name()}@example.com", "name": "Test User"}

    user1 = await _get_or_create_auth0_user(payload)
    user2 = await _get_or_create_auth0_user(payload)

    assert user1["id"] == user2["id"]


@pytest.mark.asyncio
async def test_jit_provision_resolves_username_collision(pool):
    """When the derived username is already taken, a suffix is appended."""
    base = unique_name("collide")
    sub1 = f"auth0|{secrets.token_hex(8)}"
    sub2 = f"auth0|{secrets.token_hex(8)}"
    email1 = f"{base}@example.com"
    email2 = f"{base}@other.com"  # same prefix, different domain → same base username

    user1 = await _get_or_create_auth0_user({"sub": sub1, "email": email1, "name": None})
    user2 = await _get_or_create_auth0_user({"sub": sub2, "email": email2, "name": None})

    assert user1["name"] == base
    assert user2["name"] != base  # collision resolved
    assert user2["name"].startswith(base)


# ---------------------------------------------------------------------------
# HTTP integration tests — mock _verify_auth0_token to avoid real Auth0 calls
# ---------------------------------------------------------------------------

def _make_payload(sub: str, email: str, name: str = "Test User") -> dict:
    return {"sub": sub, "email": email, "name": name}


@pytest.mark.asyncio
async def test_auth0_token_authenticates_user(client: AsyncClient):
    """A Bearer token that does NOT start with mc_ goes through the Auth0 path.
    With _verify_auth0_token mocked, /users/me should return the provisioned user.
    """
    sub = f"auth0|{secrets.token_hex(8)}"
    email = f"{unique_name()}@example.com"
    payload = _make_payload(sub, email)

    with patch("backend.auth._verify_auth0_token", new=AsyncMock(return_value=payload)):
        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer eyJFAKEJWT"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == email.split("@")[0]


@pytest.mark.asyncio
async def test_auth0_token_session_is_persistent(client: AsyncClient):
    """Same sub used in two separate requests returns the same user each time."""
    sub = f"auth0|{secrets.token_hex(8)}"
    email = f"{unique_name()}@example.com"
    payload = _make_payload(sub, email)

    with patch("backend.auth._verify_auth0_token", new=AsyncMock(return_value=payload)):
        resp1 = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer eyJFAKEJWT"})
        resp2 = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer eyJFAKEJWT"})

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_expired_auth0_token_returns_401(client: AsyncClient):
    """An expired JWT results in a 401 Unauthorized."""
    import jwt as pyjwt

    with patch(
        "backend.auth._verify_auth0_token",
        new=AsyncMock(side_effect=HTTPException(status_code=401, detail="Token expired")),
    ):
        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer eyJEXPIREDJWT"},
        )

    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_auth0_token_returns_401(client: AsyncClient):
    """A malformed JWT results in a 401 Unauthorized."""
    with patch(
        "backend.auth._verify_auth0_token",
        new=AsyncMock(side_effect=HTTPException(status_code=401, detail="Invalid token: bad signature")),
    ):
        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer eyJINVALIDJWT"},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth0_not_configured_returns_501(client: AsyncClient):
    """If AUTH0_DOMAIN is not set, the server returns 501 Not Implemented."""
    with patch(
        "backend.auth._verify_auth0_token",
        new=AsyncMock(side_effect=HTTPException(status_code=501, detail="Auth0 is not configured on this server")),
    ):
        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer eyJNOCONFIGJWT"},
        )

    assert resp.status_code == 501
