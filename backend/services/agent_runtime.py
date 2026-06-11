"""Claude Agent SDK runtime for ask-the-workspace.

Replaces the old hand-rolled agent harness (`backend/services/llm.py`).
The workspace tools are exposed as an in-process MCP server attached to
every call. Workspace scoping is handled through a ContextVar so each tool
implementation can find the active Stash Workspace without threading the id
through the SDK.

`stream_agent(...)` yields SSE-encoded chunks for the ask endpoint.
"""

from __future__ import annotations

import contextvars
import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from ..config import settings
from ..models import SkillItem
from . import (
    files_tree_service,
    memory_service,
    permission_service,
    prompts,
    shared_skill_service,
    skill_service,
    source_service,
    table_service,
)

logger = logging.getLogger(__name__)

_workspace_ctx: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "stash_workspace_id", default=None
)
_user_ctx: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "stash_user_id", default=None
)
# Best-effort edit provenance: which agent / session a tool call belongs to.
# Unset for surfaces that don't run inside a session (e.g. one-shot ask).
_session_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "stash_session_id", default=None
)
_agent_name_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "stash_agent_name", default=None
)


def _current_session() -> str | None:
    return _session_ctx.get()


def _current_agent_name() -> str | None:
    return _agent_name_ctx.get()


def _current_workspace() -> UUID:
    workspace_id = _workspace_ctx.get()
    if workspace_id is None:
        raise RuntimeError("agent_runtime: no workspace_id in context")
    return workspace_id


def _current_user() -> UUID:
    user_id = _user_ctx.get()
    if user_id is None:
        raise RuntimeError("agent_runtime: no user_id in context")
    return user_id


def _text_result(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _skill_item_to_dict(item: dict) -> dict:
    return {
        "object_type": item["object_type"],
        "object_id": str(item["object_id"]),
        "position": item["position"],
        "label_override": item.get("label_override"),
    }


def _skill_to_dict(skill: dict) -> dict:
    return {
        "id": str(skill["id"]),
        "workspace_id": str(skill["workspace_id"]),
        "slug": skill["slug"],
        "title": skill["title"],
        "description": skill["description"],
        "access": skill["access"],
        "workspace_permission": skill["workspace_permission"],
        "public_permission": skill["public_permission"],
        "discoverable": bool(skill["discoverable"]),
        "view_count": skill["view_count"],
        "items": [_skill_item_to_dict(item) for item in skill.get("items", [])],
        "created_at": str(skill["created_at"]),
        "updated_at": str(skill["updated_at"]),
    }


async def _parse_skill_items(raw_items: list[dict], workspace_id: UUID) -> list[SkillItem]:
    items = [SkillItem(**item) for item in raw_items]
    for item in items:
        item_workspace_id = await permission_service.resolve_workspace_id(
            item.object_type, item.object_id
        )
        if item_workspace_id != workspace_id:
            raise ValueError("Skill items must be in the active workspace")
    return items


# --- Tool implementations --------------------------------------------------


@tool(
    "search_history",
    "Full-text search across this Stash Workspace's agent transcripts and session events.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
)
async def _search_history(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    rows = await memory_service.search_workspace_events(
        workspace_id,
        user_id,
        args.get("query", ""),
        limit=int(args.get("limit", 10)),
    )
    out = [
        {
            "id": str(r["id"]),
            "agent": r.get("agent_name"),
            "session": r.get("session_id"),
            "content": (r.get("content") or "")[:400],
            "created_at": str(r.get("created_at")),
        }
        for r in rows
    ]
    return _text_result(json.dumps(out))


@tool(
    "read_page",
    "Read the full markdown body of a page by id.",
    {
        "type": "object",
        "properties": {"page_id": {"type": "string"}},
        "required": ["page_id"],
    },
)
async def _read_page(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    page = await files_tree_service.get_page(UUID(args["page_id"]), workspace_id, user_id)
    if not page:
        return _text_result(json.dumps({"error": "not found"}))
    return _text_result(
        json.dumps(
            {
                "id": str(page["id"]),
                "name": page["name"],
                "content": page.get("content_markdown") or page.get("content_html") or "",
            }
        )
    )


@tool(
    "grep_pages",
    "Full-text search across pages in this Stash Workspace. Returns page id + snippet.",
    {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["pattern"],
    },
)
async def _grep_pages(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    rows = await files_tree_service.search_pages_fts(
        workspace_id,
        args.get("pattern", ""),
        limit=int(args.get("limit", 10)),
        user_id=user_id,
    )
    out = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "snippet": (r.get("search_text") or r.get("content_markdown") or "")[:300],
        }
        for r in rows
    ]
    return _text_result(json.dumps(out))


@tool(
    "list_files",
    "List files (PDFs, docs, images) uploaded to this Stash Workspace.",
    {"type": "object", "properties": {}},
)
async def _list_files(args: dict) -> dict:
    from ..database import get_pool

    workspace_id = _current_workspace()
    user_id = _current_user()
    rows = await get_pool().fetch(
        "SELECT id, name, content_type, size_bytes FROM files WHERE workspace_id = $1 "
        "AND deleted_at IS NULL "
        "ORDER BY created_at DESC LIMIT 50",
        workspace_id,
    )
    visible_rows = []
    for row in rows:
        if await permission_service.check_access(
            "file",
            row["id"],
            user_id,
            workspace_id=workspace_id,
        ):
            visible_rows.append(row)
    out = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "content_type": r["content_type"],
            "size_bytes": r["size_bytes"],
        }
        for r in visible_rows
    ]
    return _text_result(json.dumps(out))


