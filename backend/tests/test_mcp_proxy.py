"""MCP proxy: connected integrations' read-only tools, served to agents.

The proxy's contract: a provider's tools appear only after its integration
is connected, and only the tools on its curated read-only allowlist are
visible in tools/list or callable in tools/call. These tests pin that on
both methods — if a refactor ever exposes a mutating tool, they must fail.
"""

from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from backend.integrations import crypto as integration_crypto
from backend.integrations import storage
from backend.integrations.base import AccountInfo, TokenSet
from backend.integrations.render import provider as render_provider
from backend.services import mcp_proxy_service

from .conftest import unique_name

TEST_FERNET_KEY = Fernet.generate_key().decode()

UPSTREAM_TOOLS = [
    Tool(name="list_services", description="List services", inputSchema={"type": "object"}),
    Tool(name="create_web_service", description="Create a service", inputSchema={"type": "object"}),
]


@pytest.fixture(autouse=True)
def _integration_encryption(monkeypatch):
    monkeypatch.setattr(
        integration_crypto.settings, "INTEGRATIONS_ENCRYPTION_KEY", TEST_FERNET_KEY
    )


class FakeUpstreamSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self, cursor=None):
        return ListToolsResult(tools=UPSTREAM_TOOLS, nextCursor=None)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return CallToolResult(
            content=[TextContent(type="text", text=f"ran {name}")], isError=False
        )


@pytest.fixture
def fake_upstream(monkeypatch):
    session = FakeUpstreamSession()

    @asynccontextmanager
    async def _fake(provider, user_id):
        yield session

    monkeypatch.setattr(mcp_proxy_service, "_upstream", _fake)
    return session


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("mcp"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _connect_render(user_id: UUID, api_key: str = "rnd_upstream_secret") -> None:
    await storage.store_token(
        user_id,
        "render",
        TokenSet(access_token=api_key, refresh_token=None, expires_at=None, scopes=[]),
        AccountInfo(email="henry@ferganalabs.com", display_name="Fergana Labs"),
    )


async def _rpc(client, api_key, method, params=None, msg_id=1) -> dict:
    resp = await client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    return resp.json()


# --- Connect flow -----------------------------------------------------------


@pytest.mark.asyncio
async def test_render_connects_through_the_integrations_framework(
    client: AsyncClient, monkeypatch
):
    class _FakeOwners:
        def __call__(self, *args, **kwargs):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params=None):
            class R:
                status_code = 200

                def json(self):
                    return [{"owner": {"name": "Fergana Labs", "email": "henry@ferganalabs.com"}}]

            return R()

    monkeypatch.setattr(render_provider.httpx, "AsyncClient", _FakeOwners())

    api_key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/integrations/render/credentials",
        json={"api_key": "rnd_real_key"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["account_display_name"] == "Fergana Labs"

    listed = await client.get("/api/v1/integrations", headers=_auth(api_key))
    render = next(p for p in listed.json()["providers"] if p["provider"] == "render")
    assert render["connected"] is True
    assert "rnd_real_key" not in listed.text


@pytest.mark.asyncio
async def test_render_rejects_bad_key(client: AsyncClient, monkeypatch):
    class _Rejecting:
        def __call__(self, *args, **kwargs):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params=None):
            class R:
                status_code = 401

                def json(self):
                    return {}

            return R()

    monkeypatch.setattr(render_provider.httpx, "AsyncClient", _Rejecting())

    api_key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/integrations/render/credentials",
        json={"api_key": "rnd_bad"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 400


# --- The curated allowlist --------------------------------------------------


def test_render_allowlist_is_read_only():
    allowlist = mcp_proxy_service.MCP_PROVIDERS["render"]["tool_allowlist"]
    assert not any(t.startswith(("create_", "update_", "delete_")) for t in allowlist)
    # The SQL tool is read-but-powerful and must stay an explicit opt-in,
    # never part of the default allowlist.
    assert "query_render_postgres" not in allowlist


# --- Proxy ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_handshake(client: AsyncClient):
    api_key, _ = await _register(client)
    body = await _rpc(client, api_key, "initialize", {"protocolVersion": "2025-03-26"})
    assert body["result"]["protocolVersion"] == "2025-03-26"
    assert body["result"]["serverInfo"]["name"] == "stash-mcp-proxy"


@pytest.mark.asyncio
async def test_tools_list_is_empty_until_the_integration_is_connected(
    client: AsyncClient, fake_upstream
):
    api_key, user_id = await _register(client)

    body = await _rpc(client, api_key, "tools/list")
    assert body["result"]["tools"] == []

    await _connect_render(user_id)
    body = await _rpc(client, api_key, "tools/list")
    names = [t["name"] for t in body["result"]["tools"]]
    assert names == ["render_list_services"]  # namespaced; create_web_service filtered out


@pytest.mark.asyncio
async def test_calling_allowed_tool_forwards_upstream(client: AsyncClient, fake_upstream):
    api_key, user_id = await _register(client)
    await _connect_render(user_id)

    body = await _rpc(
        client,
        api_key,
        "tools/call",
        {"name": "render_list_services", "arguments": {"limit": 5}},
    )
    assert body["result"]["isError"] is False
    assert body["result"]["content"][0]["text"] == "ran list_services"
    assert fake_upstream.calls == [("list_services", {"limit": 5})]


@pytest.mark.asyncio
async def test_calling_non_allowlisted_tool_is_rejected_before_upstream(
    client: AsyncClient, fake_upstream
):
    api_key, user_id = await _register(client)
    await _connect_render(user_id)

    body = await _rpc(client, api_key, "tools/call", {"name": "render_create_web_service"})
    assert "error" in body
    assert fake_upstream.calls == []


@pytest.mark.asyncio
async def test_notifications_get_202(client: AsyncClient):
    api_key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_mcp_endpoint_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert resp.status_code in (401, 403)
