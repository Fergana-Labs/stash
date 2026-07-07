"""MCP server exposing Stash tools to any MCP client."""

import json

from mcp.server.fastmcp import FastMCP

from cli.client import StashClient
from cli.config import load_config

mcp = FastMCP("stash", instructions="Stash — shared memory for AI coding agents")


def _client() -> StashClient:
    cfg = load_config()
    return StashClient(cfg["base_url"], cfg.get("api_key", ""))


def _json(obj: object) -> str:
    return json.dumps(obj, default=str)


# ── Sources (unified VFS) + search ─────────────────────────────────


@mcp.tool()
def stash_search(query: str, source: str = "", limit: int = 20) -> str:
    """Search across all your sources — native files + session transcripts +
    connected sources (GitHub/Drive/Gmail/Notion/Slack/Granola).

    Pass `source` to scope to one (a handle from stash_list_sources: 'files',
    'sessions', or a connected-source id); omit it to search everything.
    """
    return _json(_client().search_sources(query, source=source or None, limit=limit))


@mcp.tool()
def stash_list_sources() -> str:
    """List every source you can read here: native 'files' and 'sessions', plus
    your connected sources. Use a returned `source` handle with the browse /
    read / search tools."""
    return _json(_client().list_sources())


@mcp.tool()
def stash_browse_source(source: str, path: str = "") -> str:
    """List a source's entries like a file system. `source` is a handle from
    stash_list_sources; `path` is an optional path prefix for connected sources."""
    return _json(_client().list_source_entries(source, path=path))


@mcp.tool()
def stash_read_source(source: str, ref: str) -> str:
    """Read one document from a source. `ref` is a page id (files), a session id
    (sessions), or a document path (connected sources)."""
    return _json(_client().read_source_doc(source, ref))


@mcp.tool()
def stash_add_source(
    source_type: str,
    external_ref: str = "",
    display_name: str = "",
) -> str:
    """Connect a source. source_type: github_repo | google_drive | gmail |
    notion | slack | granola. Slack/Granola resolve external_ref from your
    connected token; Gmail uses the mailbox email as external_ref."""
    return _json(
        _client().add_source(
            source_type, external_ref=external_ref or None, display_name=display_name or None
        )
    )


@mcp.tool()
def stash_sync_source(source_id: str) -> str:
    """Trigger an immediate re-index of a connected source you own."""
    return _json(_client().sync_source(source_id))


@mcp.tool()
def stash_remove_source(source_id: str) -> str:
    """Disconnect a source you own (its indexed documents cascade away)."""
    client = _client()
    client.delete_source(source_id)
    return _json({"deleted": source_id})


@mcp.tool()
def stash_query_events(
    limit: int = 20,
    agent_name: str = "",
    event_type: str = "",
) -> str:
    """Query recent session events, optionally filtered by agent or event type."""
    return _json(
        _client().query_events(
            agent_name=agent_name or None,
            event_type=event_type or None,
            limit=limit,
        )
    )


@mcp.tool()
def stash_list_agents() -> str:
    """List distinct agent names that have pushed events."""
    return _json(_client().list_agent_names())


@mcp.tool()
def stash_push_event(
    agent_name: str,
    event_type: str,
    content: str,
    session_id: str,
    tool_name: str = "",
) -> str:
    """Push a new event into a session's stream."""
    return _json(
        _client().push_event(
            agent_name=agent_name,
            event_type=event_type,
            content=content,
            session_id=session_id,
            tool_name=tool_name or None,
        )
    )


# ── Files: folders + pages ────────────────────────────────────────


@mcp.tool()
def stash_list_folders() -> str:
    """List your folders (flat)."""
    return _json(_client().list_folders())


@mcp.tool()
def stash_create_folder(
    name: str,
    parent_folder_id: str = "",
) -> str:
    """Create a folder. Pass parent_folder_id to nest."""
    return _json(_client().create_folder(name, parent_folder_id=parent_folder_id or None))