@tool(
    "read_file",
    "Read extracted text content from a Stash Workspace file by id.",
    {
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)
async def _read_file(args: dict) -> dict:
    from ..database import get_pool

    workspace_id = _current_workspace()
    user_id = _current_user()
    file_id = UUID(args["file_id"])
    row = await get_pool().fetchrow(
        "SELECT name, extracted_text FROM files "
        "WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL",
        file_id,
        workspace_id,
    )
    if not row:
        return _text_result(json.dumps({"error": "not found"}))
    if not await permission_service.check_access(
        "file",
        file_id,
        user_id,
        workspace_id=workspace_id,
    ):
        return _text_result(json.dumps({"error": "not found"}))
    return _text_result(
        json.dumps({"name": row["name"], "text": (row["extracted_text"] or "")[:6000]})
    )


@tool(
    "query_table",
    "List rows from a table by name. Returns the row payloads.",
    {
        "type": "object",
        "properties": {
            "table_name": {"type": "string"},
            "limit": {"type": "integer", "default": 50},
        },
        "required": ["table_name"],
    },
)
async def _query_table(args: dict) -> dict:
    from ..database import get_pool

    workspace_id = _current_workspace()
    user_id = _current_user()
    tables = await table_service.list_tables(workspace_id, user_id)
    match = next(
        (t for t in tables if t.get("name", "").lower() == args.get("table_name", "").lower()),
        None,
    )
    if not match:
        return _text_result(json.dumps({"error": "table not found"}))
    rows = await get_pool().fetch(
        "SELECT id, data FROM table_rows WHERE table_id = $1 ORDER BY row_order LIMIT $2",
        match["id"],
        int(args.get("limit", 50)),
    )
    out = [{"id": str(r["id"]), "data": r["data"]} for r in rows]
    return _text_result(json.dumps(out))


@tool(
    "list_skills",
    "List skills (folders with SKILL.md frontmatter) defined in this Stash Workspace.",
    {"type": "object", "properties": {}},
)
async def _list_skills(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    skills = await skill_service.list_skills(workspace_id, user_id)
    out = [
        {"name": s["name"], "description": s["description"], "files": s["file_count"]}
        for s in skills
    ]
    return _text_result(json.dumps(out))


@tool(
    "read_skill",
    "Read a skill by name — returns SKILL.md + sibling files concatenated.",
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
)
async def _read_skill(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    skill = await skill_service.read_skill(workspace_id, args.get("name", ""), user_id)
    if not skill:
        return _text_result(json.dumps({"error": "not found"}))
    return _text_result(json.dumps({"name": skill["name"], "combined": skill["combined"]}))


@tool(
    "list_shared_skills",
    "List Skills from the active Stash Workspace.",
    {"type": "object", "properties": {}},
)
async def _list_shared_skills(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    skills = await shared_skill_service.list_workspace_skills(workspace_id, user_id)
    return _text_result(json.dumps([_skill_to_dict(skill) for skill in skills]))


@tool(
    "create_shared_skill",
    "Create a shared skill — a publishable bundle of workspace items.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string", "default": ""},
            "workspace_permission": {
                "type": "string",
                "enum": ["none", "read", "write"],
                "default": "read",
            },
            "public_permission": {
                "type": "string",
                "enum": ["none", "read", "write"],
                "default": "none",
            },
            "discoverable": {"type": "boolean", "default": False},
            "items": {
                "type": "array",
                "default": [],
                "items": {
                    "type": "object",
                    "properties": {
                        "object_type": {
                            "type": "string",
                            "enum": ["folder", "page", "table", "file", "session"],
                        },
                        "object_id": {"type": "string"},
                        "position": {"type": "integer", "default": 0},
                        "label_override": {"type": "string"},
                    },
                    "required": ["object_type", "object_id"],
                },
            },
        },
        "required": ["title"],
    },
)
async def _create_shared_skill(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    workspace_permission = args.get("workspace_permission") or "read"
    public_permission = args.get("public_permission") or "none"
    discoverable = bool(args.get("discoverable", False))
    if discoverable and public_permission == "none":
        return _text_result(json.dumps({"error": "Discover Skills must be public"}))
    items = await _parse_skill_items(args.get("items") or [], workspace_id)
    skill = await shared_skill_service.create_skill(
        workspace_id=workspace_id,
        owner_id=user_id,
        title=args["title"],
        description=args.get("description") or "",
        workspace_permission=workspace_permission,
        public_permission=public_permission,
        discoverable=discoverable,
        cover_image_url=None,
        items=items,
    )
    return _text_result(json.dumps(_skill_to_dict(skill)))


@tool(
    "update_shared_skill",
    "Update a shared skill's metadata or replace its item list.",
    {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "workspace_permission": {
                "type": "string",
                "enum": ["none", "read", "write"],
            },
            "public_permission": {
                "type": "string",
                "enum": ["none", "read", "write"],
            },
            "discoverable": {"type": "boolean"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "object_type": {
                            "type": "string",
                            "enum": ["folder", "page", "table", "file", "session"],
                        },
                        "object_id": {"type": "string"},
                        "position": {"type": "integer", "default": 0},
                        "label_override": {"type": "string"},
                    },
                    "required": ["object_type", "object_id"],
                },
            },
        },
        "required": ["skill_id"],
    },
)
async def _update_shared_skill(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    skill_id = UUID(args["skill_id"])
    if not await shared_skill_service.user_can_manage(skill_id, user_id):
        return _text_result(json.dumps({"error": "not allowed"}))

    updates = {
        key: args[key]
        for key in (
            "title",
            "description",
            "workspace_permission",
            "public_permission",
            "discoverable",
        )
        if key in args
    }
    if "items" in args:
        updates["items"] = await _parse_skill_items(args.get("items") or [], workspace_id)
    skill = await shared_skill_service.update_skill(
        skill_id,
        user_id,
        updates,
    )
    if not skill:
        return _text_result(json.dumps({"error": "not found"}))
    return _text_result(json.dumps(_skill_to_dict(skill)))


@tool(
    "delete_shared_skill",
    "Delete a shared skill by id.",
    {
        "type": "object",
        "properties": {"skill_id": {"type": "string"}},
        "required": ["skill_id"],
    },
)
async def _delete_shared_skill(args: dict) -> dict:
    user_id = _current_user()
    skill_id = UUID(args["skill_id"])
    if not await shared_skill_service.user_can_manage(skill_id, user_id):
        return _text_result(json.dumps({"error": "not allowed"}))
    deleted = await shared_skill_service.delete_skill(skill_id, user_id)
    return _text_result(json.dumps({"deleted": deleted, "skill_id": str(skill_id)}))


# --- Source-aware tools ----------------------------------------------------
#
# One surface over every source: the two native sources (files, session
# transcripts — workspace-scoped) and the user's own connected sources
# (GitHub/Drive/Gmail/Notion/Slack/Granola — user-scoped). Connected-source access
# always goes through source_service.get_owned_source, which is the single
# user-scoping guard.


@tool(
    "list_sources",
    "List every source this user can read: native 'files' and 'sessions', plus "
    "their connected sources (GitHub, Drive, Gmail, Notion, Slack, Granola, Jira, Asana, "
    "Gong, Snowflake, Twitter). Each has a `capability`: 'navigable'/'searchable' sources "
    "use list_source / read_source / search; a 'queryable' source (Snowflake) uses "
    "query_source. Use the returned `source` handle with those tools.",
    {"type": "object", "properties": {}},
)
async def _list_sources(args: dict) -> dict:
    sources = await source_service.list_sources(_current_workspace(), _current_user())
    return _text_result(json.dumps(sources))


@tool(
    "list_source",
    "List entries in a source like a file system. `source` is a handle from "
    "list_sources ('files', 'sessions', or a connected-source id); `path` is an "
    "optional path prefix for connected sources.",
    {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "path": {"type": "string", "default": ""},
        },
        "required": ["source"],
    },
)
async def _list_source(args: dict) -> dict:
    entries = await source_service.source_entries(
        _current_workspace(), _current_user(), args.get("source", ""), prefix=args.get("path") or ""
    )
    if entries is None:
        return _text_result(json.dumps({"error": "source not found"}))
    return _text_result(json.dumps(entries))


