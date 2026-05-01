"""MCP server exposing Stash workspace tools to any MCP client."""

import json

from mcp.server.fastmcp import FastMCP

from cli.client import StashClient
from cli.config import load_config, load_manifest

mcp = FastMCP("stash", instructions="Stash — shared memory for AI coding agents")


def _client() -> tuple[StashClient, str]:
    """Build a StashClient + resolve the active workspace id."""
    cfg = load_config()
    client = StashClient(cfg["base_url"], cfg.get("api_key", ""))
    manifest = load_manifest()
    ws_id = (manifest or {}).get("workspace_id", "")
    return client, ws_id


def _require_ws(ws_id: str | None) -> str:
    if not ws_id:
        raise ValueError(
            "No workspace. Pass workspace_id or run `stash connect` in a repo first."
        )
    return ws_id


# ── History / search ──────────────────────────────────────────────


@mcp.tool()
def stash_search(query: str, limit: int = 20, workspace_id: str = "") -> str:
    """Full-text + semantic search across workspace history events."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    results = client.search_events(ws, query, limit=limit)
    return json.dumps(results, default=str)


@mcp.tool()
def stash_query_events(
    limit: int = 20,
    agent_name: str = "",
    event_type: str = "",
    workspace_id: str = "",
) -> str:
    """Query recent history events, optionally filtered by agent or event type."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    results = client.query_events(
        ws,
        agent_name=agent_name or None,
        event_type=event_type or None,
        limit=limit,
    )
    return json.dumps(results, default=str)


@mcp.tool()
def stash_list_agents(workspace_id: str = "") -> str:
    """List distinct agent names that have pushed events to the workspace."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.list_agent_names(ws))


@mcp.tool()
def stash_push_event(
    agent_name: str,
    event_type: str,
    content: str,
    session_id: str = "",
    tool_name: str = "",
    workspace_id: str = "",
) -> str:
    """Push a new event into workspace history."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    result = client.push_event(
        ws,
        agent_name=agent_name,
        event_type=event_type,
        content=content,
        session_id=session_id or None,
        tool_name=tool_name or None,
    )
    return json.dumps(result, default=str)


# ── Notebooks ─────────────────────────────────────────────────────


@mcp.tool()
def stash_list_notebooks(workspace_id: str = "") -> str:
    """List notebooks in the workspace."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.list_notebooks(ws), default=str)


@mcp.tool()
def stash_list_pages(notebook_id: str, workspace_id: str = "") -> str:
    """List pages in a notebook."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.list_page_tree(ws, notebook_id), default=str)


@mcp.tool()
def stash_read_page(notebook_id: str, page_id: str, workspace_id: str = "") -> str:
    """Read the content of a notebook page."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.get_page(ws, notebook_id, page_id), default=str)


@mcp.tool()
def stash_create_page(
    notebook_id: str,
    name: str,
    content: str = "",
    workspace_id: str = "",
) -> str:
    """Create a new page in a notebook."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    result = client.create_page(ws, notebook_id, name=name, content=content)
    return json.dumps(result, default=str)


@mcp.tool()
def stash_edit_page(
    notebook_id: str,
    page_id: str,
    content: str,
    name: str = "",
    workspace_id: str = "",
) -> str:
    """Update an existing notebook page."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    kwargs: dict = {"content": content}
    if name:
        kwargs["name"] = name
    result = client.update_page(ws, notebook_id, page_id, **kwargs)
    return json.dumps(result, default=str)


# ── Tables ────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_tables(workspace_id: str = "") -> str:
    """List tables in the workspace."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.list_tables(ws), default=str)


@mcp.tool()
def stash_table_schema(table_id: str, workspace_id: str = "") -> str:
    """Get a table's schema (columns and types)."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.get_table(ws, table_id), default=str)


@mcp.tool()
def stash_query_table(
    table_id: str,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "",
    sort_order: str = "asc",
    filters: str = "",
    workspace_id: str = "",
) -> str:
    """Query rows from a table with optional sorting and filtering."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    result = client.list_table_rows(
        ws, table_id,
        limit=limit, offset=offset,
        sort_by=sort_by, sort_order=sort_order,
        filters=filters,
    )
    return json.dumps(result, default=str)


@mcp.tool()
def stash_insert_row(table_id: str, data: str, workspace_id: str = "") -> str:
    """Insert a row into a table. data is a JSON object mapping column names to values."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    row_data = json.loads(data) if isinstance(data, str) else data
    result = client.insert_table_row(ws, table_id, row_data)
    return json.dumps(result, default=str)


# ── Workspaces ────────────────────────────────────────────────────


@mcp.tool()
def stash_list_workspaces() -> str:
    """List workspaces you are a member of."""
    client, _ = _client()
    return json.dumps(client.list_workspaces(mine=True), default=str)


@mcp.tool()
def stash_workspace_info(workspace_id: str = "") -> str:
    """Get detailed info about a workspace."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.get_workspace(ws), default=str)


# ── Files ─────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_files(workspace_id: str = "") -> str:
    """List files uploaded to the workspace."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.list_ws_files(ws), default=str)


@mcp.tool()
def stash_file_text(file_id: str, workspace_id: str = "") -> str:
    """Extract text content from a workspace file (PDF, doc, etc.)."""
    client, default_ws = _client()
    ws = workspace_id or default_ws
    _require_ws(ws)
    return json.dumps(client.get_ws_file_text(ws, file_id), default=str)


# ── User ──────────────────────────────────────────────────────────


@mcp.tool()
def stash_whoami() -> str:
    """Get info about the currently authenticated user."""
    client, _ = _client()
    return json.dumps(client.whoami(), default=str)


# ── Entry point ───────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
