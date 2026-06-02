"""MCP server exposing Stash workspace tools to any MCP client."""

import json

from mcp.server.fastmcp import FastMCP

from cli.client import CartridgeClient, stash_permissions_for_access
from cli.config import load_config, load_manifest

mcp = FastMCP("stash", instructions="Stash — shared memory for AI coding agents")


def _client() -> tuple[CartridgeClient, str]:
    """Build a CartridgeClient + resolve the active workspace id."""
    cfg = load_config()
    client = CartridgeClient(cfg["base_url"], cfg.get("api_key", ""))
    manifest = load_manifest()
    ws_id = (manifest or {}).get("workspace_id", "")
    return client, ws_id


def _require_ws(ws_id: str | None) -> str:
    if not ws_id:
        raise ValueError("No workspace. Pass workspace_id or run `stash connect` in a repo first.")
    return ws_id


def _json(obj: object) -> str:
    return json.dumps(obj, default=str)


# ── Sources (unified VFS) + search ─────────────────────────────────


@mcp.tool()
def stash_search(query: str, source: str = "", limit: int = 20, workspace_id: str = "") -> str:
    """Search across all your sources — native files + session transcripts +
    connected sources (GitHub/Drive/Notion/Slack/Granola).

    Pass `source` to scope to one (a handle from stash_list_sources: 'files',
    'sessions', or a connected-source id); omit it to search everything.
    """
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.search_sources(ws, query, source=source or None, limit=limit))


@mcp.tool()
def stash_list_sources(workspace_id: str = "") -> str:
    """List every source you can read here: native 'files' and 'sessions', plus
    your connected sources. Use a returned `source` handle with the browse /
    read / search tools."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_sources(ws))


@mcp.tool()
def stash_browse_source(source: str, path: str = "", workspace_id: str = "") -> str:
    """List a source's entries like a file system. `source` is a handle from
    stash_list_sources; `path` is an optional path prefix for connected sources."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_source_entries(ws, source, path=path))


@mcp.tool()
def stash_read_source(source: str, ref: str, workspace_id: str = "") -> str:
    """Read one document from a source. `ref` is a page id (files), a session id
    (sessions), or a document path (connected sources)."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.read_source_doc(ws, source, ref))


@mcp.tool()
def stash_add_source(
    source_type: str,
    external_ref: str = "",
    display_name: str = "",
    workspace_id: str = "",
) -> str:
    """Connect a source. source_type: github_repo | google_drive | notion |
    slack | granola. Slack/Granola resolve external_ref from your connected
    token; the rest need an external_ref (e.g. a repo 'owner/name')."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(
        client.add_source(
            ws, source_type, external_ref=external_ref or None, display_name=display_name or None
        )
    )


@mcp.tool()
def stash_sync_source(source_id: str, workspace_id: str = "") -> str:
    """Trigger an immediate re-index of a connected source you own."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.sync_source(ws, source_id))


@mcp.tool()
def stash_remove_source(source_id: str, workspace_id: str = "") -> str:
    """Disconnect a source you own (its indexed documents cascade away)."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_source(ws, source_id)
    return _json({"deleted": source_id})


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
    default_cartridge_id: str = "",
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
            default_cartridge_id=default_cartridge_id or None,
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
    """Upload a local file to the workspace.

    Markdown (.md/.markdown/.mdx) and HTML (.html/.htm) become editable
    pages; everything else becomes a binary file. Response shape:
    `{kind: "file"|"page", id, name, app_url, ...}` — branch on `kind` if
    you care, otherwise `app_url` is the link to hand back to the user.
    """
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


# ── Cartridges ───────────────────────────────────────────────


@mcp.tool()
def stash_list_stashes(workspace_id: str = "") -> str:
    """List Cartridges in the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_stashes(ws))


@mcp.tool()
def stash_create_cartridge(
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
            client.publish_cartridge(
                ws,
                title,
                description=description,
                discoverable=discoverable,
                items=item_list,
            )
        )
    return _json(
        client.create_cartridge(
            ws,
            title,
            description=description,
            **stash_permissions_for_access(access),
            discoverable=discoverable,
            items=item_list,
        )
    )


@mcp.tool()
def stash_update_cartridge(
    cartridge_id: str,
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
    return _json(client.update_cartridge(cartridge_id, **fields))


@mcp.tool()
def stash_delete_cartridge(cartridge_id: str) -> str:
    """Delete a Stash."""
    client, _ = _client()
    client.delete_cartridge(cartridge_id)
    return _json({"deleted": cartridge_id})


@mcp.tool()
def stash_get_cartridge(slug: str) -> str:
    """Get a public Stash by its slug."""
    client, _ = _client()
    return _json(client.get_public_cartridge(slug))


@mcp.tool()
def stash_add_external_cartridge(slug: str, workspace_id: str = "") -> str:
    """Fork an external Stash into a workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.add_external_cartridge(slug, ws))


