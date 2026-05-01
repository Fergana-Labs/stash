"""History service: structured event storage with FTS, vector search, and batch insert.

Events belong directly to a workspace (or are personal with workspace_id=NULL).
Grouped by tag_name → session_id for display.
"""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

import numpy as np

from ..database import get_pool
from . import embeddings as embedding_service

logger = logging.getLogger(__name__)


# --- Embedding helpers ---


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# Dedup map for in-flight event embeds, keyed by event_id.
_embed_tasks: dict[UUID, asyncio.Task] = {}


def _schedule_event_embed(event_id: UUID, content: str, content_hash: str) -> None:
    existing = _embed_tasks.get(event_id)
    if existing is not None and not existing.done():
        existing.cancel()
    task = asyncio.create_task(_embed_event(event_id, content, content_hash))
    _embed_tasks[event_id] = task
    task.add_done_callback(
        lambda t, eid=event_id: _embed_tasks.pop(eid, None) if _embed_tasks.get(eid) is t else None
    )


async def _embed_event(event_id: UUID, content: str, content_hash: str) -> None:
    """Fire-and-forget: embed content and update the event row.

    On failure, flips `embed_stale=true` so the reconciler retries later.
    """
    vec = await embedding_service.embed_text(content)
    pool = get_pool()
    if vec is None:
        await pool.execute(
            "UPDATE history_events SET content_hash = $1, embed_stale = TRUE WHERE id = $2",
            content_hash,
            event_id,
        )
        return
    await pool.execute(
        "UPDATE history_events SET embedding = $1, content_hash = $2, embed_stale = FALSE WHERE id = $3",
        vec,
        content_hash,
        event_id,
    )


async def _embed_events_batch(event_ids: list[UUID], contents: list[str]) -> None:
    """Fire-and-forget: embed a batch of contents and update rows."""
    vecs = await embedding_service.embed_batch(contents)
    pool = get_pool()
    hashes = [_text_hash(c) for c in contents]
    if not vecs:
        await pool.executemany(
            "UPDATE history_events SET content_hash = $1, embed_stale = TRUE WHERE id = $2",
            list(zip(hashes, event_ids)),
        )
        return
    await pool.executemany(
        "UPDATE history_events SET embedding = $1, content_hash = $2, embed_stale = FALSE WHERE id = $3",
        [(vec, h, eid) for eid, vec, h in zip(event_ids, vecs, hashes)],
    )


# --- Event CRUD ---


async def push_event(
    workspace_id: UUID | None,
    tag_name: str,
    event_type: str,
    content: str,
    created_by: UUID,
    session_id: str | None = None,
    tool_name: str | None = None,
    metadata: dict | None = None,
    attachments: list[dict] | None = None,
    created_at: datetime | None = None,
) -> dict:
    """Push a single event."""
    pool = get_pool()
    meta = metadata or {}
    if created_at is None:
        ts = datetime.now(UTC)
    elif created_at.tzinfo is None:
        ts = created_at.replace(tzinfo=UTC)
    else:
        ts = created_at
    row = await pool.fetchrow(
        "INSERT INTO history_events "
        "(workspace_id, created_by, tag_name, event_type, content, session_id, tool_name, metadata, attachments, created_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10) "
        "RETURNING id, workspace_id, created_by, tag_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at",
        workspace_id,
        created_by,
        tag_name,
        event_type,
        content,
        session_id,
        tool_name,
        meta,
        attachments,
        ts,
    )
    event = dict(row)
    if embedding_service.is_configured():
        _schedule_event_embed(event["id"], content, _text_hash(content))
    return event


