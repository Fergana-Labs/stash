"""Tests for the per-user MCP server registry (/api/v1/me/mcp-servers).

The registry is strictly owner-scoped (no sharing surface), transport
fields are validated at the boundary, and secrets round-trip through the
integrations Fernet keyring.
"""

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient

from backend.config import settings

from .conftest import unique_name


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    """Secrets are Fernet-encrypted; CI has no INTEGRATIONS_ENCRYPTION_KEY."""
    monkeypatch.setattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("mcp"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


STDIO_SERVER = {"name": "linear", "transport": "stdio", "command": "npx -y linear-mcp"}
HTTP_SERVER = {
    "name": "notion",
    "transport": "http",
    "url": "https://mcp.notion.com/mcp",
    "headers": {"Authorization": "Bearer secret-token"},
}


# --- CRUD ---


@pytest.mark.asyncio
async def test_create_list_delete_roundtrip(client: AsyncClient):
    api_key = await _register(client)

    resp = await client.post("/api/v1/me/mcp-servers", json=STDIO_SERVER, headers=_auth(api_key))
    assert resp.status_code == 201
    stdio = resp.json()
    assert stdio["transport"] == "stdio"
    assert stdio["command"] == "npx -y linear-mcp"

    resp = await client.post("/api/v1/me/mcp-servers", json=HTTP_SERVER, headers=_auth(api_key))
    assert resp.status_code == 201

    resp = await client.get("/api/v1/me/mcp-servers", headers=_auth(api_key))
    assert resp.status_code == 200
    servers = {s["name"]: s for s in resp.json()}
    assert set(servers) == {"linear", "notion"}
    # Headers survive the encrypt/decrypt round-trip — the CLI needs the
    # real values to write local .mcp.json entries.
    assert servers["notion"]["headers"] == {"Authorization": "Bearer secret-token"}

    resp = await client.delete(f"/api/v1/me/mcp-servers/{stdio['id']}", headers=_auth(api_key))
    assert resp.status_code == 204
    resp = await client.get("/api/v1/me/mcp-servers", headers=_auth(api_key))
    assert [s["name"] for s in resp.json()] == ["notion"]


@pytest.mark.asyncio
async def test_duplicate_name_conflicts(client: AsyncClient):
    api_key = await _register(client)
    resp = await client.post("/api/v1/me/mcp-servers", json=STDIO_SERVER, headers=_auth(api_key))
    assert resp.status_code == 201
    resp = await client.post("/api/v1/me/mcp-servers", json=STDIO_SERVER, headers=_auth(api_key))
    assert resp.status_code == 409


# --- Owner isolation ---


@pytest.mark.asyncio
async def test_other_users_cannot_see_or_delete_my_servers(client: AsyncClient):
    mine = await _register(client)
    theirs = await _register(client)

    resp = await client.post("/api/v1/me/mcp-servers", json=STDIO_SERVER, headers=_auth(mine))
    server_id = resp.json()["id"]

    resp = await client.get("/api/v1/me/mcp-servers", headers=_auth(theirs))
    assert resp.json() == []

    resp = await client.delete(f"/api/v1/me/mcp-servers/{server_id}", headers=_auth(theirs))
    assert resp.status_code == 404

    resp = await client.get("/api/v1/me/mcp-servers", headers=_auth(mine))
    assert [s["name"] for s in resp.json()] == ["linear"]


# --- Validation: parse, don't validate — reject at the boundary ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"name": "a", "transport": "stdio"},  # stdio without command
        {"name": "a", "transport": "http"},  # http without url
        {"name": "a", "transport": "stdio", "command": "x", "url": "https://x.com"},
        {"name": "a", "transport": "http", "url": "https://x.com", "command": "x"},
        {"name": "a", "transport": "http", "url": "ftp://x.com"},  # non-http scheme
        {"name": "a", "transport": "sse", "url": "https://x.com"},  # unknown transport
        {"name": "bad name!", "transport": "stdio", "command": "x"},  # invalid name
    ],
)
async def test_invalid_bodies_are_rejected(client: AsyncClient, body: dict):
    api_key = await _register(client)
    resp = await client.post("/api/v1/me/mcp-servers", json=body, headers=_auth(api_key))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(client: AsyncClient):
    resp = await client.get("/api/v1/me/mcp-servers")
    assert resp.status_code in (401, 403)


# --- Cloud agent integration ---


@pytest.mark.asyncio
async def test_registered_servers_reach_the_sprite_mcp_config(client: AsyncClient, sprite_exec):
    """An agent turn writes the registry as .mcp.json in the sprite workdir,
    so registered servers are available to the harness."""
    import json

    api_key = await _register(client)
    for body in (STDIO_SERVER, HTTP_SERVER):
        resp = await client.post("/api/v1/me/mcp-servers", json=body, headers=_auth(api_key))
        assert resp.status_code == 201

    resp = await client.post(
        "/api/v1/me/agent-chat", json={"message": "hi"}, headers=_auth(api_key)
    )
    assert resp.status_code == 200

    mcp_writes = [w for w in sprite_exec.writes if w[0].endswith("/work/.mcp.json")]
    assert len(mcp_writes) == 1
    config = json.loads(mcp_writes[0][1])
    assert config["mcpServers"]["linear"] == {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "linear-mcp"],
    }
    assert config["mcpServers"]["notion"] == {
        "type": "http",
        "url": "https://mcp.notion.com/mcp",
        "headers": {"Authorization": "Bearer secret-token"},
    }
