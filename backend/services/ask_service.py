"""Ask-the-stash agent loop.

Streams text + tool-use events as Server-Sent Events. Tools are scoped to a
single stash; the recipient variant in Phase 5 passes a restricted ``tool_set``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from ..config import settings
from . import memory_service, skill_service, table_service, wiki_service

# Full tool surface for an authenticated stash member.
STASH_TOOL_SET = (
    "search_history",
    "read_page",
    "grep_pages",
    "list_files",
    "read_file",
    "query_table",
    "list_skills",
    "read_skill",
)

# Recipient (share-link) tool set — public-projection content only.
RECIPIENT_TOOL_SET = (
    "read_page",
    "grep_pages",
    "list_files",
    "read_file",
)


def _tool_schemas(tool_set: tuple[str, ...]) -> list[dict]:
    catalog: dict[str, dict] = {
        "search_history": {
            "name": "search_history",
            "description": "Full-text search across this stash's agent transcripts and history events.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
        "read_page": {
            "name": "read_page",
            "description": "Read the full markdown body of a wiki page by id.",
            "input_schema": {
                "type": "object",
                "properties": {"page_id": {"type": "string"}},
                "required": ["page_id"],
            },
        },
        "grep_pages": {
            "name": "grep_pages",
            "description": "Full-text search across wiki pages in this stash. Returns page id + snippet.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["pattern"],
            },
        },
        "list_files": {
            "name": "list_files",
            "description": "List files (PDFs, docs, images) uploaded to this stash.",
            "input_schema": {"type": "object", "properties": {}},
        },
        "read_file": {
            "name": "read_file",
            "description": "Read extracted text content from a stash file by id.",
            "input_schema": {
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
                "required": ["file_id"],
            },
        },
        "query_table": {
            "name": "query_table",
            "description": "List rows from a table by name. Returns the row payloads.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["table_name"],
            },
        },
        "list_skills": {
            "name": "list_skills",
            "description": "List skills (folders with SKILL.md frontmatter) defined in this stash.",
            "input_schema": {"type": "object", "properties": {}},
        },
        "read_skill": {
            "name": "read_skill",
            "description": "Read a skill by name — returns SKILL.md + sibling files concatenated.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    }
    return [catalog[name] for name in tool_set if name in catalog]


async def _execute_tool(name: str, args: dict, stash_id: UUID) -> tuple[str, str]:
    """Returns ``(json_payload, short_summary)``."""
    from ..database import get_pool

    pool = get_pool()
    if name == "search_history":
        rows = await memory_service.search_workspace_events(
            stash_id, args.get("query", ""), limit=int(args.get("limit", 10))
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
        return json.dumps(out), f"{len(out)} hits"

    if name == "read_page":
        page = await wiki_service.get_page(UUID(args["page_id"]), stash_id)
        if not page:
            return json.dumps({"error": "not found"}), "0 hits"
        return (
            json.dumps(
                {
                    "id": str(page["id"]),
                    "name": page["name"],
                    "content": page.get("content_markdown") or page.get("content_html") or "",
                }
            ),
            page["name"],
        )

    if name == "grep_pages":
        rows = await wiki_service.search_pages_fts(
            stash_id, args.get("pattern", ""), limit=int(args.get("limit", 10))
        )
        out = [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "snippet": (r.get("content_markdown") or "")[:300],
            }
            for r in rows
        ]
        return json.dumps(out), f"{len(out)} pages"

    if name == "list_files":
        rows = await pool.fetch(
            "SELECT id, name, content_type, size_bytes FROM files WHERE workspace_id = $1 "
            "ORDER BY created_at DESC LIMIT 50",
            stash_id,
        )
        out = [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "content_type": r["content_type"],
                "size_bytes": r["size_bytes"],
            }
            for r in rows
        ]
        return json.dumps(out), f"{len(out)} files"

    if name == "read_file":
        row = await pool.fetchrow(
            "SELECT name, extracted_text FROM files WHERE id = $1 AND workspace_id = $2",
            UUID(args["file_id"]),
            stash_id,
        )
        if not row:
            return json.dumps({"error": "not found"}), "0 hits"
        text = row["extracted_text"] or ""
        return json.dumps({"name": row["name"], "text": text[:6000]}), row["name"]

    if name == "query_table":
        tables = await table_service.list_tables(stash_id)
        match = next(
            (t for t in tables if t.get("name", "").lower() == args.get("table_name", "").lower()),
            None,
        )
        if not match:
            return json.dumps({"error": "table not found"}), "0 hits"
        rows = await pool.fetch(
            "SELECT id, data FROM table_rows WHERE table_id = $1 ORDER BY row_order LIMIT $2",
            match["id"],
            int(args.get("limit", 50)),
        )
        out = [{"id": str(r["id"]), "data": r["data"]} for r in rows]
        return json.dumps(out), f"{len(out)} rows"

    if name == "list_skills":
        skills = await skill_service.list_skills(stash_id)
        out = [
            {"name": s["name"], "description": s["description"], "files": s["file_count"]}
            for s in skills
        ]
        return json.dumps(out), f"{len(out)} skills"

    if name == "read_skill":
        skill = await skill_service.read_skill(stash_id, args.get("name", ""))
        if not skill:
            return json.dumps({"error": "not found"}), "0 hits"
        return json.dumps({"name": skill["name"], "combined": skill["combined"]}), skill["name"]

    return json.dumps({"error": f"unknown tool {name}"}), "error"


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_ask(
    stash_id: UUID,
    stash_name: str,
    messages: list[dict],
    tool_set: tuple[str, ...] = STASH_TOOL_SET,
) -> AsyncIterator[str]:
    """Run the agent loop and yield SSE-encoded chunks.

    Falls back to a clear error message if ANTHROPIC_API_KEY is unset, so the
    feature degrades visibly rather than 500ing.
    """
    if not settings.ANTHROPIC_API_KEY:
        yield _sse(
            {
                "type": "text",
                "delta": "Ask-the-stash needs ANTHROPIC_API_KEY set on the backend. "
                "Drop a key into backend/.env and restart.",
            }
        )
        yield _sse({"type": "end"})
        return

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        yield _sse({"type": "error", "message": "anthropic SDK not installed"})
        return

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    tools = _tool_schemas(tool_set)
    system = (
        f"You are an expert assistant for the '{stash_name}' stash. Answer questions "
        "by calling tools to ground every claim. Reference what you found by name "
        "(e.g., the wiki page name or table). Be concise."
    )

    convo: list[dict] = list(messages)

    for turn in range(settings.ASK_MAX_TURNS):
        async with client.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2048,
            system=system,
            tools=tools,
            messages=convo,
        ) as stream:
            async for chunk in stream.text_stream:
                if chunk:
                    yield _sse({"type": "text", "delta": chunk})
            response = await stream.get_final_message()

        # Append assistant turn (with both text + tool_use blocks) to convo.
        assistant_blocks = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                assistant_blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
                tool_uses.append(block)
        convo.append({"role": "assistant", "content": assistant_blocks})

        if response.stop_reason != "tool_use" or not tool_uses:
            break

        # Execute each tool call, stream a "tool" event, append tool_result to convo.
        tool_results = []
        for tu in tool_uses:
            payload, summary = await _execute_tool(tu.name, dict(tu.input), stash_id)
            yield _sse(
                {
                    "type": "tool",
                    "name": tu.name,
                    "args": dict(tu.input),
                    "result_summary": summary,
                }
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": payload,
                }
            )
        convo.append({"role": "user", "content": tool_results})

    yield _sse({"type": "end"})