@mcp.tool()
def stash_remove_external_cartridge(cartridge_id: str, workspace_id: str = "") -> str:
    """Remove a forked external Stash from a workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.remove_external_cartridge(ws, cartridge_id)
    return _json({"removed": cartridge_id})


# ── Invites ───────────────────────────────────────────────────────


@mcp.tool()
def stash_list_invites(workspace_id: str = "") -> str:
    """List active invite tokens for the workspace."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_invite_tokens(ws))


@mcp.tool()
def stash_create_invite(
    workspace_id: str = "",
    max_uses: int = 1,
    ttl_days: int = 7,
) -> str:
    """Create an invite token. Returns the shareable URL + token id."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.create_invite_token(ws, max_uses=max_uses, ttl_days=ttl_days))


@mcp.tool()
def stash_revoke_invite(token_id: str, workspace_id: str = "") -> str:
    """Revoke an active invite token by id."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.revoke_invite_token(ws, token_id)
    return _json({"revoked": token_id})


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


# ── Discover (public Stash catalog) ───────────────────────────────


@mcp.tool()
def stash_search_public_stashes(query: str = "", sort: str = "trending") -> str:
    """Search the public Stash catalog (Discover).

    sort: trending | newest | popular. Pass an empty query to browse by
    sort order. Returns the catalog entries — fork into a workspace with
    stash_add_external_cartridge to follow up.
    """
    client, _ = _client()
    return _json(client.list_discover_stashes(query=query, sort=sort))


@mcp.tool()
def stash_read_public_cartridge(slug: str) -> str:
    """Fetch a public Stash by slug as plain text (markdown-formatted
    transcript + pages). Use this instead of WebFetch for joinstash.ai/v/
    or any /cartridges/<slug> URL."""
    client, _ = _client()
    return client.get_cartridge_text(slug)


# ── Sessions: full surface (transcript + soft-delete) ─────────────


@mcp.tool()
def stash_session_transcript(session_id: str, workspace_id: str = "") -> str:
    """Fetch a full session transcript as JSONL text. Each line is one
    event from the session in chronological order."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return client.export_transcript_jsonl(ws, session_id)


@mcp.tool()
def stash_delete_session(session_row_id: str, workspace_id: str = "") -> str:
    """Soft-delete a session. Use stash_restore(kind='session', id=...) to
    bring it back, or stash_purge(kind='session', ...) to delete forever."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    client.delete_session(ws, session_row_id)
    return _json({"deleted": session_row_id})


# ── Stash access control ──────────────────────────────────────────


_STASH_ACCESS = {"private", "workspace", "public"}


@mcp.tool()
def stash_set_cartridge_access(
    cartridge_id: str,
    access: str = "workspace",
    discoverable: bool = False,
) -> str:
    """Change a Stash's access level. access: private | workspace | public.
    `discoverable=True` lists the Stash in the public Discover catalog (only
    meaningful with access='public')."""
    if access not in _STASH_ACCESS:
        raise ValueError(f"access must be one of {sorted(_STASH_ACCESS)}")
    if discoverable and access != "public":
        raise ValueError("discoverable=True requires access='public'")
    client, _ = _client()
    fields: dict = {
        "access": access,
        "public_permission": "read" if access == "public" else "none",
        "workspace_permission": "read" if access in {"workspace", "public"} else "none",
        "discoverable": discoverable,
    }
    return _json(client.update_cartridge(cartridge_id, **fields))


# ── Tables: rename + export ───────────────────────────────────────


@mcp.tool()
def stash_update_table(
    table_id: str,
    workspace_id: str = "",
    name: str = "",
    description: str = "",
) -> str:
    """Rename or update a table's metadata. Omit a field to leave it
    unchanged."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    fields = {k: v for k, v in {"name": name, "description": description}.items() if v}
    if not fields:
        raise ValueError("pass at least one of name/description")
    return _json(client.update_table(ws, table_id, **fields))


@mcp.tool()
def stash_export_table(table_id: str, workspace_id: str = "") -> str:
    """Return all rows of a table as JSON. For large tables prefer
    paginated stash_query_table calls."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.list_table_rows(ws, table_id, limit=10000, offset=0))


# ── Trash ─────────────────────────────────────────────────────────


_TRASH_KINDS = {"page", "file", "session"}


@mcp.tool()
def stash_list_trash(workspace_id: str = "") -> str:
    """List soft-deleted pages, files, and sessions. Items can be restored or purged."""
    client, default_ws = _client()
    ws = _require_ws(workspace_id or default_ws)
    return _json(client.get_trash(ws))


@mcp.tool()
def stash_restore(kind: str, id: str, workspace_id: str = "") -> str:
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
def stash_purge(kind: str, id: str, workspace_id: str = "") -> str:
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
