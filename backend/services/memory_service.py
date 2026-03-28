"""History service: structured agent event storage with FTS, vector search, and batch insert."""

import asyncio
import json
import logging
from datetime import datetime
from uuid import UUID

import numpy as np

from ..database import get_pool
from . import embedding_service

logger = logging.getLogger(__name__)


# --- Store CRUD ---


async def create_store(
    workspace_id: UUID, name: str, description: str, created_by: UUID,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO histories (workspace_id, name, description, created_by) "
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
        "(SELECT COUNT(*) FROM history_events me WHERE me.store_id = ms.id) AS event_count "
        "FROM histories ms WHERE ms.id = $1 AND ms.workspace_id = $2",
        store_id, workspace_id,
    )
    return dict(row) if row else None


async def list_stores(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT ms.*, "
        "(SELECT COUNT(*) FROM history_events me WHERE me.store_id = ms.id) AS event_count "
        "FROM histories ms WHERE ms.workspace_id = $1 ORDER BY ms.created_at",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def delete_store(store_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM histories WHERE id = $1 AND workspace_id = $2",
        store_id, workspace_id,
    )
    return result == "DELETE 1"


# --- Aggregate Queries ---


async def list_all_user_stores(user_id: UUID) -> list[dict]:
    """All historys from workspaces user is member of + personal."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT ms.id, ms.workspace_id, ms.name, ms.description, ms.created_by, ms.created_at, "
        "(SELECT COUNT(*) FROM history_events me WHERE me.store_id = ms.id) AS event_count, "
        "w.name AS workspace_name "
        "FROM histories ms "
        "LEFT JOIN workspaces w ON w.id = ms.workspace_id "
        "WHERE ms.workspace_id IN ("
        "  SELECT workspace_id FROM workspace_members WHERE user_id = $1"
        ") OR (ms.workspace_id IS NULL AND ms.created_by = $1) "
        "ORDER BY ms.created_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def query_all_user_events(
    user_id: UUID,
    agent_name: str | None = None,
    event_type: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], bool]:
    """Events across ALL accessible stores, with filters."""
    pool = get_pool()
    limit = min(limit, 200)

    conditions = [
        "(ms.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1) "
        "OR (ms.workspace_id IS NULL AND ms.created_by = $1))"
    ]
    args: list = [user_id]
    idx = 2

    if agent_name:
        conditions.append(f"me.agent_name = ${idx}")
        args.append(agent_name)
        idx += 1
    if event_type:
        conditions.append(f"me.event_type = ${idx}")
        args.append(event_type)
        idx += 1
    if after:
        conditions.append(f"me.created_at > ${idx}")
        args.append(after)
        idx += 1
    if before:
        conditions.append(f"me.created_at < ${idx}")
        args.append(before)
        idx += 1

    where = " AND ".join(conditions)
    args.append(limit + 1)

    rows = await pool.fetch(
        f"SELECT me.id, me.store_id, me.agent_name, me.event_type, me.session_id, "
        f"me.tool_name, me.content, me.metadata, me.created_at, "
        f"ms.name AS store_name, ms.workspace_id, w.name AS workspace_name "
        f"FROM history_events me "
        f"JOIN histories ms ON ms.id = me.store_id "
        f"LEFT JOIN workspaces w ON w.id = ms.workspace_id "
        f"WHERE {where} "
        f"ORDER BY me.created_at DESC LIMIT ${idx}",
        *args,
    )

    events = [dict(r) for r in rows]
    has_more = len(events) > limit
    if has_more:
        events = events[:limit]
    return events, has_more


# --- Personal Store CRUD ---


async def create_personal_store(
    name: str, description: str, created_by: UUID,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO histories (workspace_id, name, description, created_by) "
        "VALUES (NULL, $1, $2, $3) "
        "RETURNING id, workspace_id, name, description, created_by, created_at",
        name, description, created_by,
    )
    store = dict(row)
    store["event_count"] = 0
    return store


async def get_personal_store(store_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT ms.*, "
        "(SELECT COUNT(*) FROM history_events me WHERE me.store_id = ms.id) AS event_count "
        "FROM histories ms WHERE ms.id = $1 AND ms.workspace_id IS NULL AND ms.created_by = $2",
        store_id, user_id,
    )
    return dict(row) if row else None


async def list_personal_stores(user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT ms.*, "
        "(SELECT COUNT(*) FROM history_events me WHERE me.store_id = ms.id) AS event_count "
        "FROM histories ms WHERE ms.workspace_id IS NULL AND ms.created_by = $1 "
        "ORDER BY ms.created_at",
        user_id,
    )
    return [dict(r) for r in rows]


async def delete_personal_store(store_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM histories WHERE id = $1 AND workspace_id IS NULL AND created_by = $2",
        store_id, user_id,
    )
    return result == "DELETE 1"


# --- Embedding helpers ---


async def _embed_event(event_id: UUID, content: str) -> None:
    """Fire-and-forget: embed content and update the event row."""
    try:
        vec = await embedding_service.embed_text(content)
        if vec is not None:
            pool = get_pool()
            await pool.execute(
                "UPDATE history_events SET embedding = $1 WHERE id = $2",
                vec, event_id,
            )
    except Exception:
        logger.debug("Failed to embed event %s", event_id, exc_info=True)


async def _embed_events_batch(event_ids: list[UUID], contents: list[str]) -> None:
    """Fire-and-forget: embed a batch of contents and update rows."""
    try:
        vecs = await embedding_service.embed_batch(contents)
        if vecs:
            pool = get_pool()
            async with pool.acquire() as conn:
                for eid, vec in zip(event_ids, vecs):
                    await conn.execute(
                        "UPDATE history_events SET embedding = $1 WHERE id = $2",
                        vec, eid,
                    )
    except Exception:
        logger.debug("Failed to batch-embed events", exc_info=True)


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
    """Push a single event to a history."""
    pool = get_pool()
    meta_json = json.dumps(metadata or {})
    row = await pool.fetchrow(
        "INSERT INTO history_events (store_id, agent_name, event_type, content, session_id, tool_name, metadata) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb) "
        "RETURNING id, store_id, agent_name, event_type, session_id, tool_name, content, metadata, created_at",
        store_id, agent_name, event_type, content, session_id, tool_name, meta_json,
    )
    event = dict(row)
    # Fire-and-forget embedding
    if embedding_service.is_configured():
        asyncio.create_task(_embed_event(event["id"], content))
    # Mark injection session as complete on session_end
    if event_type == "session_end" and session_id:
        try:
            await pool.execute(
                "UPDATE injection_sessions SET completed_at = now() "
                "WHERE session_id = $1 AND completed_at IS NULL",
                session_id,
            )
        except Exception:
            logger.debug("Failed to mark injection session complete", exc_info=True)
    return event


async def push_events_batch(store_id: UUID, events: list[dict]) -> list[dict]:
    """Batch push events to a history. Returns list of created events."""
    pool = get_pool()
    results = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for evt in events:
                meta_json = json.dumps(evt.get("metadata", {}))
                row = await conn.fetchrow(
                    "INSERT INTO history_events "
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
    # Fire-and-forget batch embedding
    if embedding_service.is_configured() and results:
        ids = [r["id"] for r in results]
        contents = [r["content"] for r in results]
        asyncio.create_task(_embed_events_batch(ids, contents))
    return results


async def get_event(event_id: UUID, store_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, store_id, agent_name, event_type, session_id, tool_name, "
        "content, metadata, created_at "
        "FROM history_events WHERE id = $1 AND store_id = $2",
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
        f"FROM history_events WHERE {where} "
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
        "FROM history_events "
        "WHERE store_id = $1 AND to_tsvector('english', content) @@ websearch_to_tsquery('english', $2) "
        "ORDER BY rank DESC LIMIT $3",
        store_id, query, limit,
    )
    return [dict(r) for r in rows]


async def search_events_vector(
    store_id: UUID, query_embedding: np.ndarray, limit: int = 20,
) -> list[dict]:
    """Semantic vector search using pgvector cosine distance."""
    pool = get_pool()
    limit = min(limit, 200)
    rows = await pool.fetch(
        "SELECT id, store_id, agent_name, event_type, session_id, tool_name, "
        "content, metadata, created_at, "
        "1 - (embedding <=> $2) AS similarity "
        "FROM history_events "
        "WHERE store_id = $1 AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        store_id, query_embedding, limit,
    )
    return [dict(r) for r in rows]