async def push_events_batch(
    workspace_id: UUID | None,
    created_by: UUID,
    events: list[dict],
) -> list[dict]:
    """Batch push events. Returns list of created events."""
    pool = get_pool()
    results = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for evt in events:
                meta = evt.get("metadata", {})
                raw_ts = evt.get("created_at")
                if raw_ts is None:
                    ts = datetime.now(UTC)
                elif raw_ts.tzinfo is None:
                    ts = raw_ts.replace(tzinfo=UTC)
                else:
                    ts = raw_ts
                row = await conn.fetchrow(
                    "INSERT INTO history_events "
                    "(workspace_id, created_by, tag_name, event_type, content, "
                    "session_id, tool_name, metadata, attachments, created_at) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10) "
                    "RETURNING id, workspace_id, created_by, tag_name, event_type, "
                    "session_id, tool_name, content, metadata, attachments, created_at",
                    workspace_id,
                    created_by,
                    evt["tag_name"],
                    evt["event_type"],
                    evt["content"],
                    evt.get("session_id"),
                    evt.get("tool_name"),
                    meta,
                    evt.get("attachments"),
                    ts,
                )
                results.append(dict(row))
    if embedding_service.is_configured() and results:
        ids = [r["id"] for r in results]
        contents = [r["content"] for r in results]
        asyncio.create_task(_embed_events_batch(ids, contents))
    return results


async def get_workspace_event(event_id: UUID, workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM history_events WHERE id = $1 AND workspace_id = $2",
        event_id,
        workspace_id,
    )
    return dict(row) if row else None


async def get_personal_event(event_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM history_events "
        "WHERE id = $1 AND workspace_id IS NULL AND created_by = $2",
        event_id,
        user_id,
    )
    return dict(row) if row else None


def _build_event_filters(
    base_condition: str,
    base_args: list,
    tag_name: str | None,
    session_id: str | None,
    event_type: str | None,
    after: str | None,
    before: str | None,
) -> tuple[str, list, int]:
    """Append optional filters to a base scope condition. Returns (where, args, next_idx)."""
    conditions = [base_condition]
    args = list(base_args)
    idx = len(args) + 1

    if tag_name:
        conditions.append(f"tag_name = ${idx}")
        args.append(tag_name)
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

    return " AND ".join(conditions), args, idx


async def _query_events(
    where: str,
    args: list,
    limit_idx: int,
    limit: int,
) -> tuple[list[dict], bool]:
    pool = get_pool()
    args = [*args, limit + 1]
    rows = await pool.fetch(
        f"SELECT id, workspace_id, created_by, tag_name, event_type, session_id, "
        f"tool_name, content, metadata, attachments, created_at "
        f"FROM history_events WHERE {where} "
        f"ORDER BY created_at ASC LIMIT ${limit_idx}",
        *args,
    )
    events = [dict(r) for r in rows]
    has_more = len(events) > limit
    if has_more:
        events = events[:limit]
    return events, has_more


async def query_workspace_events(
    workspace_id: UUID,
    tag_name: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], bool]:
    """Query events in a workspace. Returns (events, has_more)."""
    limit = min(limit, 200)
    where, args, next_idx = _build_event_filters(
        "workspace_id = $1",
        [workspace_id],
        tag_name,
        session_id,
        event_type,
        after,
        before,
    )
    return await _query_events(where, args, next_idx, limit)


async def query_personal_events(
    user_id: UUID,
    tag_name: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], bool]:
    """Query personal (non-workspace) events for a user. Returns (events, has_more)."""
    limit = min(limit, 200)
    where, args, next_idx = _build_event_filters(
        "workspace_id IS NULL AND created_by = $1",
        [user_id],
        tag_name,
        session_id,
        event_type,
        after,
        before,
    )
    return await _query_events(where, args, next_idx, limit)


async def search_workspace_events(
    workspace_id: UUID,
    query: str,
    limit: int = 50,
) -> list[dict]:
    """Full-text search on workspace events."""
    pool = get_pool()
    limit = min(limit, 200)
    rows = await pool.fetch(
        "SELECT id, workspace_id, created_by, tag_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at, "
        "ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', $2)) AS rank "
        "FROM history_events "
        "WHERE workspace_id = $1 AND to_tsvector('english', content) @@ websearch_to_tsquery('english', $2) "
        "ORDER BY rank DESC LIMIT $3",
        workspace_id,
        query,
        limit,
    )
    return [dict(r) for r in rows]


