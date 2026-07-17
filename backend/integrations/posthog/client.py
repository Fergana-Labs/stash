"""Authenticated client for PostHog's hosted MCP server."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = (
    "https://mcp.posthog.com/mcp"
    "?features=dashboards,product_analytics,flags,experiments&readonly=true"
)


@asynccontextmanager
async def posthog_session(access_token: str) -> AsyncIterator[ClientSession]:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_tool(session: ClientSession, name: str, arguments: dict[str, Any] | None = None):
    result = await session.call_tool(name, arguments or {})
    if result.isError:
        raise RuntimeError(f"PostHog tool failed: {name}")
    if result.structuredContent is not None:
        return result.structuredContent
    for block in result.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    return None