@tool(
    "read_source",
    "Read one document from a source. `ref` is a page id (files), a session id "
    "(sessions), or a document path (connected sources).",
    {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "ref": {"type": "string"},
        },
        "required": ["source", "ref"],
    },
)
async def _read_source(args: dict) -> dict:
    source_ok, doc = await source_service.source_document(
        _current_workspace(), _current_user(), args.get("source", ""), args.get("ref", "")
    )
    if not source_ok:
        return _text_result(json.dumps({"error": "source not found"}))
    if doc is None:
        return _text_result(json.dumps({"error": "not found"}))
    return _text_result(json.dumps(doc))


@tool(
    "search",
    "Search across sources. Omit `source` to search everything the user can see "
    "(native files + sessions + their connected sources), or pass a source handle "
    "to scope to one. Twitter / X is only searched when explicitly scoped — its "
    "API quota is metered, so unscoped searches skip it. For a Twitter source, "
    "use list_source/read_source for personal refs (home, my-posts, bookmarks, "
    "likes, dms) and post expansion refs (thread:<id>, likers:<id>, "
    "reposters:<id>). Use scoped search with `from:handle` for recent public "
    "post search.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "source": {"type": "string"},
            "limit": {"type": "integer", "default": 20},
        },
        "required": ["query"],
    },
)
async def _search(args: dict) -> dict:
    results = await source_service.search_all(
        _current_workspace(),
        _current_user(),
        args.get("query", ""),
        source=args.get("source"),
        limit=int(args.get("limit", 20)),
    )
    if results is None:
        return _text_result(json.dumps({"error": "source not found"}))
    return _text_result(json.dumps(results))