async def search_personal_events(
    user_id: UUID,
    query: str,
    limit: int = 50,
) -> list[dict]:
    """Full-text search on personal events."""
    pool = get_pool()
    limit = min(limit, 200)
    rows = await pool.fetch(
        "SELECT id, workspace_id, created_by, tag_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at, "
        "ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', $2)) AS rank "
        "FROM history_events "
        "WHERE workspace_id IS NULL AND created_by = $1 "
        "AND to_tsvector('english', content) @@ websearch_to_tsquery('english', $2) "
        "ORDER BY rank DESC LIMIT $3",
        user_id,
        query,
        limit,
    )
    return [dict(r) for r in rows]


async def search_workspace_events_vector(
    workspace_id: UUID,
    query_embedding: np.ndarray,
    limit: int = 20,
) -> list[dict]:
    """Semantic vector search on workspace events."""
    pool = get_pool()
    limit = min(limit, 200)
    rows = await pool.fetch(
        "SELECT id, workspace_id, created_by, tag_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at, "
        "1 - (embedding <=> $2) AS similarity "
        "FROM history_events "
        "WHERE workspace_id = $1 AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        workspace_id,
        query_embedding,
        limit,
    )
    return [dict(r) for r in rows]


async def search_personal_events_vector(
    user_id: UUID,
    query_embedding: np.ndarray,
    limit: int = 20,
) -> list[dict]:
    """Semantic vector search on personal events."""
    pool = get_pool()
    limit = min(limit, 200)
    rows = await pool.fetch(
        "SELECT id, workspace_id, created_by, tag_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at, "
        "1 - (embedding <=> $2) AS similarity "
        "FROM history_events "
        "WHERE workspace_id IS NULL AND created_by = $1 AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        user_id,
        query_embedding,
        limit,
    )
    return [dict(r) for r in rows]


# --- Aggregate queries ---


async def query_all_user_events(
    user_id: UUID,
    tag_name: str | None = None,
    event_type: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], bool]:
    """Events across ALL accessible workspaces + personal, with filters."""
    pool = get_pool()
    limit = min(limit, 200)

    conditions = [
        "(he.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1) "
        "OR (he.workspace_id IS NULL AND he.created_by = $1))"
    ]
    args: list = [user_id]
    idx = 2

    if tag_name:
        conditions.append(f"he.tag_name = ${idx}")
        args.append(tag_name)
        idx += 1
    if event_type:
        conditions.append(f"he.event_type = ${idx}")
        args.append(event_type)
        idx += 1
    if after:
        conditions.append(f"he.created_at > ${idx}")
        args.append(after)
        idx += 1
    if before:
        conditions.append(f"he.created_at < ${idx}")
        args.append(before)
        idx += 1

    where = " AND ".join(conditions)
    args.append(limit + 1)

    rows = await pool.fetch(
        f"SELECT he.id, he.workspace_id, he.created_by, he.tag_name, he.event_type, "
        f"he.session_id, he.tool_name, he.content, he.metadata, he.created_at, "
        f"w.name AS workspace_name, "
        f"COALESCE(u.display_name, u.name) AS created_by_name "
        f"FROM history_events he "
        f"LEFT JOIN workspaces w ON w.id = he.workspace_id "
        f"LEFT JOIN users u ON u.id = he.created_by "
        f"WHERE {where} "
        f"ORDER BY he.created_at DESC LIMIT ${idx}",
        *args,
    )

    events = [dict(r) for r in rows]
    has_more = len(events) > limit
    if has_more:
        events = events[:limit]
    return events, has_more


async def delete_workspace_tag_events(tag_name: str, workspace_id: UUID) -> int:
    """Delete all workspace events for a given tag. Returns count deleted."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM history_events WHERE tag_name = $1 AND workspace_id = $2",
        tag_name,
        workspace_id,
    )
    return int(result.split()[-1]) if result else 0


async def delete_personal_tag_events(tag_name: str, user_id: UUID) -> int:
    """Delete all personal events for a given tag. Returns count deleted."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM history_events WHERE tag_name = $1 AND workspace_id IS NULL AND created_by = $2",
        tag_name,
        user_id,
    )
    return int(result.split()[-1]) if result else 0


async def get_workspace_event_count(workspace_id: UUID) -> int:
    """Count events in a workspace."""
    pool = get_pool()
    return (
        await pool.fetchval(
            "SELECT COUNT(*) FROM history_events WHERE workspace_id = $1",
            workspace_id,
        )
        or 0
    )
