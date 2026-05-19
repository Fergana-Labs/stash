"""Claude Agent SDK runtime for ask-the-workspace and the session summarizer.

Replaces the old hand-rolled agent harness (`backend/services/llm.py`).
The workspace tools are exposed as an in-process MCP server attached to
every call. Workspace scoping is handled through a ContextVar so each tool
implementation can find the active Stash Workspace without threading the id
through the SDK.

Two call shapes:
- `run_agent(...)` aggregates the full query stream into an `AgentResult`
  (used by the session summarizer).
- `stream_agent(...)` yields SSE-encoded chunks for the ask endpoint.
"""

from __future__ import annotations

import contextvars
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
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
from ..models import StashItem
from . import (
    files_tree_service,
    memory_service,
    permission_service,
    skill_service,
    stash_service,
    table_service,
)

logger = logging.getLogger(__name__)

_workspace_ctx: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "stash_workspace_id", default=None
)
_user_ctx: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "stash_user_id", default=None
)


class ModelTier(StrEnum):
    QUALITY = "quality"
    FAST = "fast"


class LLMNotConfiguredError(RuntimeError):
    """Raised when an LLM call is attempted with ANTHROPIC_API_KEY unset."""


def _model_for(tier: ModelTier) -> str:
    if tier is ModelTier.QUALITY:
        return settings.ANTHROPIC_MODEL
    return settings.ANTHROPIC_FAST_MODEL


def _require_api_key() -> None:
    if not settings.ANTHROPIC_API_KEY:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY is not set")


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


def _stash_item_to_dict(item: dict) -> dict:
    return {
        "object_type": item["object_type"],
        "object_id": str(item["object_id"]),
        "position": item["position"],
        "label_override": item.get("label_override"),
    }


def _stash_to_dict(stash: dict) -> dict:
    return {
        "id": str(stash["id"]),
        "workspace_id": str(stash["workspace_id"]),
        "slug": stash["slug"],
        "title": stash["title"],
        "description": stash["description"],
        "access": stash["access"],
        "discoverable": bool(stash["discoverable"]),
        "view_count": stash["view_count"],
        "items": [_stash_item_to_dict(item) for item in stash.get("items", [])],
        "created_at": str(stash["created_at"]),
        "updated_at": str(stash["updated_at"]),
    }


