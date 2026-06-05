"""Thin MCP client for the Granola server.

Granola's data lives behind its official MCP server (Streamable HTTP). We talk
to it as a plain MCP client with a bearer access token in the Authorization
header — the OAuth handshake (see oauth.py) already produced that token, so the
transport here is auth-agnostic. Callers open a session, call tools, and read
JSON back.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ...config import settings


@asynccontextmanager
async def granola_session(access_token: str) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP session to the Granola server."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with streamablehttp_client(settings.GRANOLA_MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_tool_json(
    session: ClientSession, name: str, arguments: dict[str, Any] | None = None
) -> Any:
    """Call an MCP tool and return its result as parsed JSON.

    MCP tools return `structuredContent` (a dict) when they declare an output
    schema; otherwise the payload comes back as a single JSON text block. We
    prefer the structured form and fall back to parsing the text — both are the
    normal MCP result shape, not error handling.
    """
    result = await session.call_tool(name, arguments or {})
    if result.isError:
        text = _first_text(result.content)
        raise RuntimeError(f"granola tool {name} failed: {text}")
    if result.structuredContent is not None:
        return result.structuredContent
    text = _first_text(result.content)
    return json.loads(text) if text else None


async def call_tool_data(
    session: ClientSession, name: str, arguments: dict[str, Any] | None = None
) -> Any:
    """Call a tool and return its data, tolerant of result shape: prefer
    structuredContent, then JSON text, then the raw text. Never raises on a
    non-JSON body (Granola tools may return markdown) — only on an MCP error."""
    result = await session.call_tool(name, arguments or {})
    if result.isError:
        raise RuntimeError(f"granola tool {name} failed: {_first_text(result.content)}")
    if result.structuredContent is not None:
        return result.structuredContent
    text = _first_text(result.content)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text  # markdown / plain text — caller handles it


def _first_text(content: list) -> str:
    for block in content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""
