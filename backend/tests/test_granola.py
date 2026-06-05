"""Granola integration (MCP server + OAuth 2.0).

The OAuth handshake and MCP transport are mocked so no live Granola account is
needed: we test that connect builds a correct PKCE authorize URL, that the
callback exchanges + stores a connected account, and that the indexer renders
meetings + transcripts into granola_notes.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.integrations.granola import indexer as granola_indexer
from backend.integrations.granola import oauth
from backend.services import source_service

from .conftest import unique_name

REDIRECT_URI = "https://app.example.com/api/v1/integrations/granola/callback"
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _async(value):
    async def _coro(*a, **k):
        return value

    return _coro


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("gr"), "password": "securepassword1"},
    )
    return r.json()["api_key"], UUID(r.json()["id"])


def _mock_oauth_server(monkeypatch):
    monkeypatch.setattr(oauth.settings, "INTEGRATIONS_ENCRYPTION_KEY", TEST_FERNET_KEY)
    monkeypatch.setattr(oauth.settings, "GRANOLA_OAUTH_REDIRECT_URI", REDIRECT_URI)
    monkeypatch.setattr(
        oauth,
        "_discover",
        _async(
            {
                "authorization_endpoint": "https://mcp-auth.granola.ai/oauth2/authorize",
                "token_endpoint": "https://mcp-auth.granola.ai/oauth2/token",
                "registration_endpoint": "https://mcp-auth.granola.ai/oauth2/register",
            }
        ),
    )
    monkeypatch.setattr(oauth, "_register_client", _async({"client_id": "client_abc"}))


@pytest.mark.asyncio
async def test_connect_builds_pkce_authorize_url(monkeypatch):
    _mock_oauth_server(monkeypatch)

    url = await oauth.start_authorization(UUID(int=1), "/onboarding")
    parsed = urlparse(url)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    assert parsed.netloc == "mcp-auth.granola.ai"
    assert params["client_id"] == "client_abc"
    assert params["response_type"] == "code"
    assert params["code_challenge_method"] == "S256"
    assert params["redirect_uri"] == REDIRECT_URI
    assert params["resource"] == oauth.RESOURCE

    # The state blob round-trips the user, return_to, verifier, and DCR client.
    decoded = oauth._decode_state(params["state"])
    assert decoded["r"] == "/onboarding"
    assert decoded["c"]["client_id"] == "client_abc"
    assert len(decoded["v"]) >= 43  # PKCE verifier


@pytest.mark.asyncio
async def test_callback_exchanges_and_marks_connected(client: AsyncClient, monkeypatch):
    api_key, owner_id = await _register(client)
    _mock_oauth_server(monkeypatch)
    monkeypatch.setattr(
        oauth,
        "_post_token",
        _async({"access_token": "at_live", "refresh_token": "rt_live", "expires_in": 3600}),
    )
    monkeypatch.setattr(
        oauth, "_fetch_account", _async({"email": "sam@example.com", "display_name": "Sam"})
    )

    state = oauth._encode_state(owner_id, "/settings", "verifier" * 8, {"client_id": "client_abc"})
    return_to = await oauth.finish_authorization("auth_code", state)
    assert return_to == "/settings"

    auth = {"Authorization": f"Bearer {api_key}"}
    ints = await client.get("/api/v1/integrations", headers=auth)
    granola = next(p for p in ints.json()["providers"] if p["provider"] == "granola")
    assert granola["connected"] is True
    assert granola["auth_kind"] == "mcp_oauth"
    assert granola["account_email"] == "sam@example.com"


@pytest.mark.asyncio
async def test_integrations_are_unavailable_without_encryption_key(client: AsyncClient, monkeypatch):
    api_key, _ = await _register(client)
    monkeypatch.setattr(oauth.settings, "INTEGRATIONS_ENCRYPTION_KEY", None)

    auth = {"Authorization": f"Bearer {api_key}"}
    response = await client.get("/api/v1/integrations", headers=auth)
    assert response.status_code == 200
    github = next(p for p in response.json()["providers"] if p["provider"] == "github")
    assert github["enabled"] is False
    assert github["connected"] is False
    assert "INTEGRATIONS_ENCRYPTION_KEY" in github["disabled_reason"]

    connect = await client.get("/api/v1/integrations/github/connect", headers=auth)
    assert connect.status_code == 503
    assert "INTEGRATIONS_ENCRYPTION_KEY" in connect.json()["detail"]


@pytest.mark.asyncio
async def test_integrations_are_unavailable_with_invalid_encryption_key(
    client: AsyncClient, monkeypatch
):
    api_key, _ = await _register(client)
    monkeypatch.setattr(oauth.settings, "INTEGRATIONS_ENCRYPTION_KEY", "not-a-fernet-key")

    auth = {"Authorization": f"Bearer {api_key}"}
    response = await client.get("/api/v1/integrations", headers=auth)
    assert response.status_code == 200
    github = next(p for p in response.json()["providers"] if p["provider"] == "github")
    assert github["enabled"] is False
    assert github["disabled_reason"] == "INTEGRATIONS_ENCRYPTION_KEY must be a valid Fernet key."


def _fake_session(tool_routes: dict):
    tool_names = [SimpleNamespace(name=name) for name in tool_routes]
    session = SimpleNamespace()

    async def _list_tools():
        return SimpleNamespace(tools=tool_names)

    session.list_tools = _list_tools

    @asynccontextmanager
    async def _factory(access_token):
        yield session

    async def _call(session, name, arguments=None):
        return tool_routes[name](arguments or {})

    return _factory, _call


@pytest.mark.asyncio
async def test_indexer_pulls_meetings_and_transcripts(client: AsyncClient, monkeypatch):
    api_key, owner_id = await _register(client)
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": unique_name("ws")},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    ws = UUID(ws_resp.json()["id"])
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="granola",
        external_ref="granola",
        display_name="Granola",
    )

    def _transcript(args):
        return {
            "mtg_1": {
                "transcript": [
                    {"speaker": "Sam", "text": "Ship the sources work"},
                    {"speaker": "Alex", "text": "On it"},
                ]
            },
            "mtg_2": {"transcript": []},
        }[args["meeting_id"]]

    routes = {
        "list_meetings": lambda args: {
            "meetings": [
                {
                    "id": "mtg_1",
                    "title": "Q3 Planning",
                    "attendees": [{"name": "Sam"}],
                    "summary": "Budget approved.",
                },
                {"id": "mtg_2", "title": "Standup"},
            ]
        },
        "get_meeting_transcript": _transcript,
    }
    factory, call = _fake_session(routes)
    monkeypatch.setattr(granola_indexer, "get_valid_access_token", _async("at_live"))
    monkeypatch.setattr(granola_indexer, "granola_session", factory)
    monkeypatch.setattr(granola_indexer, "call_tool_data", call)

    await granola_indexer.index_granola(
        {
            "id": str(src["id"]),
            "workspace_id": str(ws),
            "owner_user_id": str(owner_id),
            "source_type": "granola",
            "external_ref": "granola",
        }
    )

    docs = await source_service.list_documents(src)
    assert {d["path"] for d in docs} == {"mtg_1", "mtg_2"}
    note = await source_service.read_document(src, "mtg_1")
    assert "Budget approved." in note["content"]
    assert "**Sam:** Ship the sources work" in note["content"]