@mcp.tool()
def stash_edit_folder(
    folder_id: str,
    name: str = "",
    parent_folder_id: str = "",
    move_to_root: bool = False,
) -> str:
    """Rename and/or reparent a folder. Pass any subset of name / parent_folder_id / move_to_root."""
    return _json(
        _client().update_folder(
            folder_id,
            name=name or None,
            parent_folder_id=parent_folder_id or None,
            move_to_root=move_to_root,
        )
    )


@mcp.tool()
def stash_delete_folder(folder_id: str) -> str:
    """Delete a folder (and everything inside it)."""
    client = _client()
    client.delete_folder(folder_id)
    return _json({"deleted": folder_id})


@mcp.tool()
def stash_tree() -> str:
    """Nested folder/page tree for your scope."""
    return _json(_client().get_tree())


@mcp.tool()
def stash_list_pages() -> str:
    """Flat list of every page."""
    return _json(_client().list_pages())


@mcp.tool()
def stash_read_page(page_id: str) -> str:
    """Read a page's content."""
    return _json(_client().get_page(page_id))


@mcp.tool()
def stash_create_page(
    name: str,
    content: str = "",
    folder_id: str = "",
) -> str:
    """Create a page. Pass folder_id to drop it into a folder; omit for the root."""
    return _json(_client().create_page(name=name, content=content, folder_id=folder_id or None))


@mcp.tool()
def stash_edit_page(
    page_id: str,
    content: str,
    name: str = "",
) -> str:
    """Update an existing page's content (and optionally rename)."""
    kwargs: dict = {"content": content}
    if name:
        kwargs["name"] = name
    return _json(_client().update_page(page_id, **kwargs))


@mcp.tool()
def stash_delete_page(page_id: str) -> str:
    """Delete a page."""
    client = _client()
    client.delete_page(page_id)
    return _json({"deleted": page_id})


@mcp.tool()
def stash_copy_page(page_id: str, target_folder_id: str = "") -> str:
    """Duplicate a page as 'Copy of <name>'. Optionally place it in target_folder_id."""
    return _json(_client().copy_page(page_id, target_folder_id=target_folder_id or None))


@mcp.tool()
def stash_copy_folder(folder_id: str, target_folder_id: str = "") -> str:
    """Deep-duplicate a folder (subfolders, pages, tables, files) as 'Copy of <name>'."""
    return _json(_client().copy_folder(folder_id, target_folder_id=target_folder_id or None))


@mcp.tool()
def stash_copy_file(file_id: str, target_folder_id: str = "") -> str:
    """Duplicate an uploaded file (and its blob) as 'Copy of <name>'."""
    return _json(_client().copy_file(file_id, target_folder_id=target_folder_id or None))


@mcp.tool()
def stash_batch_move(
    items: list[dict],
    target_folder_id: str = "",
    move_to_root: bool = False,
) -> str:
    """Move many items at once. `items` is a list of {object_type, object_id}
    (object_type: page | file | folder | table). Best-effort: returns which
    moved and which failed."""
    return _json(
        _client().batch_move(
            items, target_folder_id=target_folder_id or None, move_to_root=move_to_root
        )
    )


@mcp.tool()
def stash_batch_delete(items: list[dict]) -> str:
    """Move many pages/files to the trash at once. `items` is a list of
    {object_type, object_id}. Best-effort."""
    return _json(_client().batch_delete(items))


@mcp.tool()
def stash_batch_restore(items: list[dict]) -> str:
    """Restore many pages/files from the trash at once. Best-effort."""
    return _json(_client().batch_restore(items))


# ── Tables ────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_tables() -> str:
    """List your tables."""
    return _json(_client().list_tables())


@mcp.tool()
def stash_create_table(
    name: str,
    description: str = "",
    columns: str = "[]",
) -> str:
    """Create a new table. columns is a JSON array of {name, type} objects."""
    cols = json.loads(columns) if isinstance(columns, str) else columns
    return _json(_client().create_table(name, description=description, columns=cols))


@mcp.tool()
def stash_delete_table(table_id: str) -> str:
    """Delete a table."""
    client = _client()
    client.delete_table(table_id)
    return _json({"deleted": table_id})


@mcp.tool()
def stash_table_schema(table_id: str) -> str:
    """Get a table's schema (columns and types)."""
    return _json(_client().get_table(table_id))


