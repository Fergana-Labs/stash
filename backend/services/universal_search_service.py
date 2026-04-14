"""Universal search service: agent-loop Q&A across all resource types.

Uses a tool-use agent loop where Claude:
1. Searches across history stores, notebooks, tables, and documents
2. Reviews results and refines searches
3. Synthesizes a final answer with sources

Extends the pattern from history_query_service.py to span all resource types.
"""

import json
import logging
from uuid import UUID

import anthropic

from . import (
    embedding_service,
    memory_service,
    notebook_service,
    table_service,
)

logger = logging.getLogger(__name__)

QUERY_MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 5

_client: anthropic.AsyncAnthropic | None = None


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


# --- Tool definitions ---

TOOLS = [
    {
        "name": "search_history",
        "description": (
            "Full-text search over history event logs. Use specific keywords. "
            "PostgreSQL websearch syntax: words are AND'd, use OR for alternatives, "
            "quotes for exact phrases, - to exclude."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "History store UUID (from list_resources)"},
                "query": {"type": "string", "description": "Search keywords"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["store_id", "query"],
        },
    },
    {
        "name": "search_notebooks",
        "description": (
            "Full-text search over notebook pages (markdown content). "
            "Returns matching pages with content previews."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notebook_id": {"type": "string", "description": "Notebook UUID (from list_resources)"},
                "query": {"type": "string", "description": "Search keywords"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["notebook_id", "query"],
        },
    },
    {
        "name": "search_tables",
        "description": "Search table rows using text matching across all text columns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "Table UUID (from list_resources)"},
                "query": {"type": "string", "description": "Search text"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["table_id", "query"],
        },
    },
    {
        "name": "list_resources",
        "description": (
            "List all available resources in scope: history stores, notebooks, tables. "
            "Call this first to discover resource IDs for targeted searches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "read_page",
        "description": "Read the full content of a specific notebook page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "notebook_id": {"type": "string"},
                "page_id": {"type": "string"},
            },
            "required": ["notebook_id", "page_id"],
        },
    },
    {
        "name": "answer",
        "description": "Provide the final answer. Call when you have enough information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Your synthesized answer"},
                "source_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Types of sources used (e.g. history, notebook, table, document)",
                },
            },
            "required": ["text"],
        },
    },
]


# --- Resource discovery ---


async def _list_resources(workspace_id: UUID | None, user_id: UUID) -> str:
    """List all searchable resources."""
    from ..database import get_pool
    pool = get_pool()
    lines = []

    if workspace_id:
        # Workspace-scoped
        histories = await pool.fetch(
            "SELECT id, name FROM histories WHERE workspace_id = $1", workspace_id,
        )
        notebooks = await pool.fetch(
            "SELECT id, name FROM notebooks WHERE workspace_id = $1", workspace_id,
        )
        tables = await pool.fetch(
            "SELECT id, name FROM tables WHERE workspace_id = $1", workspace_id,
        )
        lines.append("## History Stores")
        for h in histories:
            lines.append(f"- {h['name']} (id: {h['id']})")
        lines.append("\n## Notebooks")
        for n in notebooks:
            lines.append(f"- {n['name']} (id: {n['id']})")
        lines.append("\n## Tables")
        for t in tables:
            lines.append(f"- {t['name']} (id: {t['id']})")
    else:
        # Personal resources
        histories = await pool.fetch(
            "SELECT id, name FROM histories WHERE workspace_id IS NULL AND created_by = $1",
            user_id,
        )
        notebooks = await pool.fetch(
            "SELECT id, name FROM notebooks WHERE workspace_id IS NULL AND created_by = $1",
            user_id,
        )
        tables = await pool.fetch(
            "SELECT id, name FROM tables WHERE workspace_id IS NULL AND created_by = $1",
            user_id,
        )
        lines.append("## Personal History Stores")
        for h in histories:
            lines.append(f"- {h['name']} (id: {h['id']})")
        lines.append("\n## Personal Notebooks")
        for n in notebooks:
            lines.append(f"- {n['name']} (id: {n['id']})")
        lines.append("\n## Personal Tables")
        for t in tables:
            lines.append(f"- {t['name']} (id: {t['id']})")

    return "\n".join(lines)


# --- Tool execution ---


