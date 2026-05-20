"""MCP server exposing Stash workspace tools to any MCP client."""

import json

from mcp.server.fastmcp import FastMCP

from cli.client import StashClient, stash_permissions_for_access
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
        raise ValueError("No workspace. Pass workspace_id or run `stash connect` in a repo first.")
    return ws_id


def _json(obj: object) -> str:
    return json.dumps(obj, default=str)


# ── Sessions / search ──────────────────────────────────────────────


@mcp.tool()
def stash_search(query: str, limit: int = 20, workspace_id: str = "") -> str:
    """Full-text + semantic search across workspace session events."""
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
    """Query recent session events, optionally filtered by agent or event type."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(
        client.query_events(
            ws,
            agent_name=agent_name or None,
            event_type=event_type or None,
            limit=limit,
        )
    )


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
    default_stash_id: str = "",
    tool_name: str = "",
    workspace_id: str = "",
) -> str:
    """Push a new event into workspace sessions."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(
        client.push_event(
            ws,
            agent_name=agent_name,
            event_type=event_type,
            content=content,
            session_id=session_id or None,
            default_stash_id=default_stash_id or None,
            tool_name=tool_name or None,
        )
    )


# ── Files: folders + pages ────────────────────────────────────────


@mcp.tool()
def stash_list_folders(workspace_id: str = "") -> str:
    """List folders in the workspace (flat)."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_folders(ws))


@mcp.tool()
def stash_create_folder(
    name: str,
    parent_folder_id: str = "",
    workspace_id: str = "",
) -> str:
    """Create a folder in the workspace. Pass parent_folder_id to nest."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.create_folder(ws, name, parent_folder_id=parent_folder_id or None))


@mcp.tool()
def stash_edit_folder(
    folder_id: str,
    name: str = "",
    parent_folder_id: str = "",
    move_to_root: bool = False,
    workspace_id: str = "",
) -> str:
    """Rename and/or reparent a folder. Pass any subset of name / parent_folder_id / move_to_root."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(
        client.update_folder(
            ws,
            folder_id,
            name=name or None,
            parent_folder_id=parent_folder_id or None,
            move_to_root=move_to_root,
        )
    )


@mcp.tool()
def stash_delete_folder(folder_id: str, workspace_id: str = "") -> str:
    """Delete a folder (and everything inside it) from the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_folder(ws, folder_id)
    return _json({"deleted": folder_id})


@mcp.tool()
def stash_workspace_tree(workspace_id: str = "") -> str:
    """Nested folder/page tree for the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_workspace_tree(ws))


@mcp.tool()
def stash_list_pages(workspace_id: str = "") -> str:
    """Flat list of every page in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_pages(ws))


@mcp.tool()
def stash_read_page(page_id: str, workspace_id: str = "") -> str:
    """Read a page's content."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_page(ws, page_id))


@mcp.tool()
def stash_create_page(
    name: str,
    content: str = "",
    folder_id: str = "",
    workspace_id: str = "",
) -> str:
    """Create a page. Pass folder_id to drop it into a folder; omit for the workspace root."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.create_page(ws, name=name, content=content, folder_id=folder_id or None))


@mcp.tool()
def stash_edit_page(
    page_id: str,
    content: str,
    name: str = "",
    workspace_id: str = "",
) -> str:
    """Update an existing page's content (and optionally rename)."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    kwargs: dict = {"content": content}
    if name:
        kwargs["name"] = name
    return _json(client.update_page(ws, page_id, **kwargs))


@mcp.tool()
def stash_delete_page(page_id: str, workspace_id: str = "") -> str:
    """Delete a page."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_page(ws, page_id)
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
    return _json(
        client.list_table_rows(
            ws,
            table_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters,
        )
    )


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
    return _json(
        client.add_table_column(ws, table_id, name, col_type=col_type, options=opts or None)
    )


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
    return _json(client.list_workspaces())


@mcp.tool()
def stash_workspace_info(workspace_id: str = "") -> str:
    """Get detailed info about a workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_workspace(ws))


@mcp.tool()
def stash_create_workspace(name: str, description: str = "") -> str:
    """Create a new workspace."""
    client, _ = _client()
    return _json(client.create_workspace(name, description=description))


@mcp.tool()
def stash_workspace_members(workspace_id: str = "") -> str:
    """List members of a workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.workspace_members(ws))


# ── Skills ─────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_skills(workspace_id: str = "") -> str:
    """List skills defined as Files folders with a SKILL.md page."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client._get(f"/api/v1/workspaces/{ws}/skills"))


@mcp.tool()
def stash_read_skill(name: str, workspace_id: str = "") -> str:
    """Read a skill's SKILL.md and sibling pages from Files."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client._get(f"/api/v1/workspaces/{ws}/skills/{name}"))


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
    """Upload a local file to the workspace. Returns a stable app_url for the user."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.upload_ws_file(ws, file_path))


@mcp.tool()
def stash_edit_file(
    file_id: str,
    name: str = "",
    folder_id: str = "",
    move_to_root: bool = False,
    workspace_id: str = "",
) -> str:
    """Rename and/or move a file. Pass any subset of name / folder_id / move_to_root."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(
        client.update_ws_file(
            ws,
            file_id,
            name=name or None,
            folder_id=folder_id or None,
            move_to_root=move_to_root,
        )
    )