@mcp.tool()
def stash_query_table(
    table_id: str,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "",
    sort_order: str = "asc",
    filters: str = "",
) -> str:
    """Query rows from a table with optional sorting and filtering."""
    return _json(
        _client().list_table_rows(
            table_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters,
        )
    )


@mcp.tool()
def stash_insert_row(table_id: str, data: str) -> str:
    """Insert a row into a table. data is a JSON object mapping column names to values."""
    row_data = json.loads(data) if isinstance(data, str) else data
    return _json(_client().insert_table_row(table_id, row_data))


@mcp.tool()
def stash_update_row(table_id: str, row_id: str, data: str) -> str:
    """Update a row in a table. data is a JSON object of column values to update."""
    row_data = json.loads(data) if isinstance(data, str) else data
    return _json(_client().update_table_row(table_id, row_id, row_data))


@mcp.tool()
def stash_delete_row(table_id: str, row_id: str) -> str:
    """Delete a row from a table."""
    client = _client()
    client.delete_table_row(table_id, row_id)
    return _json({"deleted": row_id})


@mcp.tool()
def stash_add_column(
    table_id: str,
    name: str,
    col_type: str = "text",
    options: str = "[]",
) -> str:
    """Add a column to a table. col_type: text, number, boolean, date, select, url."""
    opts = json.loads(options) if isinstance(options, str) else options
    return _json(
        _client().add_table_column(table_id, name, col_type=col_type, options=opts or None)
    )


@mcp.tool()
def stash_delete_column(table_id: str, column_id: str) -> str:
    """Delete a column from a table."""
    return _json(_client().delete_table_column(table_id, column_id))


# ── Skills ─────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_skills() -> str:
    """List your skills. Each item carries the skill record under `skill`
    (id, slug, title, discoverable, view_count) and a `public` flag saying
    whether the skill's folder is publicly shared."""
    return _json(_client().list_skills())


@mcp.tool()
def stash_read_skill(folder_id: str) -> str:
    """Read a skill's contents (SKILL.md and sibling pages) by its folder id."""
    return _json(_client().get_skill_contents(folder_id))


# ── Files ─────────────────────────────────────────────────────────


@mcp.tool()
def stash_list_files() -> str:
    """List your uploaded files."""
    return _json(_client().list_files())


@mcp.tool()
def stash_file_text(file_id: str) -> str:
    """Extract text content from a file (PDF, doc, etc.)."""
    return _json(_client().get_file_text(file_id))


@mcp.tool()
def stash_upload_file(file_path: str) -> str:
    """Upload a local file.

    Markdown (.md/.markdown/.mdx) and HTML (.html/.htm) become editable
    pages; everything else becomes a binary file. Response shape:
    `{kind: "file"|"page", id, name, app_url, ...}` — branch on `kind` if
    you care, otherwise `app_url` is the link to hand back to the user.
    """
    return _json(_client().upload_file(file_path))


@mcp.tool()
def stash_edit_file(
    file_id: str,
    name: str = "",
    folder_id: str = "",
    move_to_root: bool = False,
) -> str:
    """Rename and/or move a file. Pass any subset of name / folder_id / move_to_root."""
    return _json(
        _client().update_file(
            file_id,
            name=name or None,
            folder_id=folder_id or None,
            move_to_root=move_to_root,
        )
    )


@mcp.tool()
def stash_delete_file(file_id: str) -> str:
    """Delete a file."""
    client = _client()
    client.delete_file(file_id)
    return _json({"deleted": file_id})


# ── Shared skills ───────────────────────────────────────────────


@mcp.tool()
def stash_create_skill(
    name: str,
    skill_md: str = "",
) -> str:
    """Create a skill: a folder with a SKILL.md, classified by a skill record
    (slug, title). Pass skill_md as the full SKILL.md content (frontmatter +
    body); a template is used when omitted. The skill starts private — make
    it public with stash_set_general_access on the returned folder_id."""
    client = _client()
    folder = client.create_folder(name)
    content = skill_md or f"---\nname: {name}\ndescription: \n---\n\n# {name}\n"
    client.create_page(
        name="SKILL.md", content=content, folder_id=folder["id"], content_type="markdown"
    )
    skill = client.create_skill_record(folder["id"])
    return _json({"folder_id": folder["id"], "name": name, "skill": skill})


