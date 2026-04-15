#!/usr/bin/env python3
"""Octopus MCP server — stdio transport.

Exposes retrieval tools over the Model Context Protocol so any MCP-capable
agent (Cursor, Codex, Gemini, Copilot-in-VSCode, opencode, etc.) can search
and read from an Octopus workspace without a native plugin.

Covers retrieval only. Per-prompt streaming and tool_use logging need the
agent-specific plugins in ../cursor-plugin/, ../gemini-plugin/, etc.

Install:
    pip install "mcp[cli]" httpx
    # point your agent's MCP config at: python3 /abs/path/to/server.py
"""

import json
import os
import re
import sys
from pathlib import Path

_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _valid_id(value: str) -> bool:
    return bool(value) and _ID_RE.fullmatch(value) is not None


SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(SHARED))

from mcp.server.fastmcp import FastMCP  # type: ignore  # noqa: E402

from octopus_client import OctopusClient  # noqa: E402


def _cli_config() -> dict:
    path = Path.home() / ".octopus" / "config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _client() -> OctopusClient:
    cli = _cli_config()
    base = os.environ.get("OCTOPUS_API_ENDPOINT", cli.get("base_url", "https://getoctopus.com"))
    key = os.environ.get("OCTOPUS_API_KEY", cli.get("api_key", ""))
    return OctopusClient(base_url=base, api_key=key)


def _default_workspace() -> str:
    return os.environ.get("OCTOPUS_WORKSPACE_ID", _cli_config().get("default_workspace", ""))


mcp = FastMCP("octopus")


@mcp.tool()
def whoami() -> dict:
    """Return the current user's profile (name, email, default workspace)."""
    with _client() as c:
        return c.whoami()


@mcp.tool()
def list_workspaces(mine_only: bool = True) -> list:
    """List Octopus workspaces. Set mine_only=false to include public ones."""
    with _client() as c:
        return c.list_workspaces(mine=mine_only)


@mcp.tool()
def query_history(
    workspace_id: str = "",
    agent_name: str = "",
    event_type: str = "",
    limit: int = 20,
) -> list:
    """Query recent events from a workspace's history.

    event_type is one of: user_message, assistant_message, tool_use, session_end.
    Empty string for agent_name/event_type means no filter. Empty workspace_id
    falls back to the user's default workspace, or personal memory if none set.
    """
    ws = workspace_id or _default_workspace()
    if workspace_id and not _valid_id(ws):
        return []
    limit = max(1, min(limit, 200))
    with _client() as c:
        return c.query_events(
            ws or None,
            agent_name=agent_name or None,
            event_type=event_type or None,
            limit=limit,
        )


@mcp.tool()
def search_history(query: str, workspace_id: str = "", limit: int = 20) -> list:
    """Full-text search across history events in the given workspace.

    Empty workspace_id falls back to default workspace, then personal memory.
    """
    ws = workspace_id or _default_workspace()
    if workspace_id and not _valid_id(ws):
        return []
    limit = max(1, min(limit, 200))
    query = query[:2000]
    with _client() as c:
        return c.search_events(ws or None, query, limit=limit)


@mcp.tool()
def list_all_history_events(
    agent_name: str = "",
    event_type: str = "",
    limit: int = 20,
) -> list:
    """Cross-workspace events across every workspace + personal memory the user can see."""
    limit = max(1, min(limit, 200))
    with _client() as c:
        return c.list_all_history_events(
            agent_name=agent_name or None,
            event_type=event_type or None,
            limit=limit,
        )


if __name__ == "__main__":
    mcp.run()