def _format_events(events: list[dict]) -> str:
    if not events:
        return "(no results)"
    lines = []
    for e in events:
        ts = str(e.get("created_at", ""))[:19]
        content = str(e.get("content", ""))[:300]
        lines.append(f"[{ts}] {e.get('agent_name', '')}/{e.get('event_type', '')}: {content}")
    return "\n".join(lines)


def _format_pages(pages: list[dict]) -> str:
    if not pages:
        return "(no results)"
    lines = []
    for p in pages:
        content = (p.get("content_markdown") or "")[:300]
        lines.append(f"[{p.get('name', '?')}]: {content}")
    return "\n".join(lines)


def _format_rows(rows: list[dict]) -> str:
    if not rows:
        return "(no results)"
    lines = []
    for r in rows:
        data_preview = json.dumps(r.get("data", {}), default=str)[:300]
        lines.append(f"Row {r.get('id', '?')}: {data_preview}")
    return "\n".join(lines)


async def _execute_tool(
    workspace_id: UUID | None, user_id: UUID,
    tool_name: str, tool_input: dict,
) -> str:
    """Execute a search tool and return formatted results."""
    if tool_name == "list_resources":
        return await _list_resources(workspace_id, user_id)

    elif tool_name == "search_history":
        store_id = UUID(tool_input["store_id"])
        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 20)
        events = await memory_service.search_events(store_id, query, limit=limit)
        return _format_events(events)

    elif tool_name == "search_notebooks":
        notebook_id = UUID(tool_input["notebook_id"])
        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 20)
        pages = await notebook_service.search_pages_fts(notebook_id, query, limit=limit)
        return _format_pages(pages)

    elif tool_name == "search_tables":
        table_id = UUID(tool_input["table_id"])
        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 20)
        rows, _ = await table_service.search_rows(table_id, query, limit=limit)
        return _format_rows(rows)

    elif tool_name == "read_page":
        notebook_id = UUID(tool_input["notebook_id"])
        page_id = UUID(tool_input["page_id"])
        page = await notebook_service.get_page(page_id, notebook_id)
        if not page:
            return "(page not found)"
        return f"# {page['name']}\n\n{page.get('content_markdown', '')}"

    return "(unknown tool)"


# --- Main query function ---


async def universal_search(
    question: str,
    user_id: UUID,
    workspace_id: UUID | None = None,
    resource_types: list[str] | None = None,
) -> dict:
    """Run an agent loop to answer a question across all resource types.

    Returns {"answer": str, "sources_used": list[str]}.
    """
    client = _get_anthropic()

    # Filter tools by resource_types if specified
    tools = list(TOOLS)
    if resource_types:
        exclude = set()
        if "history" not in resource_types:
            exclude.add("search_history")
        if "notebook" not in resource_types:
            exclude.update({"search_notebooks", "read_page"})
        if "table" not in resource_types:
            exclude.add("search_tables")
        tools = [t for t in tools if t["name"] not in exclude]

    system = (
        "You are a research assistant that searches across multiple data sources to answer questions. "
        "Available sources: history event logs, notebook pages (markdown), and structured tables.\n\n"
        "Strategy:\n"
        "1. First call list_resources to discover what's available\n"
        "2. Search relevant resources with targeted queries\n"
        "3. If needed, read full pages for detail\n"
        "4. Synthesize your findings and call answer\n\n"
        "Be specific — cite source names, page titles, and relevant details."
    )

    messages = [{"role": "user", "content": question}]

    try:
        for _ in range(MAX_ITERATIONS):
            response = await client.messages.create(
                model=QUERY_MODEL,
                max_tokens=2048,
                system=system,
                tools=tools,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        if block.name == "answer":
                            return {
                                "answer": block.input.get("text", ""),
                                "sources_used": block.input.get("source_types", []),
                            }

                        result = await _execute_tool(
                            workspace_id, user_id, block.name, block.input,
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                return {
                    "answer": "\n".join(text_parts).strip(),
                    "sources_used": [],
                }

        return {
            "answer": "Reached search limit. Please try a more specific question.",
            "sources_used": [],
        }

    except Exception as e:
        logger.error("Universal search agent failed: %s", e)
        return {
            "answer": f"Search failed: {e}",
            "sources_used": [],
        }