@mcp.tool()
def stash_set_general_access(object_type: str, object_id: str, access: str) -> str:
    """Set link-level access on any resource: access is 'public' (anyone with
    the link can read) or 'restricted'. object_type: folder | page | file |
    table | session | session_folder | source. To make a skill public, set
    access on its folder. To share with one person instead, use
    stash_share_object."""
    return _json(_client().set_general_access(object_type, object_id, access))


@mcp.tool()
def stash_update_skill(
    skill_id: str,
    title: str = "",
    description: str = "",
    discoverable: str = "",
) -> str:
    """Update a skill's metadata or Discover flag."""
    fields: dict = {}
    if title:
        fields["title"] = title
    if description:
        fields["description"] = description
    if discoverable:
        fields["discoverable"] = discoverable.lower() in {"1", "true", "yes", "on"}
    if not fields:
        raise ValueError("Pass at least one field to update")
    return _json(_client().update_skill(skill_id, **fields))


@mcp.tool()
def stash_add_session_to_skill(session_id: str, folder_id: str) -> str:
    """Materialize a session transcript into a skill folder as a frozen
    snapshot page (re-running replaces it in place). session_id is the
    session's string id, not the row uuid."""
    return _json(_client().materialize_session(session_id, folder_id))


@mcp.tool()
def stash_get_shared_skill(slug: str) -> str:
    """Get a public shared skill by its slug."""
    return _json(_client().get_public_skill(slug))


@mcp.tool()
def stash_fork_skill(slug: str) -> str:
    """Fork a public Skill into your own scope."""
    return _json(_client().fork_skill(slug))


# ── User ──────────────────────────────────────────────────────────


@mcp.tool()
def stash_whoami() -> str:
    """Get info about the currently authenticated user."""
    return _json(_client().whoami())


# ── Sharing (Skill URLs + publish) ──────────────────