@tool(
    "query_source",
    "Run a read-only SQL query against a queryable source (e.g. Snowflake). "
    "`source` is the handle from list_sources; use list_source to see its tables "
    "and read_source on a table to see its columns first. Only SELECT/WITH/SHOW/"
    "DESCRIBE/EXPLAIN are allowed and rows are capped.",
    {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "sql": {"type": "string"},
            "limit": {"type": "integer", "default": 200},
        },
        "required": ["source", "sql"],
    },
)
async def _query_source(args: dict) -> dict:
    result = await source_service.query_source(
        _current_workspace(),
        _current_user(),
        args.get("source", ""),
        args.get("sql", ""),
        limit=int(args.get("limit", 200)),
    )
    if result is None:
        return _text_result(json.dumps({"error": "source not found"}))
    return _text_result(json.dumps(result))


@tool(
    "fetch_history",
    "Pull OLDER data from a source for a time range, beyond what's already "
    "cached/searchable (Slack messages, Gong calls). Use when the user asks "
    "about something before the recent window. `since`/`until` are ISO-8601 "
    "dates (e.g. '2026-01-01'); until defaults to now. Fetched items are cached, "
    "so afterward you can find them with search/read_source.",
    {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "since": {"type": "string"},
            "until": {"type": "string"},
            "limit": {"type": "integer", "default": 500},
        },
        "required": ["source", "since"],
    },
)
async def _fetch_history(args: dict) -> dict:
    result = await source_service.fetch_history(
        _current_workspace(),
        _current_user(),
        args.get("source", ""),
        args.get("since", ""),
        until=args.get("until"),
        limit=int(args.get("limit", 500)),
    )
    if result is None:
        return _text_result(json.dumps({"error": "source not found"}))
    return _text_result(json.dumps(result))