async def _parse_stash_items(raw_items: list[dict], workspace_id: UUID) -> list[StashItem]:
    items = [StashItem(**item) for item in raw_items]
    for item in items:
        item_workspace_id = await permission_service.resolve_workspace_id(
            item.object_type, item.object_id
        )
        if item_workspace_id != workspace_id:
            raise ValueError("Stash items must be in the active workspace")
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
            "snippet": (r.get("content_markdown") or "")[:300],
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
    "list_stashes",
    "List Stashes from the active Stash Workspace.",
    {"type": "object", "properties": {}},
)
async def _list_stashes(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    stashes = await stash_service.list_workspace_stashes(workspace_id, user_id)
    return _text_result(json.dumps([_stash_to_dict(stash) for stash in stashes]))


@tool(
    "create_stash",
    "Create a Stash from workspace items.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string", "default": ""},
            "access": {
                "type": "string",
                "enum": ["workspace", "private", "public"],
                "default": "workspace",
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
async def _create_stash(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    access = args.get("access") or "workspace"
    discoverable = bool(args.get("discoverable", False))
    if discoverable and access != "public":
        return _text_result(json.dumps({"error": "Discover Stashes must be public"}))
    items = await _parse_stash_items(args.get("items") or [], workspace_id)
    stash = await stash_service.create_stash(
        workspace_id=workspace_id,
        owner_id=user_id,
        title=args["title"],
        description=args.get("description") or "",
        access=access,
        discoverable=discoverable,
        cover_image_url=None,
        items=items,
    )
    return _text_result(json.dumps(_stash_to_dict(stash)))


@tool(
    "update_stash",
    "Update Stash metadata or replace its item list.",
    {
        "type": "object",
        "properties": {
            "stash_id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "access": {
                "type": "string",
                "enum": ["workspace", "private", "public"],
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
        "required": ["stash_id"],
    },
)
async def _update_stash(args: dict) -> dict:
    workspace_id = _current_workspace()
    user_id = _current_user()
    stash_id = UUID(args["stash_id"])
    if not await stash_service.user_can_manage(stash_id, user_id):
        return _text_result(json.dumps({"error": "not allowed"}))

    updates = {
        key: args[key] for key in ("title", "description", "access", "discoverable") if key in args
    }
    if "items" in args:
        updates["items"] = await _parse_stash_items(args.get("items") or [], workspace_id)
    stash = await stash_service.update_stash(
        stash_id,
        user_id,
        updates,
    )
    if not stash:
        return _text_result(json.dumps({"error": "not found"}))
    return _text_result(json.dumps(_stash_to_dict(stash)))


@tool(
    "delete_stash",
    "Delete a Stash by id.",
    {
        "type": "object",
        "properties": {"stash_id": {"type": "string"}},
        "required": ["stash_id"],
    },
)
async def _delete_stash(args: dict) -> dict:
    user_id = _current_user()
    stash_id = UUID(args["stash_id"])
    if not await stash_service.user_can_manage(stash_id, user_id):
        return _text_result(json.dumps({"error": "not allowed"}))
    deleted = await stash_service.delete_stash(stash_id, user_id)
    return _text_result(json.dumps({"deleted": deleted, "stash_id": str(stash_id)}))


_TOOLS_BY_NAME = {
    "search_history": _search_history,
    "read_page": _read_page,
    "grep_pages": _grep_pages,
    "list_files": _list_files,
    "read_file": _read_file,
    "query_table": _query_table,
    "list_skills": _list_skills,
    "read_skill": _read_skill,
    "list_stashes": _list_stashes,
    "create_stash": _create_stash,
    "update_stash": _update_stash,
    "delete_stash": _delete_stash,
}


def _build_options(
    *,
    system: str,
    tool_set: tuple[str, ...],
    model: str,
    max_turns: int,
) -> ClaudeAgentOptions:
    tools = [_TOOLS_BY_NAME[name] for name in tool_set]
    mcp_server = create_sdk_mcp_server(name="stash", version="1.0.0", tools=tools)
    # The SDK exposes MCP tools as `mcp__{server}__{tool_name}` in allowed_tools.
    allowed = [f"mcp__stash__{name}" for name in tool_set]
    return ClaudeAgentOptions(
        system_prompt=system,
        model=model,
        max_turns=max_turns,
        mcp_servers={"stash": mcp_server},
        allowed_tools=allowed,
        # No filesystem/Bash tools — purely the in-process MCP toolset.
        disallowed_tools=["Bash", "Edit", "Write", "Read", "Glob", "Grep"],
        # We pass full prompt as the user turn; no continuation needed.
        permission_mode="bypassPermissions",
        env={"ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY or ""},
    )


# --- Public API ------------------------------------------------------------


@dataclass(slots=True)
class AgentResult:
    text: str
    input_tokens: int
    output_tokens: int
    turns_used: int
    tool_calls_used: int
    model: str
    terminated_by: str  # 'end_turn' | 'max_turns' | 'error'


def _extract_usage(msg) -> tuple[int, int]:
    """Returns (input_tokens, output_tokens) from a ResultMessage or AssistantMessage."""
    usage = getattr(msg, "usage", None) or {}
    if isinstance(usage, dict):
        return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    return int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)


async def run_agent(
    *,
    tier: ModelTier,
    system: str,
    prompt: str,
    workspace_id: UUID,
    user_id: UUID | None = None,
    tool_set: tuple[str, ...] = (),
    max_turns: int = 8,
    max_output_tokens: int = 4096,
) -> AgentResult:
    """Single-turn or multi-turn agent call. Aggregates the SDK message
    stream into one result."""
    _require_api_key()
    model = _model_for(tier)
    options = _build_options(system=system, tool_set=tool_set, model=model, max_turns=max_turns)

    final_text = ""
    input_tokens = 0
    output_tokens = 0
    turns = 0
    tool_calls = 0
    terminated_by = "end_turn"

    workspace_token = _workspace_ctx.set(workspace_id)
    user_token = _user_ctx.set(user_id)
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                turns += 1
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        final_text = block.text
                    elif isinstance(block, ToolUseBlock):
                        tool_calls += 1
                in_t, out_t = _extract_usage(msg)
                input_tokens += in_t
                output_tokens += out_t
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    terminated_by = msg.subtype or "error"
                if msg.result:
                    final_text = msg.result
                if msg.usage:
                    if msg.usage.get("input_tokens"):
                        input_tokens = int(msg.usage["input_tokens"])
                    if msg.usage.get("output_tokens"):
                        output_tokens = int(msg.usage["output_tokens"])
                if msg.num_turns:
                    turns = msg.num_turns
                if msg.subtype == "error_max_turns":
                    terminated_by = "max_turns"
    finally:
        _user_ctx.reset(user_token)
        _workspace_ctx.reset(workspace_token)

    return AgentResult(
        text=final_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        turns_used=turns,
        tool_calls_used=tool_calls,
        model=model,
        terminated_by=terminated_by,
    )


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_agent(
    *,
    tier: ModelTier,
    system: str,
    prompt: str,
    workspace_id: UUID,
    user_id: UUID | None = None,
    tool_set: tuple[str, ...],
    max_turns: int = 8,
) -> AsyncIterator[str]:
    """SSE generator for ask-the-workspace. Forwards assistant text deltas + a
    summary line per tool call."""
    if not settings.ANTHROPIC_API_KEY:
        yield _sse(
            {
                "type": "text",
                "delta": (
                    "Ask-the-workspace needs ANTHROPIC_API_KEY set on the backend. "
                    "Drop a key into backend/.env and restart."
                ),
            }
        )
        yield _sse({"type": "end"})
        return

    model = _model_for(tier)
    options = _build_options(system=system, tool_set=tool_set, model=model, max_turns=max_turns)

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
