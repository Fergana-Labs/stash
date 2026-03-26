"""Memory service: structured agent event storage with FTS and batch insert."""

import json
from datetime import datetime
from uuid import UUID

from ..database import get_pool


# --- Store CRUD ---


async def create_store(
    workspace_id: UUID, name: str, description: str, created_by: UUID,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO memory_stores (workspace_id, name, description, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, workspace_id, name, description, created_by, created_at",
        workspace_id, name, description, created_by,
    )
    store = dict(row)
    store["event_count"] = 0
    return store


async def get_store(store_id: UUID, workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT ms.*, "
        "(SELECT COUNT(*) FROM memory_events me WHERE me.store_id = ms.id) AS event_count "
        "FROM memory_stores ms WHERE ms.id = $1 AND ms.workspace_id = $2",
        store_id, workspace_id,
    )
    return dict(row) if row else None


async def list_stores(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT ms.*, "
        "(SELECT COUNT(*) FROM memory_events me WHERE me.store_id = ms.id) AS event_count "
        "FROM memory_stores ms WHERE ms.workspace_id = $1 ORDER BY ms.created_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def delete_store(store_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM memory_stores WHERE id = $1 AND workspace_id = $2",
        store_id, workspace_id,
    )
    return result == "DELETE 1"


# --- Event CRUD ---


async def push_event(
    store_id: UUID,
    agent_name: str,
    event_type: str,
    content: str,
    session_id: str | None = None,
    tool_name: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Push a single event to a memory store."""
    pool = get_pool()
    meta_json = json.dumps(metadata or {})
    row = await pool.fetchrow(
        "INSERT INTO memory_events (store_id, agent_name, event_type, content, session_id, tool_name, metadata) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb) "
        "RETURNING id, store_id, agent_name, event_type, session_id, tool_name, content, metadata, created_at",
        store_id, agent_name, event_type, content, session_id, tool_name, meta_json,
    )
    return dict(row)


async def push_events_batch(store_id: UUID, events: list[dict]) -> list[dict]:
    """Batch push events to a memory store. Returns list of created events."""
    pool = get_pool()
    results = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for evt in events:
                meta_json = json.dumps(evt.get("metadata", {}))
                row = await conn.fetchrow(
                    "INSERT INTO memory_events "
                    "(store_id, agent_name, event_type, content, session_id, tool_name, metadata) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb) "
                    "RETURNING id, store_id, agent_name, event_type, session_id, tool_name, "
                    "content, metadata, created_at",
                    store_id,
                    evt["agent_name"],
                    evt["event_type"],
                    evt["content"],
                    evt.get("session_id"),
                    evt.get("tool_name"),
                    meta_json,
                )
                results.append(dict(row))
    return results


async def get_event(event_id: UUID, store_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, store_id, agent_name, event_type, session_id, tool_name, "
        "content, metadata, created_at "
        "FROM memory_events WHERE id = $1 AND store_id = $2",
        event_id, store_id,
    )
    return dict(row) if row else None


async def query_events(
    store_id: UUID,
    agent_name: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], bool]:
    """Query events with filters. Returns (events, has_more)."""
    pool = get_pool()
    limit = min(limit, 200)

    conditions = ["store_id = $1"]
    args: list = [store_id]
    idx = 2

    if agent_name:
        conditions.append(f"agent_name = ${idx}")
        args.append(agent_name)
        idx += 1
    if session_id:
        conditions.append(f"session_id = ${idx}")
        args.append(session_id)
        idx += 1
    if event_type:
        conditions.append(f"event_type = ${idx}")
        args.append(event_type)
        idx += 1
    if after:
        conditions.append(f"created_at > ${idx}")
        args.append(after)
        idx += 1
    if before:
        conditions.append(f"created_at < ${idx}")
        args.append(before)
        idx += 1

    where = " AND ".join(conditions)
    args.append(limit + 1)

    rows = await pool.fetch(
        f"SELECT id, store_id, agent_name, event_type, session_id, tool_name, "
        f"content, metadata, created_at "
        f"FROM memory_events WHERE {where} "
        f"ORDER BY created_at ASC LIMIT ${idx}",
        *args,
    )

    events = [dict(r) for r in rows]
    has_more = len(events) > limit
    if has_more:
        events = events[:limit]
    return events, has_more


async def search_events(
    store_id: UUID, query: str, limit: int = 50,
) -> list[dict]:
    """Full-text search on memory events."""
    pool = get_pool()
    limit = min(limit, 200)
    rows = await pool.fetch(
        "SELECT id, store_id, agent_name, event_type, session_id, tool_name, "
        "content, metadata, created_at, "
        "ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', $2)) AS rank "
        "FROM memory_events "
        "WHERE store_id = $1 AND to_tsvector('english', content) @@ websearch_to_tsquery('english', $2) "
        "ORDER BY rank DESC LIMIT $3",
        store_id, query, limit,
    )
    return [dict(r) for r in rows]