@tool(
    "create_page",
    "Create a new page in the workspace. Use content_type 'markdown' with `content`, "
    "or 'html' with `content_html`. Returns the new page id.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "content_type": {
                "type": "string",
                "enum": ["markdown", "html"],
                "default": "markdown",
            },
            "content": {"type": "string", "default": ""},
            "content_html": {"type": "string", "default": ""},
            "folder_id": {"type": "string"},
        },
        "required": ["name"],
    },
)
async def _create_page(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    folder_id = UUID(args["folder_id"]) if args.get("folder_id") else None
    try:
        page = await files_tree_service.create_page(
            workspace_id=workspace_id,
            name=args["name"],
            created_by=user_id,
            folder_id=folder_id,
            content=args.get("content") or "",
            content_type=args.get("content_type") or "markdown",
            content_html=args.get("content_html") or "",
            edit_session_id=_current_session(),
            edit_agent_name=_current_agent_name(),
        )
    except files_tree_service.DuplicatePageName:
        return _text_result(json.dumps({"error": "a page with that name already exists here"}))
    except ValueError as e:
        return _text_result(json.dumps({"error": str(e)}))
    return _text_result(json.dumps({"id": str(page["id"]), "name": page["name"]}))


@tool(
    "update_page",
    "Update an existing page's content or name by id. Pass content_type 'markdown' with "
    "`content`, or 'html' with `content_html`. Omit a field to leave it unchanged.",
    {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"},
            "name": {"type": "string"},
            "content_type": {"type": "string", "enum": ["markdown", "html"]},
            "content": {"type": "string"},
            "content_html": {"type": "string"},
        },
        "required": ["page_id"],
    },
)
async def _update_page(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    page = await files_tree_service.update_page(
        page_id=UUID(args["page_id"]),
        workspace_id=workspace_id,
        updated_by=user_id,
        name=args.get("name"),
        content=args.get("content"),
        content_type=args.get("content_type"),
        content_html=args.get("content_html"),
        edit_session_id=_current_session(),
        edit_agent_name=_current_agent_name(),
    )
    if page is None:
        return _text_result(json.dumps({"error": "page not found"}))
    return _text_result(json.dumps({"id": str(page["id"]), "name": page["name"]}))


@tool(
    "edit_page",
    "Make a surgical edit to a page body instead of rewriting it whole. In "
    "'replace' mode `old_string` must appear exactly once in the page (it is "
    "replaced with `new_string`); in 'append' mode `new_string` is added to the "
    "end. Edits the active content (markdown or html) of the page.",
    {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"},
            "old_string": {"type": "string", "default": ""},
            "new_string": {"type": "string"},
            "mode": {"type": "string", "enum": ["replace", "append"], "default": "replace"},
        },
        "required": ["page_id", "new_string"],
    },
)
async def _edit_page(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    try:
        page = await files_tree_service.edit_page(
            page_id=UUID(args["page_id"]),
            workspace_id=workspace_id,
            updated_by=user_id,
            old_string=args.get("old_string") or "",
            new_string=args["new_string"],
            mode=args.get("mode") or "replace",
            edit_session_id=_current_session(),
            edit_agent_name=_current_agent_name(),
        )
    except files_tree_service.EditMatchError as e:
        return _text_result(
            json.dumps(
                {
                    "error": "no-unique-match",
                    "detail": f"old_string matched {e.count} times; it must match exactly once",
                }
            )
        )
    except files_tree_service.ConcurrentEditError:
        return _text_result(json.dumps({"error": "page changed during edit, read it and retry"}))
    if page is None:
        return _text_result(json.dumps({"error": "page not found"}))
    return _text_result(json.dumps({"id": str(page["id"]), "name": page["name"]}))


# --- Tree mutation tools (folders, pages, tables) --------------------------
#
# These wrap the same service functions the REST/MCP layer uses, so the in-app
# agent can organize the workspace, not just write page bodies. Operations on an
# existing object by id are workspace-scoped by the service WHERE clause (pages)
# or by an explicit guard (tables, which the service does not scope).


async def _table_in_workspace(table_id: UUID, workspace_id: UUID) -> bool:
    meta = await table_service.get_table_metadata(table_id)
    return bool(meta and meta["workspace_id"] == workspace_id)


@tool(
    "create_folder",
    "Create a folder in the workspace. Pass parent_folder_id to nest it.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "parent_folder_id": {"type": "string"},
        },
        "required": ["name"],
    },
)
async def _create_folder(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    parent_folder_id = UUID(args["parent_folder_id"]) if args.get("parent_folder_id") else None
    try:
        folder = await files_tree_service.create_folder(
            workspace_id, args["name"], user_id, parent_folder_id=parent_folder_id
        )
    except files_tree_service.DuplicateFolderName:
        return _text_result(json.dumps({"error": "a folder with that name already exists here"}))
    except ValueError as e:
        return _text_result(json.dumps({"error": str(e)}))
    return _text_result(json.dumps({"id": str(folder["id"]), "name": folder["name"]}))


@tool(
    "move_page",
    "Move a page into a folder, or to the workspace root with move_to_root.",
    {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"},
            "folder_id": {"type": "string"},
            "move_to_root": {"type": "boolean", "default": False},
        },
        "required": ["page_id"],
    },
)
async def _move_page(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    folder_id = UUID(args["folder_id"]) if args.get("folder_id") else None
    try:
        page = await files_tree_service.update_page(
            page_id=UUID(args["page_id"]),
            workspace_id=workspace_id,
            updated_by=user_id,
            folder_id=folder_id,
            move_to_root=bool(args.get("move_to_root", False)),
        )
    except ValueError as e:
        return _text_result(json.dumps({"error": str(e)}))
    if page is None:
        return _text_result(json.dumps({"error": "page not found"}))
    return _text_result(json.dumps({"id": str(page["id"]), "name": page["name"]}))


@tool(
    "rename_page",
    "Rename a page by id.",
    {
        "type": "object",
        "properties": {"page_id": {"type": "string"}, "name": {"type": "string"}},
        "required": ["page_id", "name"],
    },
)
async def _rename_page(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    try:
        page = await files_tree_service.update_page(
            page_id=UUID(args["page_id"]),
            workspace_id=workspace_id,
            updated_by=user_id,
            name=args["name"],
        )
    except files_tree_service.DuplicatePageName:
        return _text_result(json.dumps({"error": "a page with that name already exists here"}))
    if page is None:
        return _text_result(json.dumps({"error": "page not found"}))
    return _text_result(json.dumps({"id": str(page["id"]), "name": page["name"]}))


@tool(
    "delete_page",
    "Move a page to the trash (soft delete) by id.",
    {
        "type": "object",
        "properties": {"page_id": {"type": "string"}},
        "required": ["page_id"],
    },
)
async def _delete_page(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    deleted = await files_tree_service.delete_page(UUID(args["page_id"]), workspace_id, user_id)
    if not deleted:
        return _text_result(json.dumps({"error": "page not found"}))
    return _text_result(json.dumps({"deleted": True, "page_id": args["page_id"]}))


@tool(
    "create_table",
    "Create a table. `columns` is a list of {name, type} column definitions "
    "(type one of text, number, boolean, date, datetime, url, email, select, "
    "multiselect, json). Pass folder_id to place it in a folder.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string", "default": ""},
            "columns": {"type": "array", "items": {"type": "object"}, "default": []},
            "folder_id": {"type": "string"},
        },
        "required": ["name"],
    },
)
async def _create_table(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    folder_id = UUID(args["folder_id"]) if args.get("folder_id") else None
    try:
        table = await table_service.create_table(
            workspace_id,
            args["name"],
            args.get("description") or "",
            args.get("columns") or [],
            user_id,
            folder_id=folder_id,
        )
    except ValueError as e:
        return _text_result(json.dumps({"error": str(e)}))
    return _text_result(json.dumps({"id": str(table["id"]), "name": table["name"]}))


@tool(
    "insert_row",
    "Insert a row into a table. `data` maps column id/name to value.",
    {
        "type": "object",
        "properties": {
            "table_id": {"type": "string"},
            "data": {"type": "object"},
        },
        "required": ["table_id", "data"],
    },
)
async def _insert_row(args: dict) -> dict:
    workspace_id = _current_workspace()
    table_id = UUID(args["table_id"])
    if not await _table_in_workspace(table_id, workspace_id):
        return _text_result(json.dumps({"error": "table not found"}))
    row = await table_service.create_row(table_id, args.get("data") or {}, _current_user())
    return _text_result(json.dumps({"id": str(row["id"])}))


@tool(
    "update_row",
    "Update a table row (partial merge — only the keys you pass change).",
    {
        "type": "object",
        "properties": {
            "table_id": {"type": "string"},
            "row_id": {"type": "string"},
            "data": {"type": "object"},
        },
        "required": ["table_id", "row_id", "data"],
    },
)
async def _update_row(args: dict) -> dict:
    workspace_id = _current_workspace()
    table_id = UUID(args["table_id"])
    if not await _table_in_workspace(table_id, workspace_id):
        return _text_result(json.dumps({"error": "table not found"}))
    row = await table_service.update_row(
        UUID(args["row_id"]), args.get("data") or {}, _current_user(), table_id=table_id
    )
    if row is None:
        return _text_result(json.dumps({"error": "row not found"}))
    return _text_result(json.dumps({"id": str(row["id"])}))


@tool(
    "add_column",
    "Add a column to a table. `column` is a {name, type} definition.",
    {
        "type": "object",
        "properties": {
            "table_id": {"type": "string"},
            "column": {"type": "object"},
        },
        "required": ["table_id", "column"],
    },
)
async def _add_column(args: dict) -> dict:
    workspace_id = _current_workspace()
    table_id = UUID(args["table_id"])
    if not await _table_in_workspace(table_id, workspace_id):
        return _text_result(json.dumps({"error": "table not found"}))
    table = await table_service.add_column(table_id, args.get("column") or {}, _current_user())
    return _text_result(json.dumps({"id": str(table["id"]), "name": table["name"]}))


@tool(
    "delete_row",
    "Delete a row from a table by id.",
    {
        "type": "object",
        "properties": {
            "table_id": {"type": "string"},
            "row_id": {"type": "string"},
        },
        "required": ["table_id", "row_id"],
    },
)
async def _delete_row(args: dict) -> dict:
    workspace_id = _current_workspace()
    table_id = UUID(args["table_id"])
    if not await _table_in_workspace(table_id, workspace_id):
        return _text_result(json.dumps({"error": "table not found"}))
    deleted = await table_service.delete_row(UUID(args["row_id"]), table_id=table_id)
    if not deleted:
        return _text_result(json.dumps({"error": "row not found"}))
    return _text_result(json.dumps({"deleted": True, "row_id": args["row_id"]}))


@tool(
    "copy_page",
    "Duplicate a page as 'Copy of <name>'. Pass target_folder_id to place the "
    "copy in a specific folder (defaults to the source's folder).",
    {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"},
            "target_folder_id": {"type": "string"},
        },
        "required": ["page_id"],
    },
)
async def _copy_page(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    target = UUID(args["target_folder_id"]) if args.get("target_folder_id") else None
    page = await files_tree_service.copy_page(
        UUID(args["page_id"]), workspace_id, user_id, target_folder_id=target
    )
    if page is None:
        return _text_result(json.dumps({"error": "page not found"}))
    return _text_result(json.dumps({"id": str(page["id"]), "name": page["name"]}))


@tool(
    "copy_folder",
    "Deep-duplicate a folder (its subfolders, pages, and tables) as "
    "'Copy of <name>'. Pass target_parent_id to nest the copy under another folder.",
    {
        "type": "object",
        "properties": {
            "folder_id": {"type": "string"},
            "target_parent_id": {"type": "string"},
        },
        "required": ["folder_id"],
    },
)
async def _copy_folder(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    target = UUID(args["target_parent_id"]) if args.get("target_parent_id") else None
    try:
        folder = await files_tree_service.copy_folder(
            UUID(args["folder_id"]), workspace_id, user_id, target_parent_id=target
        )
    except files_tree_service.FolderCycle as e:
        return _text_result(json.dumps({"error": str(e)}))
    if folder is None:
        return _text_result(json.dumps({"error": "folder not found"}))
    return _text_result(json.dumps({"id": str(folder["id"]), "name": folder["name"]}))


_BATCH_ITEMS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "object_type": {
                "type": "string",
                "enum": ["page", "file", "folder", "table"],
            },
            "object_id": {"type": "string"},
        },
        "required": ["object_type", "object_id"],
    },
}


