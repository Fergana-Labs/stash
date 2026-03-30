"""History query service: agent-loop Q&A over a history store.

Uses a small tool-use agent loop where Claude:
1. Decides what searches to run (keyword FTS, vector similarity, filtered queries)
2. Executes them as tool calls
3. Reviews results, optionally refines with more searches
4. Synthesizes a final answer

This is much better than naively dumping the whole question into FTS.
"""

import json
import logging
from uuid import UUID

import anthropic

from . import embedding_service, memory_service

logger = logging.getLogger(__name__)

QUERY_MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 5

_client: anthropic.AsyncAnthropic | None = None


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


# --- Tools the agent can call ---

TOOLS = [
    {
        "name": "keyword_search",
        "description": (
            "Full-text search over history events. Use specific keywords, not full sentences. "
            "PostgreSQL websearch syntax: words are AND'd, use OR for alternatives, "
            "use quotes for exact phrases, use - to exclude. "
            "Examples: 'deploy error', 'file_path OR filepath', '\"database migration\"', 'test -unit'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords (not a full question)"},
                "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "filter_events",
        "description": (
            "Filter events by agent name, event type, session ID, or time range. "
            "All filters are optional — combine as needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Filter by agent name"},
                "event_type": {"type": "string", "description": "Filter by event type (e.g. tool_use, session_end)"},
                "session_id": {"type": "string", "description": "Filter by session ID"},
                "after": {"type": "string", "description": "Only events after this ISO timestamp"},
                "before": {"type": "string", "description": "Only events before this ISO timestamp"},
                "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
            },
        },
    },
    {
        "name": "answer",
        "description": "Provide the final answer to the user's question. Call this when you have enough information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Your answer to the question"},
            },
            "required": ["text"],
        },
    },
]

# Add vector search tool only if embeddings are configured
VECTOR_TOOL = {
    "name": "semantic_search",
    "description": (
        "Semantic similarity search — finds events with similar meaning even if exact keywords don't match. "
        "Good for conceptual questions like 'what work was done on authentication'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language description of what to search for"},
            "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
        },
        "required": ["query"],
    },
}


def _format_events_for_agent(events: list[dict]) -> str:
    if not events:
        return "(no results)"
    lines = []
    for e in events:
        ts = str(e.get("created_at", ""))[:19]
        agent = e.get("agent_name", "")
        etype = e.get("event_type", "")
        tool = e.get("tool_name", "")
        content = str(e.get("content", ""))[:400]
        meta = e.get("metadata", {})

        header = f"[{ts}] {agent}/{etype}"
        if tool:
            header += f" (tool: {tool})"
        lines.append(f"{header}: {content}")
        if meta:
            useful = {k: str(v)[:150] for k, v in meta.items() if k not in ("cwd",) and v}
            if useful:
                lines.append(f"  metadata: {json.dumps(useful)}")
    return "\n".join(lines)


async def _execute_tool(store_id: UUID, tool_name: str, tool_input: dict) -> tuple[str, list[dict]]:
    """Execute a tool call. Returns (formatted_result, raw_events)."""
    if tool_name == "keyword_search":
        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 20)
        events = await memory_service.search_events(store_id, query, limit=limit)
        return _format_events_for_agent(events), events

    elif tool_name == "semantic_search":
        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 20)
        if embedding_service.is_configured():
            vec = await embedding_service.embed_text(query)
            if vec is not None:
                events = await memory_service.search_events_vector(store_id, vec, limit=limit)
                return _format_events_for_agent(events), events
        return "(semantic search not available — no embeddings configured)", []

    elif tool_name == "filter_events":
        events, _ = await memory_service.query_events(
            store_id,
            agent_name=tool_input.get("agent_name"),
            event_type=tool_input.get("event_type"),
            session_id=tool_input.get("session_id"),
            after=tool_input.get("after"),
            before=tool_input.get("before"),
            limit=tool_input.get("limit", 20),
        )
        return _format_events_for_agent(events), events

    return "(unknown tool)", []


async def query_history(
    store_id: UUID,
    question: str,
    limit: int = 20,
) -> dict:
    """Run an agent loop to answer a question about a history store.

    Returns {"answer": str, "sources": list[dict]}.
    """
    client = _get_anthropic()
    all_sources: dict[str, dict] = {}

    tools = list(TOOLS)
    if embedding_service.is_configured():
        tools.insert(1, VECTOR_TOOL)

    system = (
        "You are a research assistant answering questions about an activity history log. "
        "The history contains timestamped events from AI agents — tool uses, session summaries, "
        "and other structured events.\n\n"
        "You have search tools to find relevant events. Strategy:\n"
        "1. Break the question into specific search queries (keywords, not full sentences)\n"
        "2. Use keyword_search for specific terms, filter_events for structural queries\n"
        "3. Review results — if you need more detail, search again with refined terms\n"
        "4. When you have enough info, call the answer tool\n\n"
        "Be specific in your answer — cite timestamps, agent names, and event details."
    )

    messages = [{"role": "user", "content": question}]

    try:
        for _ in range(MAX_ITERATIONS):
            response = await client.messages.create(
                model=QUERY_MODEL,
                max_tokens=1024,
                system=system,
                tools=tools,
                messages=messages,
            )

            # Check if the model wants to use tools
            if response.stop_reason == "tool_use":
                # Process tool calls
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        if block.name == "answer":
                            # Final answer
                            sources = sorted(
                                all_sources.values(),
                                key=lambda e: e.get("created_at", ""),
                            )
                            return {
                                "answer": block.input.get("text", ""),
                                "sources": sources,
                            }

                        formatted, events = await _execute_tool(
                            store_id, block.name, block.input
                        )
                        for e in events:
                            all_sources[str(e["id"])] = e

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": formatted,
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                # Model responded with text (no tool use) — treat as answer
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                answer = "\n".join(text_parts).strip()
                sources = sorted(
                    all_sources.values(),
                    key=lambda e: e.get("created_at", ""),
                )
                return {"answer": answer, "sources": sources}

        # Hit max iterations
        sources = sorted(all_sources.values(), key=lambda e: e.get("created_at", ""))
        return {
            "answer": f"Searched {len(all_sources)} events but couldn't form a complete answer. See sources.",
            "sources": sources,
        }

    except Exception as e:
        logger.error("History query agent failed: %s", e)
        # Fallback: just do a simple FTS search and return events without synthesis
        events = await memory_service.search_events(store_id, question, limit=limit)
        if not events:
            recent, _ = await memory_service.query_events(store_id, limit=limit)
            events = recent
        return {
            "answer": f"LLM unavailable — returning {len(events)} matching events.",
            "sources": events,
        }