@mcp.tool()
def stash_delete_file(file_id: str, workspace_id: str = "") -> str:
    """Delete a file from the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_ws_file(ws, file_id)
    return _json({"deleted": file_id})


# ── Stashes ───────────────────────────────────────────────


@mcp.tool()
def stash_list_stashes(workspace_id: str = "") -> str:
    """List Stashes in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_stashes(ws))


@mcp.tool()
def stash_create_stash(
    title: str,
    description: str = "",
    access: str = "workspace",
    discoverable: bool = False,
    items: str = "[]",
    workspace_id: str = "",
) -> str:
    """Create a Stash. items is a JSON array of object references."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    item_list = json.loads(items) if isinstance(items, str) else items
    if access == "public":
        return _json(
            client.publish_stash(
                ws,
                title,
                description=description,
                discoverable=discoverable,
                items=item_list,
            )
        )
    return _json(
        client.create_stash(
            ws,
            title,
            description=description,
            **stash_permissions_for_access(access),
            discoverable=discoverable,
            items=item_list,
        )
    )


@mcp.tool()
def stash_update_stash(
    stash_id: str,
    title: str = "",
    description: str = "",
    access: str = "",
    discoverable: str = "",
    items: str = "",
) -> str:
    """Update a Stash's metadata, access, Discover flag, or item list."""
    client, _ = _client()
    fields: dict = {}
    if title:
        fields["title"] = title
    if description:
        fields["description"] = description
    if access:
        fields.update(stash_permissions_for_access(access))
    if discoverable:
        fields["discoverable"] = discoverable.lower() in {"1", "true", "yes", "on"}
    if items:
        fields["items"] = json.loads(items)
    if not fields:
        raise ValueError("Pass at least one field to update")
    return _json(client.update_stash(stash_id, **fields))


@mcp.tool()
def stash_delete_stash(stash_id: str) -> str:
    """Delete a Stash."""
    client, _ = _client()
    client.delete_stash(stash_id)
    return _json({"deleted": stash_id})


@mcp.tool()
def stash_get_stash(slug: str) -> str:
    """Get a public Stash by its slug."""
    client, _ = _client()
    return _json(client.get_public_stash(slug))


@mcp.tool()
def stash_add_external_stash(slug: str, workspace_id: str = "") -> str:
    """Fork an external Stash into a workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.add_external_stash(slug, ws))


@mcp.tool()
def stash_remove_external_stash(stash_id: str, workspace_id: str = "") -> str:
    """Remove a forked external Stash from a workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.remove_external_stash(ws, stash_id)
    return _json({"removed": stash_id})


# ── Invites ───────────────────────────────────────────────────────


@mcp.tool()
def stash_list_invites(workspace_id: str = "") -> str:
    """List active invite tokens for the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_invite_tokens(ws))


# ── User ──────────────────────────────────────────────────────────


@mcp.tool()
def stash_whoami() -> str:
    """Get info about the currently authenticated user."""
    client, _ = _client()
    return _json(client.whoami())


# ── Sharing (Stash URLs + publish) ──────────────────


@mcp.tool()
def stash_publish_html(
    title: str,
    html: str,
    workspace_id: str = "",
    audience: str = "public",
    folder_id: str = "",
) -> str:
    """Single-call publish: create an HTML page, wrap it in a Stash, and return the Stash URL.

    If folder_id is omitted, the page lands in the workspace's auto-created
    'AI Drafts' folder. audience: 'workspace', 'private', or 'public'."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(
        client.publish(
            workspace_id=ws,
            title=title,
            content=html,
            content_type="html",
            audience=audience,
            folder_id=folder_id or None,
        )
    )


@mcp.tool()
def stash_publish_markdown(
    title: str,
    markdown: str,
    workspace_id: str = "",
    audience: str = "public",
    folder_id: str = "",
) -> str:
    """Single-call publish: create a markdown page, wrap it in a Stash, and return the Stash URL.
    Same flow as stash_publish_html but for markdown content."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(
        client.publish(
            workspace_id=ws,
            title=title,
            content=markdown,
            content_type="markdown",
            audience=audience,
            folder_id=folder_id or None,
        )
    )


# ── Trash ─────────────────────────────────────────────────────────


_TRASH_KINDS = {"page", "file", "session"}


@mcp.tool()
def list_trash(workspace_id: str = "") -> str:
    """List soft-deleted pages, files, and sessions. Items can be restored or purged."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_trash(ws))


@mcp.tool()
def restore_object(kind: str, id: str, workspace_id: str = "") -> str:
    """Restore a trashed page/file/session. `kind` is one of: page, file, session."""
    if kind not in _TRASH_KINDS:
        raise ValueError(f"kind must be one of {sorted(_TRASH_KINDS)}")
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    if kind == "page":
        client.restore_page(ws, id)
    elif kind == "file":
        client.restore_ws_file(ws, id)
    else:
        client.restore_session(ws, id)
    return _json({"ok": True, "kind": kind, "id": id})


@mcp.tool()
def purge_object(kind: str, id: str, workspace_id: str = "") -> str:
    """Permanently delete a trashed page/file/session. Not reversible."""
    if kind not in _TRASH_KINDS:
        raise ValueError(f"kind must be one of {sorted(_TRASH_KINDS)}")
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    if kind == "page":
        client.purge_page(ws, id)
    elif kind == "file":
        client.purge_ws_file(ws, id)
    else:
        client.purge_session(ws, id)
    return _json({"ok": True, "kind": kind, "id": id})


# ── Entry point ───────────────────────────────────────────────────


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