@tool(
    "batch_move",
    "Move many items at once into a folder (or to the root with move_to_root). "
    "Best-effort: returns which items moved and which failed. Items: pages, "
    "files, folders, tables.",
    {
        "type": "object",
        "properties": {
            "items": _BATCH_ITEMS_SCHEMA,
            "target_folder_id": {"type": "string"},
            "move_to_root": {"type": "boolean", "default": False},
        },
        "required": ["items"],
    },
)
async def _batch_move(args: dict) -> dict:
    from . import batch_service

    target = UUID(args["target_folder_id"]) if args.get("target_folder_id") else None
    result = await batch_service.batch_move(
        _current_workspace(),
        _current_user(),
        args.get("items") or [],
        target_folder_id=target,
        move_to_root=bool(args.get("move_to_root", False)),
    )
    return _text_result(json.dumps(result))


@tool(
    "batch_delete",
    "Move many pages/files to the trash at once (soft delete). Best-effort: "
    "returns which items were trashed and which failed.",
    {
        "type": "object",
        "properties": {"items": _BATCH_ITEMS_SCHEMA},
        "required": ["items"],
    },
)
async def _batch_delete(args: dict) -> dict:
    from . import batch_service

    result = await batch_service.batch_delete(
        _current_workspace(), _current_user(), args.get("items") or []
    )
    return _text_result(json.dumps(result))


