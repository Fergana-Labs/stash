"""Remote MCP endpoint: mounting rules and token audience separation.

The audience tests are the important ones. Claude's tokens are minted for the
MCP endpoint's own URL, and the web app's are minted for the API identifier. If
this endpoint ever validated against the web app's audience, a token issued for
one surface would be accepted by the other — which is the whole reason the two
audiences are separate.
"""

import pytest
from fastapi import FastAPI, HTTPException

from backend import mcp_remote
from backend.config import settings

MCP_URL = "https://api.example.test/mcp"
AUTH0_DOMAIN = "tenant.us.auth0.test"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", MCP_URL)
    monkeypatch.setattr(settings, "AUTH0_DOMAIN", AUTH0_DOMAIN)


def test_not_mounted_without_config(monkeypatch):
    """A self-hosted or local deployment has no Auth0 tenant to verify tokens
    against, so it must not serve a half-configured public endpoint."""
    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", "")
    app = FastAPI()

    assert mcp_remote.attach(app) is False
    assert not any(getattr(r, "path", "") == "/mcp" for r in app.routes)


def test_mounts_at_the_url_path(configured):
    """Claude requires the advertised resource to match the connector URL
    exactly, path included — so the mount point comes from the URL, not a
    constant that could drift away from it."""
    app = FastAPI()

    assert mcp_remote.attach(app) is True
    assert any(getattr(r, "path", "") == "/mcp" for r in app.routes)


def test_pathless_url_fails_loud(monkeypatch):
    """A bare origin would mount at "" and answer nothing; Claude's error for
    that is an unhelpful "couldn't reach the MCP server"."""
    monkeypatch.setattr(settings, "MCP_PUBLIC_URL", "https://api.example.test")
    monkeypatch.setattr(settings, "AUTH0_DOMAIN", AUTH0_DOMAIN)

    with pytest.raises(RuntimeError, match="needs a path"):
        mcp_remote.attach(FastAPI())


@pytest.mark.asyncio
async def test_unauthenticated_call_starts_the_discovery_chain(configured):
    """The entire connect flow hangs off this handshake: Claude posts, gets a
    401 whose WWW-Authenticate names a metadata URL, reads that document, and
    learns which authorization server to send the user to. Break any link and
    Claude reports only "couldn't reach the MCP server"."""
    from httpx import ASGITransport, AsyncClient

    app = FastAPI()
    mcp_remote.attach(app)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t", follow_redirects=True
    ) as client:
        call = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert call.status_code == 401
        challenge = call.headers["www-authenticate"]
        assert 'resource_metadata="' in challenge

        metadata_url = challenge.split('resource_metadata="')[1].split('"')[0]
        doc = await client.get(metadata_url.replace("https://api.example.test", ""))

    assert doc.status_code == 200
    body = doc.json()
    assert body["resource"] == MCP_URL
    assert body["authorization_servers"] == [f"https://{AUTH0_DOMAIN}/"]


@pytest.mark.asyncio
async def test_verifier_uses_the_endpoints_own_audience(configured, monkeypatch):
    """Tokens must be checked against this endpoint's URL, never the web app's
    API identifier — that separation is what stops a token minted for one
    surface being replayed against the other."""
    seen = {}

    async def fake_validate(token, audience):
        seen["audience"] = audience
        return {"sub": "auth0|abc", "scope": "openid profile", "exp": 9999999999}

    monkeypatch.setattr(
        "backend.managed.auth0.jwt.validate_auth0_token_for_audience", fake_validate
    )

    result = await mcp_remote.Auth0TokenVerifier().verify_token("a-token")

    assert seen["audience"] == MCP_URL
    assert result is not None
    assert result.subject == "auth0|abc"
    assert result.resource == MCP_URL


@pytest.mark.asyncio
async def test_rejected_token_returns_none(configured, monkeypatch):
    """An expired or malformed token is routine — Claude refreshes on a 401.
    The library wants None for that; a raised HTTPException would surface as a
    500 and Claude would not re-authenticate."""

    async def fake_validate(token, audience):
        raise HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr(
        "backend.managed.auth0.jwt.validate_auth0_token_for_audience", fake_validate
    )

    assert await mcp_remote.Auth0TokenVerifier().verify_token("bad") is None


@pytest.mark.asyncio
async def test_token_without_subject_is_rejected(configured, monkeypatch):
    """Every tool call acts as a specific user. A token that names nobody must
    not become a session that acts as nobody."""

    async def fake_validate(token, audience):
        return {"scope": "openid"}

    monkeypatch.setattr(
        "backend.managed.auth0.jwt.validate_auth0_token_for_audience", fake_validate
    )

    assert await mcp_remote.Auth0TokenVerifier().verify_token("no-sub") is None
