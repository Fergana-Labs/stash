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


def _json(obj: object) -> str:
    return json.dumps(obj, default=str)


# ── History / search ──────────────────────────────────────────────


@mcp.tool()
def stash_search(query: str, limit: int = 20, workspace_id: str = "") -> str:
    """Full-text + semantic search across workspace history events."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.search_events(ws, query, limit=limit))


@mcp.tool()
def stash_query_events(
    limit: int = 20,
    agent_name: str = "",
    event_type: str = "",
    workspace_id: str = "",
) -> str:
    """Query recent history events, optionally filtered by agent or event type."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.query_events(
        ws,
        agent_name=agent_name or None,
        event_type=event_type or None,
        limit=limit,
    ))


@mcp.tool()
def stash_list_agents(workspace_id: str = "") -> str:
    """List distinct agent names that have pushed events to the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_agent_names(ws))


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
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.push_event(
        ws,
        agent_name=agent_name,
        event_type=event_type,
        content=content,
        session_id=session_id or None,
        tool_name=tool_name or None,
    ))


# ── Notebooks ─────────────────────────────────────────────────────


@mcp.tool()
def stash_list_notebooks(workspace_id: str = "") -> str:
    """List notebooks in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_notebooks(ws))


@mcp.tool()
def stash_create_notebook(name: str, description: str = "", workspace_id: str = "") -> str:
    """Create a new notebook in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.create_notebook(ws, name, description=description))


@mcp.tool()
def stash_delete_notebook(notebook_id: str, workspace_id: str = "") -> str:
    """Delete a notebook from the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_notebook(ws, notebook_id)
    return _json({"deleted": notebook_id})


@mcp.tool()
def stash_list_pages(notebook_id: str, workspace_id: str = "") -> str:
    """List pages in a notebook."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_page_tree(ws, notebook_id))


@mcp.tool()
def stash_read_page(notebook_id: str, page_id: str, workspace_id: str = "") -> str:
    """Read the content of a notebook page."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_page(ws, notebook_id, page_id))


@mcp.tool()
def stash_create_page(
    notebook_id: str,
    name: str,
    content: str = "",
    workspace_id: str = "",
) -> str:
    """Create a new page in a notebook."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.create_page(ws, notebook_id, name=name, content=content))


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
    ws = _require_ws(workspace_id or default_ws)
    kwargs: dict = {"content": content}
    if name:
        kwargs["name"] = name
    return _json(client.update_page(ws, notebook_id, page_id, **kwargs))


@mcp.tool()
def stash_delete_page(notebook_id: str, page_id: str, workspace_id: str = "") -> str:
    """Delete a page from a notebook."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_page(ws, notebook_id, page_id)
    return _json({"deleted": page_id})


# ── Tables ────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_tables(workspace_id: str = "") -> str:
    """List tables in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_tables(ws))


@mcp.tool()
def stash_create_table(
    name: str,
    description: str = "",
    columns: str = "[]",
    workspace_id: str = "",
) -> str:
    """Create a new table. columns is a JSON array of {name, type} objects."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    cols = json.loads(columns) if isinstance(columns, str) else columns
    return _json(client.create_table(ws, name, description=description, columns=cols))


@mcp.tool()
def stash_delete_table(table_id: str, workspace_id: str = "") -> str:
    """Delete a table from the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_table(ws, table_id)
    return _json({"deleted": table_id})


@mcp.tool()
def stash_table_schema(table_id: str, workspace_id: str = "") -> str:
    """Get a table's schema (columns and types)."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_table(ws, table_id))


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
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_table_rows(
        ws, table_id,
        limit=limit, offset=offset,
        sort_by=sort_by, sort_order=sort_order,
        filters=filters,
    ))


@mcp.tool()
def stash_insert_row(table_id: str, data: str, workspace_id: str = "") -> str:
    """Insert a row into a table. data is a JSON object mapping column names to values."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    row_data = json.loads(data) if isinstance(data, str) else data
    return _json(client.insert_table_row(ws, table_id, row_data))


@mcp.tool()
def stash_update_row(table_id: str, row_id: str, data: str, workspace_id: str = "") -> str:
    """Update a row in a table. data is a JSON object of column values to update."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    row_data = json.loads(data) if isinstance(data, str) else data
    return _json(client.update_table_row(ws, table_id, row_id, row_data))


@mcp.tool()
def stash_delete_row(table_id: str, row_id: str, workspace_id: str = "") -> str:
    """Delete a row from a table."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_table_row(ws, table_id, row_id)
    return _json({"deleted": row_id})


@mcp.tool()
def stash_add_column(
    table_id: str,
    name: str,
    col_type: str = "text",
    options: str = "[]",
    workspace_id: str = "",
) -> str:
    """Add a column to a table. col_type: text, number, boolean, date, select, url."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    opts = json.loads(options) if isinstance(options, str) else options
    return _json(client.add_table_column(ws, table_id, name, col_type=col_type, options=opts or None))