@tool(
    "batch_restore",
    "Restore many pages/files from the trash at once. Best-effort: returns "
    "which items were restored and which failed.",
    {
        "type": "object",
        "properties": {"items": _BATCH_ITEMS_SCHEMA},
        "required": ["items"],
    },
)
async def _batch_restore(args: dict) -> dict:
    from . import batch_service

    result = await batch_service.batch_restore(
        _current_workspace(), _current_user(), args.get("items") or []
    )
    return _text_result(json.dumps(result))


_TOOLS_BY_NAME = {
    "search_history": _search_history,
    "read_page": _read_page,
    "create_page": _create_page,
    "update_page": _update_page,
    "edit_page": _edit_page,
    "create_folder": _create_folder,
    "move_page": _move_page,
    "rename_page": _rename_page,
    "delete_page": _delete_page,
    "create_table": _create_table,
    "insert_row": _insert_row,
    "update_row": _update_row,
    "add_column": _add_column,
    "delete_row": _delete_row,
    "copy_page": _copy_page,
    "copy_folder": _copy_folder,
    "batch_move": _batch_move,
    "batch_delete": _batch_delete,
    "batch_restore": _batch_restore,
    "grep_pages": _grep_pages,
    "list_files": _list_files,
    "read_file": _read_file,
    "query_table": _query_table,
    "list_skills": _list_skills,
    "read_skill": _read_skill,
    "list_shared_skills": _list_shared_skills,
    "create_shared_skill": _create_shared_skill,
    "update_shared_skill": _update_shared_skill,
    "delete_shared_skill": _delete_shared_skill,
    "list_sources": _list_sources,
    "list_source": _list_source,
    "read_source": _read_source,
    "search": _search,
    "query_source": _query_source,
    "fetch_history": _fetch_history,
}


