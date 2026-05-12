"""Ask-the-stash agent loop.

Streams text + tool-use events as Server-Sent Events. Tool schemas live in
``services.prompts``; the executors below run repo code, so they stay here.

The handoff curator imports ``_execute_tool`` to reuse the same toolset for
its own agent loop — keeping the two features aligned without a shared
abstraction.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from ..config import settings
from . import (
    llm,
    memory_service,
    prompts,
    skill_service,
    table_service,
    wiki_service,
)


async def _execute_tool(name: str, args: dict, stash_id: UUID) -> tuple[str, str]:
    """Returns ``(json_payload, short_summary)`` for a tool invocation."""
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
    tool_set: tuple[str, ...] = prompts.STASH_TOOL_SET,
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

    client = llm.get_async_client()
    model = llm.model_for(llm.ModelTier.QUALITY)
    tools = prompts.tool_schemas(tool_set)
    system = prompts.render_ask_system(stash_name)
    convo: list[dict] = list(messages)

    for _turn in range(settings.ASK_MAX_TURNS):
        async with client.messages.stream(
            model=model,
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


# Re-exports for backwards compatibility with any caller importing constants
# from this module.
STASH_TOOL_SET = prompts.STASH_TOOL_SET
RECIPIENT_TOOL_SET = prompts.RECIPIENT_TOOL_SET
