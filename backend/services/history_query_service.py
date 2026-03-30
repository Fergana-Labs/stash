"""History query service: LLM-powered Q&A over a history store.

Searches events via FTS + vector similarity, then synthesizes an answer
using Claude Haiku.
"""

import logging
from uuid import UUID

import anthropic

from . import embedding_service, memory_service

logger = logging.getLogger(__name__)

QUERY_MODEL = "claude-haiku-4-5-20251001"

_client: anthropic.AsyncAnthropic | None = None


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


def _format_events(events: list[dict]) -> str:
    lines = []
    for e in events:
        ts = str(e.get("created_at", ""))[:19]
        agent = e.get("agent_name", "")
        etype = e.get("event_type", "")
        tool = e.get("tool_name", "")
        content = str(e.get("content", ""))[:500]
        meta = e.get("metadata", {})

        header = f"[{ts}] {agent}/{etype}"
        if tool:
            header += f" (tool: {tool})"
        lines.append(f"{header}\n{content}")
        if meta:
            # Include useful metadata fields
            for k, v in meta.items():
                if k not in ("cwd",) and v:
                    lines.append(f"  {k}: {str(v)[:200]}")
        lines.append("")
    return "\n".join(lines)


async def query_history(
    store_id: UUID,
    question: str,
    limit: int = 20,
) -> dict:
    """Search history events and synthesize an answer using Claude.

    Returns {"answer": str, "sources": list[dict]}.
    """
    # Gather events from multiple search strategies
    all_events: dict[str, dict] = {}  # dedupe by id

    # 1. Full-text search
    fts_results = await memory_service.search_events(store_id, question, limit=limit)
    for e in fts_results:
        all_events[str(e["id"])] = e

    # 2. Vector similarity search (if embeddings are configured)
    if embedding_service.is_configured():
        query_vec = await embedding_service.embed_text(question)
        if query_vec is not None:
            vec_results = await memory_service.search_events_vector(
                store_id, query_vec, limit=limit
            )
            for e in vec_results:
                all_events[str(e["id"])] = e

    # 3. If no search results, fall back to recent events
    if not all_events:
        recent, _ = await memory_service.query_events(store_id, limit=limit)
        for e in recent:
            all_events[str(e["id"])] = e

    sources = sorted(all_events.values(), key=lambda e: e.get("created_at", ""))

    if not sources:
        return {
            "answer": "No events found in this history store.",
            "sources": [],
        }

    # Synthesize answer with Claude
    formatted = _format_events(sources)
    client = _get_anthropic()

    try:
        response = await client.messages.create(
            model=QUERY_MODEL,
            max_tokens=1024,
            system=(
                "You are answering questions about an activity history log. "
                "The log contains timestamped events from AI agents and tools. "
                "Answer the question based ONLY on the events provided. "
                "Be specific — cite timestamps, agent names, and details from the events. "
                "If the events don't contain enough information to answer, say so."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"## Events\n\n{formatted}\n\n"
                    f"## Question\n\n{question}"
                ),
            }],
        )
        answer = response.content[0].text.strip()
    except Exception as e:
        logger.error("LLM query failed: %s", e)
        answer = (
            "Unable to synthesize an answer (LLM unavailable). "
            f"Found {len(sources)} relevant events — see sources."
        )

    return {
        "answer": answer,
        "sources": sources,
    }