def _build_options(*, system: str) -> ClaudeAgentOptions:
    tools = [_TOOLS_BY_NAME[name] for name in prompts.STASH_TOOL_SET]
    mcp_server = create_sdk_mcp_server(name="stash", version="1.0.0", tools=tools)
    # The SDK exposes MCP tools as `mcp__{server}__{tool_name}` in allowed_tools.
    allowed = [f"mcp__stash__{name}" for name in prompts.STASH_TOOL_SET]
    return ClaudeAgentOptions(
        system_prompt=system,
        model=settings.ANTHROPIC_MODEL,
        max_turns=8,
        mcp_servers={"stash": mcp_server},
        allowed_tools=allowed,
        # No filesystem/Bash tools — purely the in-process MCP toolset.
        disallowed_tools=["Bash", "Edit", "Write", "Read", "Glob", "Grep"],
        # We pass full prompt as the user turn; no continuation needed.
        permission_mode="bypassPermissions",
        env={"ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY or ""},
    )


# --- Public API ------------------------------------------------------------


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_agent(
    *,
    system: str,
    prompt: str,
    workspace_id: UUID,
    user_id: UUID | None = None,
) -> AsyncIterator[str]:
    """SSE generator for ask-the-workspace. Caller must verify
    `settings.ANTHROPIC_API_KEY` is set before invoking."""
    options = _build_options(system=system)

    workspace_token = _workspace_ctx.set(workspace_id)
    user_token = _user_ctx.set(user_id)
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        yield _sse({"type": "text", "delta": block.text})
                    elif isinstance(block, ToolUseBlock):
                        # Strip the SDK's MCP prefix so the wire format
                        # stays readable in the UI.
                        name = block.name
                        if name.startswith("mcp__stash__"):
                            name = name[len("mcp__stash__") :]
                        yield _sse(
                            {
                                "type": "tool",
                                "name": name,
                                "args": dict(block.input or {}),
                            }
                        )
            elif isinstance(msg, ResultMessage):
                if msg.is_error and not msg.result:
                    yield _sse(
                        {
                            "type": "text",
                            "delta": f"\n\n(stream ended: {msg.subtype})",
                        }
                    )
            elif isinstance(msg, SystemMessage):
                # SDK init/system noise — drop.
                continue
    finally:
        _user_ctx.reset(user_token)
        _workspace_ctx.reset(workspace_token)

    yield _sse({"type": "end"})
