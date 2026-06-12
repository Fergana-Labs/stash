"""Workspace MCP proxy: registered upstream MCP servers + tool forwarding.

A workspace registers upstream MCP servers (url + auth headers, encrypted at
rest with the integrations Fernet key) and curates an explicit tool allowlist
per server — default deny, so a freshly registered server exposes nothing.
The proxy endpoint then acts as a single MCP server whose tools are the
allowlisted upstream tools, namespaced `<server>_<tool>`. Server names cannot
contain underscores, which keeps the namespace reversible.

One upstream credential lives here instead of in every agent's local config:
agents authenticate to Stash with the API key they already have.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ..database import get_pool
from ..integrations.storage import _decrypt, _encrypt

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Protocol revisions this proxy speaks. The handshake echoes the client's
# requested version when we know it, else answers with our latest.
_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


class McpProxyError(Exception):
    """Invalid registration input or unknown server/tool. Routers map this
    to a 4xx; the JSON-RPC handler maps it to an invalid-params error."""


def _row_to_public(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "url": row["url"],
        "has_headers": row["headers_encrypted"] is not None,
        "tool_allowlist": list(row["tool_allowlist"]),
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _encrypt_headers(headers: dict[str, str] | None) -> bytes | None:
    if not headers:
        return None
    return _encrypt(json.dumps(headers))


# --- Registry CRUD -------------------------------------------------------


async def list_servers(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM workspace_mcp_servers WHERE workspace_id = $1 ORDER BY name",
        workspace_id,
    )
    return [_row_to_public(r) for r in rows]


async def create_server(
    workspace_id: UUID,
    name: str,
    url: str,
    headers: dict[str, str] | None,
    tool_allowlist: list[str],
) -> dict:
    if not _NAME_RE.match(name):
        raise McpProxyError(
            "server name must be lowercase letters, digits, and hyphens "
            "(it becomes the tool namespace, so no underscores)"
        )
    pool = get_pool()
    existing = await pool.fetchval(
        "SELECT 1 FROM workspace_mcp_servers WHERE workspace_id = $1 AND name = $2",
        workspace_id,
        name,
    )
    if existing:
        raise McpProxyError(f"an MCP server named '{name}' is already registered")
    row = await pool.fetchrow(
        """
        INSERT INTO workspace_mcp_servers
            (workspace_id, name, url, headers_encrypted, tool_allowlist)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        workspace_id,
        name,
        url,
        _encrypt_headers(headers),
        tool_allowlist,
    )
    return _row_to_public(row)


async def update_server(
    workspace_id: UUID,
    name: str,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    tool_allowlist: list[str] | None = None,
) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        UPDATE workspace_mcp_servers SET
            url = COALESCE($3, url),
            headers_encrypted = COALESCE($4, headers_encrypted),
            tool_allowlist = COALESCE($5, tool_allowlist),
            updated_at = now()
        WHERE workspace_id = $1 AND name = $2
        RETURNING *
        """,
        workspace_id,
        name,
        url,
        _encrypt_headers(headers),
        tool_allowlist,
    )
    return _row_to_public(row) if row else None


async def delete_server(workspace_id: UUID, name: str) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM workspace_mcp_servers WHERE workspace_id = $1 AND name = $2",
        workspace_id,
        name,
    )
    return result == "DELETE 1"


async def _get_server_with_headers(workspace_id: UUID, name: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM workspace_mcp_servers WHERE workspace_id = $1 AND name = $2",
        workspace_id,
        name,
    )
    if not row:
        return None
    decrypted = _decrypt(row["headers_encrypted"])
    server = _row_to_public(row)
    server["headers"] = json.loads(decrypted) if decrypted else {}
    return server


# --- Upstream MCP client --------------------------------------------------


@asynccontextmanager
async def _upstream(url: str, headers: dict[str, str]) -> AsyncIterator[ClientSession]:
    async with streamablehttp_client(url, headers=headers or None) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def list_upstream_tools(workspace_id: UUID, name: str) -> list[dict]:
    """Live tool listing from one upstream, for curating the allowlist."""
    server = await _get_server_with_headers(workspace_id, name)
    if not server:
        raise McpProxyError(f"no MCP server named '{name}'")
    allowed = set(server["tool_allowlist"])
    async with _upstream(server["url"], server["headers"]) as session:
        tools = await _list_all_tools(session)
    return [
        {
            "name": t.name,
            "description": t.description,
            "allowed": t.name in allowed,
        }
        for t in tools
    ]


async def _list_all_tools(session: ClientSession) -> list:
    tools = []
    cursor = None
    while True:
        result = await session.list_tools(cursor=cursor)
        tools.extend(result.tools)
        cursor = result.nextCursor
        if not cursor:
            return tools


# --- MCP proxy (JSON-RPC over streamable HTTP, stateless) -----------------


async def handle_rpc(workspace_id: UUID, message: dict) -> dict | None:
    """Handle one JSON-RPC message. Returns the response payload, or None
    for notifications (which get a bare 202)."""
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}
    if msg_id is None:
        return None

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in _PROTOCOL_VERSIONS else _PROTOCOL_VERSIONS[0]
        return _result(
            msg_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "stash-mcp-proxy", "version": "1.0"},
            },
        )
    if method == "ping":
        return _result(msg_id, {})

    # Tool methods reach over the network to upstreams, which can fail during
    # normal usage (upstream down, bad credentials) — surface those as
    # JSON-RPC errors instead of a 500.
    try:
        if method == "tools/list":
            return _result(msg_id, {"tools": await _aggregate_tools(workspace_id)})
        if method == "tools/call":
            payload = await _call_tool(
                workspace_id, params.get("name") or "", params.get("arguments")
            )
            return _result(msg_id, payload)
    except McpProxyError as e:
        return _error(msg_id, -32602, str(e))
    except Exception as e:
        return _error(msg_id, -32000, f"upstream MCP call failed: {e}")

    return _error(msg_id, -32601, f"method not supported: {method}")


async def _aggregate_tools(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT name FROM workspace_mcp_servers "
        "WHERE workspace_id = $1 AND tool_allowlist != '[]'::jsonb ORDER BY name",
        workspace_id,
    )
    listings = await asyncio.gather(
        *(_allowed_tools_for(workspace_id, row["name"]) for row in rows)
    )
    return [tool for listing in listings for tool in listing]


async def _allowed_tools_for(workspace_id: UUID, name: str) -> list[dict]:
    server = await _get_server_with_headers(workspace_id, name)
    allowed = set(server["tool_allowlist"])
    async with _upstream(server["url"], server["headers"]) as session:
        tools = await _list_all_tools(session)
    return [
        {
            "name": f"{name}_{t.name}",
            "description": t.description,
            "inputSchema": t.inputSchema,
        }
        for t in tools
        if t.name in allowed
    ]


async def _call_tool(workspace_id: UUID, name: str, arguments: dict | None) -> dict:
    server_name, _, tool_name = name.partition("_")
    server = await _get_server_with_headers(workspace_id, server_name)
    if not server or tool_name not in server["tool_allowlist"]:
        raise McpProxyError(f"unknown tool: {name}")
    async with _upstream(server["url"], server["headers"]) as session:
        result = await session.call_tool(tool_name, arguments or {})
    payload: dict[str, Any] = {
        "content": [block.model_dump(mode="json", exclude_none=True) for block in result.content],
        "isError": result.isError,
    }
    if result.structuredContent is not None:
        payload["structuredContent"] = result.structuredContent
    return payload


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