@mcp.tool()
def stash_publish_html(
    title: str,
    html: str,
    audience: str = "public",
    folder_id: str = "",
) -> str:
    """Single-call publish: create an HTML page, wrap it in a Skill, and return the Skill URL.

    If folder_id is omitted, a new skill folder named after the title is
    created. audience: 'private' or 'public'."""
    return _json(
        _client().publish(
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
    audience: str = "public",
    folder_id: str = "",
) -> str:
    """Single-call publish: create a markdown page, wrap it in a Skill, and return the Skill URL.
    Same flow as stash_publish_html but for markdown content."""
    return _json(
        _client().publish(
            title=title,
            content=markdown,
            content_type="markdown",
            audience=audience,
            folder_id=folder_id or None,
        )
    )


# ── Discover (public Skill catalog) ───────────────────────────────


@mcp.tool()
def stash_search_public_skills(query: str = "", sort: str = "trending") -> str:
    """Search the public Skill catalog (Discover).

    sort: trending | newest | popular. Pass an empty query to browse by
    sort order. Returns the catalog entries — fork into your scope with
    stash_fork_skill to follow up.
    """
    return _json(_client().list_discover_skills(query=query, sort=sort))


@mcp.tool()
def stash_read_public_skill(slug: str) -> str:
    """Fetch a public Skill by slug as plain text (markdown-formatted
    transcript + pages). Use this instead of WebFetch for joinstash.ai/v/
    or any /skills/<slug> URL."""
    return _client().get_skill_text(slug)


# ── Sessions: full surface (transcript + soft-delete) ─────────────


@mcp.tool()
def stash_session_transcript(session_id: str) -> str:
    """Fetch a full session transcript as JSONL text. Each line is one
    event from the session in chronological order."""
    return _client().export_transcript_jsonl(session_id)


@mcp.tool()
def stash_delete_session(session_row_id: str) -> str:
    """Soft-delete a session. Use stash_restore(kind='session', id=...) to
    bring it back, or stash_purge(kind='session', ...) to delete forever."""
    client = _client()
    client.delete_session(session_row_id)
    return _json({"deleted": session_row_id})


# ── Tables: rename + export ───────────────────────────────────────


@mcp.tool()
def stash_update_table(
    table_id: str,
    name: str = "",
    description: str = "",
) -> str:
    """Rename or update a table's metadata. Omit a field to leave it
    unchanged."""
    fields = {k: v for k, v in {"name": name, "description": description}.items() if v}
    if not fields:
        raise ValueError("pass at least one of name/description")
    return _json(_client().update_table(table_id, **fields))


@mcp.tool()
def stash_export_table(table_id: str) -> str:
    """Return all rows of a table as JSON. For large tables prefer
    paginated stash_query_table calls."""
    return _json(_client().list_table_rows(table_id, limit=10000, offset=0))


# ── Trash ─────────────────────────────────────────────────────────


_TRASH_KINDS = {"page", "file", "session"}


@mcp.tool()
def stash_list_trash() -> str:
    """List soft-deleted pages, files, and sessions. Items can be restored or purged."""
    return _json(_client().get_trash())


@mcp.tool()
def stash_restore(kind: str, id: str) -> str:
    """Restore a trashed page/file/session. `kind` is one of: page, file, session."""
    if kind not in _TRASH_KINDS:
        raise ValueError(f"kind must be one of {sorted(_TRASH_KINDS)}")
    client = _client()
    if kind == "page":
        client.restore_page(id)
    elif kind == "file":
        client.restore_file(id)
    else:
        client.restore_session(id)
    return _json({"ok": True, "kind": kind, "id": id})


@mcp.tool()
def stash_purge(kind: str, id: str) -> str:
    """Permanently delete a trashed page/file/session. Not reversible."""
    if kind not in _TRASH_KINDS:
        raise ValueError(f"kind must be one of {sorted(_TRASH_KINDS)}")
    client = _client()
    if kind == "page":
        client.purge_page(id)
    elif kind == "file":
        client.purge_file(id)
    else:
        client.purge_session(id)
    return _json({"ok": True, "kind": kind, "id": id})


# ── Object sharing (grant a person access by email) ───────────────


@mcp.tool()
def stash_share_object(
    object_type: str,
    object_id: str,
    email: str,
    permission: str = "read",
    expires_at: str = "",
) -> str:
    """Share a folder/page/file/session/table with a person by email. If they
    don't have an account yet the share is recorded as pending and converts when
    they sign up. permission: read | comment | write. expires_at: optional
    ISO-8601 timestamp after which the share lapses (omit = never)."""
    return _json(
        _client().share_object(
            object_type, object_id, email, permission=permission, expires_at=expires_at or None
        )
    )


@mcp.tool()
def stash_unshare_object(
    object_type: str, object_id: str, principal_type: str, principal_id: str
) -> str:
    """Revoke a share. principal_type is 'user' (principal_id is the user id from
    stash_list_shares)."""
    client = _client()
    client.unshare_object(object_type, object_id, principal_type, principal_id)
    return _json({"unshared": object_id})


@mcp.tool()
def stash_list_shares(object_type: str, object_id: str) -> str:
    """List who an object is shared with."""
    return _json(_client().list_object_shares(object_type, object_id))


@mcp.tool()
def stash_snapshot_source(skill_id: str, source_id: str, path: str) -> str:
    """Copy a point-in-time snapshot of one connected-source document (source_id
    + path from the source tools) into a Skill as a page, so the bundle stays
    self-contained."""
    return _json(_client().snapshot_source_into_skill(skill_id, source_id, path))


# ── Session folders ───────────────────────────────────────────────


@mcp.tool()
def stash_list_session_folders() -> str:
    """List session folders (shareable groupings of sessions)."""
    return _json(_client().list_session_folders())


@mcp.tool()
def stash_create_session_folder(name: str) -> str:
    """Create a session folder."""
    return _json(_client().create_session_folder(name))


@mcp.tool()
def stash_assign_session(session_row_id: str, folder_id: str = "") -> str:
    """Move a session into a session folder, or pass an empty folder_id to move
    it back to the ungrouped root."""
    return _json(_client().assign_session_folder(session_row_id, folder_id=folder_id or None))


# ── Entry point ───────────────────────────────────────────────────


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
