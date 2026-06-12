"""Workspace MCP proxy: registry CRUD + tool forwarding.

The proxy's contract is default-deny: an upstream tool is invisible and
uncallable unless it is on the server's explicit allowlist. These tests pin
that property on both tools/list and tools/call — if a refactor ever exposes
non-allowlisted tools, they must fail.
"""

from contextlib import asynccontextmanager

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from backend.integrations import storage
from backend.services import mcp_proxy_service

from .conftest import unique_name

TEST_FERNET_KEY = Fernet.generate_key().decode()

UPSTREAM_TOOLS = [
    Tool(name="list_services", description="List services", inputSchema={"type": "object"}),
    Tool(name="delete_service", description="Delete a service", inputSchema={"type": "object"}),
]


@pytest.fixture(autouse=True)
def _integration_encryption(monkeypatch):
    monkeypatch.setattr(storage.settings, "INTEGRATIONS_ENCRYPTION_KEY", TEST_FERNET_KEY)
    monkeypatch.setattr(storage, "_fernet", None)


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
    async def _fake(url, headers):
        yield session

    monkeypatch.setattr(mcp_proxy_service, "_upstream", _fake)
    return session


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("mcp"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _create_workspace(client: AsyncClient, api_key: str) -> str:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": unique_name("mcp_ws")},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _add_server(client, api_key, ws_id, allowlist, name="render") -> dict:
    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/mcp-servers",
        json={
            "name": name,
            "url": "https://mcp.example.com/mcp",
            "headers": {"Authorization": "Bearer upstream-secret"},
            "tool_allowlist": allowlist,
        },
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()


async def _rpc(client, api_key, ws_id, method, params=None, msg_id=1) -> dict:
    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/mcp",
        json={"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    return resp.json()


# --- Registry -------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_encrypts_headers_and_never_returns_them(client: AsyncClient, pool):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    created = await _add_server(client, api_key, ws_id, ["list_services"])

    assert "headers" not in created
    assert created["has_headers"] is True

    listed = await client.get(
        f"/api/v1/workspaces/{ws_id}/mcp-servers", headers=_auth(api_key)
    )
    body = listed.json()["servers"]
    assert len(body) == 1
    assert "headers" not in body[0]
    assert "upstream-secret" not in listed.text

    stored = await pool.fetchval(
        "SELECT headers_encrypted FROM workspace_mcp_servers WHERE name = 'render'"
    )
    assert b"upstream-secret" not in bytes(stored)


@pytest.mark.asyncio
async def test_server_names_with_underscores_are_rejected(client: AsyncClient):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/mcp-servers",
        json={"name": "my_render", "url": "https://mcp.example.com/mcp"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_members_cannot_touch_the_registry(client: AsyncClient):
    owner_key = await _register(client)
    ws_id = await _create_workspace(client, owner_key)
    intruder_key = await _register(client)

    resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/mcp-servers", headers=_auth(intruder_key)
    )
    assert resp.status_code == 403

    rpc = await client.post(
        f"/api/v1/workspaces/{ws_id}/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers=_auth(intruder_key),
    )
    assert rpc.status_code == 403


@pytest.mark.asyncio
async def test_allow_then_remove_lifecycle(client: AsyncClient):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    await _add_server(client, api_key, ws_id, [])

    updated = await client.patch(
        f"/api/v1/workspaces/{ws_id}/mcp-servers/render",
        json={"tool_allowlist": ["list_services"]},
        headers=_auth(api_key),
    )
    assert updated.json()["tool_allowlist"] == ["list_services"]

    deleted = await client.delete(
        f"/api/v1/workspaces/{ws_id}/mcp-servers/render", headers=_auth(api_key)
    )
    assert deleted.status_code == 204
    listed = await client.get(
        f"/api/v1/workspaces/{ws_id}/mcp-servers", headers=_auth(api_key)
    )
    assert listed.json()["servers"] == []


@pytest.mark.asyncio
async def test_upstream_tools_endpoint_marks_allowed(client: AsyncClient, fake_upstream):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    await _add_server(client, api_key, ws_id, ["list_services"])

    resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/mcp-servers/render/tools", headers=_auth(api_key)
    )
    tools = {t["name"]: t["allowed"] for t in resp.json()["tools"]}
    assert tools == {"list_services": True, "delete_service": False}


# --- Proxy ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_handshake(client: AsyncClient):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    body = await _rpc(
        client, api_key, ws_id, "initialize", {"protocolVersion": "2025-03-26"}
    )
    assert body["result"]["protocolVersion"] == "2025-03-26"
    assert body["result"]["serverInfo"]["name"] == "stash-mcp-proxy"


@pytest.mark.asyncio
async def test_tools_list_exposes_only_allowlisted_tools_namespaced(
    client: AsyncClient, fake_upstream
):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    await _add_server(client, api_key, ws_id, ["list_services"])

    body = await _rpc(client, api_key, ws_id, "tools/list")
    names = [t["name"] for t in body["result"]["tools"]]
    assert names == ["render_list_services"]


@pytest.mark.asyncio
async def test_empty_allowlist_exposes_nothing(client: AsyncClient, fake_upstream):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    await _add_server(client, api_key, ws_id, [])

    body = await _rpc(client, api_key, ws_id, "tools/list")
    assert body["result"]["tools"] == []


@pytest.mark.asyncio
async def test_calling_allowed_tool_forwards_upstream(client: AsyncClient, fake_upstream):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    await _add_server(client, api_key, ws_id, ["list_services"])

    body = await _rpc(
        client,
        api_key,
        ws_id,
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
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    await _add_server(client, api_key, ws_id, ["list_services"])

    body = await _rpc(
        client, api_key, ws_id, "tools/call", {"name": "render_delete_service"}
    )
    assert "error" in body
    assert fake_upstream.calls == []


@pytest.mark.asyncio
async def test_notifications_get_202(client: AsyncClient):
    api_key = await _register(client)
    ws_id = await _create_workspace(client, api_key)
    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 202
