"""MCP proxy: agents reach connected providers' MCP tools through Stash.

POST /api/v1/mcp is a stateless streamable-HTTP MCP server. Its tools are
the union of MCP_PROVIDERS entries whose integration the user has connected
(credentials live in user_integrations like every other integration — see
backend/integrations/). Tools are namespaced `<provider>_<tool>` and each
provider carries a curated, read-only allowlist: anything not on it is
invisible in tools/list and rejected in tools/call before any upstream
request.

One credential, many agents: the user connects the integration once in
settings; agents authenticate to this endpoint with the Stash API key they
already hold.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ..database import get_pool
from ..integrations.storage import get_valid_token

# The read-only judgment per provider, encoded once. Render's
# query_render_postgres is deliberately excluded — it executes SQL against
# production databases, an opt-in beyond "read-only".
MCP_PROVIDERS: dict[str, dict] = {
    "render": {
        "url": "https://mcp.render.com/mcp",
        "tool_allowlist": [
            "list_workspaces",
            "get_selected_workspace",
            "list_services",
            "get_service",
            "list_deploys",
            "get_deploy",
            "list_logs",
            "list_log_label_values",
            "get_metrics",
            "list_postgres_instances",
            "get_postgres",
            "list_key_value",
            "get_key_value",
        ],
    },
}

# Protocol revisions this proxy speaks. The handshake echoes the client's
# requested version when we know it, else answers with our latest.
_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


class McpProxyError(Exception):
    """Unknown or non-allowlisted tool — mapped to a JSON-RPC invalid-params
    error rather than a 500."""


async def _connected_providers(user_id: UUID) -> list[str]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT provider FROM user_integrations WHERE user_id = $1 AND provider = ANY($2)",
        user_id,
        list(MCP_PROVIDERS),
    )
    return sorted(row["provider"] for row in rows)


@asynccontextmanager
async def _upstream(provider: str, user_id: UUID) -> AsyncIterator[ClientSession]:
    api_key = await get_valid_token(user_id, provider)
    headers = {"Authorization": f"Bearer {api_key}"}
    async with streamablehttp_client(MCP_PROVIDERS[provider]["url"], headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _list_all_tools(session: ClientSession) -> list:
    tools = []
    cursor = None
    while True:
        result = await session.list_tools(cursor=cursor)
        tools.extend(result.tools)
        cursor = result.nextCursor
        if not cursor:
            return tools


# --- JSON-RPC over streamable HTTP, stateless ------------------------------


async def handle_rpc(user_id: UUID, message: dict) -> dict | None:
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
    # normal usage (upstream down, key revoked) — surface those as JSON-RPC
    # errors instead of a 500.
    try:
        if method == "tools/list":
            return _result(msg_id, {"tools": await _aggregate_tools(user_id)})
        if method == "tools/call":
            payload = await _call_tool(user_id, params.get("name") or "", params.get("arguments"))
            return _result(msg_id, payload)
    except McpProxyError as e:
        return _error(msg_id, -32602, str(e))
    except Exception as e:
        return _error(msg_id, -32000, f"upstream MCP call failed: {e}")

    return _error(msg_id, -32601, f"method not supported: {method}")


async def _aggregate_tools(user_id: UUID) -> list[dict]:
    providers = await _connected_providers(user_id)
    listings = await asyncio.gather(*(_allowed_tools_for(p, user_id) for p in providers))
    return [tool for listing in listings for tool in listing]


async def _allowed_tools_for(provider: str, user_id: UUID) -> list[dict]:
    allowed = set(MCP_PROVIDERS[provider]["tool_allowlist"])
    async with _upstream(provider, user_id) as session:
        tools = await _list_all_tools(session)
    return [
        {
            "name": f"{provider}_{t.name}",
            "description": t.description,
            "inputSchema": t.inputSchema,
        }
        for t in tools
        if t.name in allowed
    ]


async def _call_tool(user_id: UUID, name: str, arguments: dict | None) -> dict:
    provider, _, tool_name = name.partition("_")
    spec = MCP_PROVIDERS.get(provider)
    if not spec or tool_name not in spec["tool_allowlist"]:
        raise McpProxyError(f"unknown tool: {name}")
    async with _upstream(provider, user_id) as session:
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