@mcp.tool()
def stash_delete_column(table_id: str, column_id: str, workspace_id: str = "") -> str:
    """Delete a column from a table."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.delete_table_column(ws, table_id, column_id))


# ── Workspaces ────────────────────────────────────────────────────


@mcp.tool()
def stash_list_workspaces() -> str:
    """List workspaces you are a member of."""
    client, _ = _client()
    return _json(client.list_workspaces(mine=True))


@mcp.tool()
def stash_workspace_info(workspace_id: str = "") -> str:
    """Get detailed info about a workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_workspace(ws))


@mcp.tool()
def stash_create_workspace(name: str, description: str = "", is_public: bool = False) -> str:
    """Create a new workspace."""
    client, _ = _client()
    return _json(client.create_workspace(name, description=description, is_public=is_public))


@mcp.tool()
def stash_workspace_members(workspace_id: str = "") -> str:
    """List members of a workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.workspace_members(ws))


@mcp.tool()
def stash_join_workspace(invite_code: str) -> str:
    """Join a workspace using an invite code."""
    client, _ = _client()
    return _json(client.join_workspace(invite_code))


@mcp.tool()
def stash_leave_workspace(workspace_id: str) -> str:
    """Leave a workspace."""
    client, _ = _client()
    client.leave_workspace(workspace_id)
    return _json({"left": workspace_id})


@mcp.tool()
def stash_fork_workspace(workspace_id: str, name: str = "") -> str:
    """Fork a public workspace into your account."""
    client, _ = _client()
    return _json(client.fork_workspace(workspace_id, name=name))


# ── Files ─────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_files(workspace_id: str = "") -> str:
    """List files uploaded to the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_ws_files(ws))


@mcp.tool()
def stash_file_text(file_id: str, workspace_id: str = "") -> str:
    """Extract text content from a workspace file (PDF, doc, etc.)."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_ws_file_text(ws, file_id))


@mcp.tool()
def stash_upload_file(file_path: str, workspace_id: str = "") -> str:
    """Upload a local file to the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.upload_ws_file(ws, file_path))


@mcp.tool()
def stash_delete_file(file_id: str, workspace_id: str = "") -> str:
    """Delete a file from the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_ws_file(ws, file_id)
    return _json({"deleted": file_id})


# ── Views ─────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_views(workspace_id: str = "") -> str:
    """List views in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_views(ws))


@mcp.tool()
def stash_create_view(
    title: str,
    description: str = "",
    is_public: bool = False,
    items: str = "[]",
    workspace_id: str = "",
) -> str:
    """Create a curated view. items is a JSON array of object references."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    item_list = json.loads(items) if isinstance(items, str) else items
    return _json(client.create_view(ws, title, description=description, is_public=is_public, items=item_list))


@mcp.tool()
def stash_delete_view(view_id: str) -> str:
    """Delete a view."""
    client, _ = _client()
    client.delete_view(view_id)
    return _json({"deleted": view_id})


@mcp.tool()
def stash_get_view(slug: str) -> str:
    """Get a public view by its slug."""
    client, _ = _client()
    return _json(client.get_public_view(slug))


@mcp.tool()
def stash_fork_view(slug: str, name: str = "") -> str:
    """Fork a view into your workspace."""
    client, _ = _client()
    return _json(client.fork_view(slug, name=name))


# ── Invites ───────────────────────────────────────────────────────


@mcp.tool()
def stash_create_invite(max_uses: int = 1, ttl_days: int = 7, workspace_id: str = "") -> str:
    """Create an invite token for the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.create_invite_token(ws, max_uses=max_uses, ttl_days=ttl_days))


@mcp.tool()
def stash_list_invites(workspace_id: str = "") -> str:
    """List active invite tokens for the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_invite_tokens(ws))


@mcp.tool()
def stash_revoke_invite(token_id: str, workspace_id: str = "") -> str:
    """Revoke an invite token."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.revoke_invite_token(ws, token_id)
    return _json({"revoked": token_id})


# ── Decks ─────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_decks(workspace_id: str = "") -> str:
    """List decks in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_decks(ws))


@mcp.tool()
def stash_create_deck(
    name: str,
    description: str = "",
    html_content: str = "",
    deck_type: str = "freeform",
    workspace_id: str = "",
) -> str:
    """Create a new deck in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.create_deck(ws, name, description=description, html_content=html_content, deck_type=deck_type))


@mcp.tool()
def stash_get_deck(deck_id: str, workspace_id: str = "") -> str:
    """Get a deck by ID."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_deck(ws, deck_id))


@mcp.tool()
def stash_update_deck(deck_id: str, updates: str = "{}", workspace_id: str = "") -> str:
    """Update a deck. updates is a JSON object of fields to change."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    fields = json.loads(updates) if isinstance(updates, str) else updates
    return _json(client.update_deck(ws, deck_id, **fields))


@mcp.tool()
def stash_delete_deck(deck_id: str, workspace_id: str = "") -> str:
    """Delete a deck from the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_deck(ws, deck_id)
    return _json({"deleted": deck_id})


# ── User ──────────────────────────────────────────────────────────


@mcp.tool()
def stash_whoami() -> str:
    """Get info about the currently authenticated user."""
    client, _ = _client()
    return _json(client.whoami())


# ── Entry point ───────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
