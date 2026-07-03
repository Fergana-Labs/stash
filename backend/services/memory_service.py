"""Session event service: structured agent event storage with FTS, vector search, and batch insert.

Events belong directly to a scope (or are personal with owner_user_id=NULL).
Grouped by agent_name → session_id for display.
"""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import numpy as np

from ..database import get_pool
from . import embeddings as embedding_service
from . import github_pr_service, linear_ticket_service, permission_service, session_service

logger = logging.getLogger(__name__)


# --- Embedding helpers ---


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _normalize_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


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
    owner_user_id: UUID | None,
    agent_name: str,
    event_type: str,
    content: str,
    created_by: UUID,
    session_id: str,
    session_folder_id: UUID | None = None,
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
    else:
        ts = _normalize_ts(created_at)
    row = await pool.fetchrow(
        "INSERT INTO history_events "
        "(owner_user_id, created_by, agent_name, event_type, content, session_id, tool_name, metadata, attachments, created_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10) "
        "RETURNING id, owner_user_id, created_by, agent_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at",
        owner_user_id,
        created_by,
        agent_name,
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
    if owner_user_id is not None and session_id:
        session = await session_service.upsert_session(
            owner_user_id,
            session_id,
            agent_name=agent_name,
            cwd=meta.get("cwd") if isinstance(meta.get("cwd"), str) else None,
            created_by=created_by,
            session_folder_id=session_folder_id,
        )
        if linear_ticket_service.has_ticket_hint([content]):
            await linear_ticket_service.sync_session_labels(
                owner_user_id, session["id"], session_id
            )
        if github_pr_service.has_pull_request_hint([content]):
            github_pr_service.enqueue_session_discovery(session["id"])
    return event


async def push_events_batch(
    owner_user_id: UUID | None,
    created_by: UUID,
    events: list[dict],
) -> list[dict]:
    """Batch push events in a single round-trip.

    Previously this issued N separate INSERTs in a transaction, which was
    fine for small batches from the live hooks but turned onboarding (a
    user importing hundreds of historical sessions, thousands of rows
    each) into a multi-minute affair. UNNEST pushes the whole batch in
    one statement; insertion of 1000 rows on Neon goes from ~10s to ~200ms.
    """
    if not events:
        return []
    pool = get_pool()
    now = datetime.now(UTC)

    agent_names = [e["agent_name"] for e in events]
    event_types = [e["event_type"] for e in events]
    contents = [e["content"] for e in events]
    session_ids = [e.get("session_id") for e in events]
    tool_names = [e.get("tool_name") for e in events]
    metadatas = [json.dumps(e.get("metadata") or {}) for e in events]
    attachments = [json.dumps(e["attachments"]) if e.get("attachments") else None for e in events]
    timestamps = [_normalize_ts(e["created_at"]) if e.get("created_at") else now for e in events]

    rows = await pool.fetch(
        """
        INSERT INTO history_events
            (owner_user_id, created_by, agent_name, event_type, content,
             session_id, tool_name, metadata, attachments, created_at)
        SELECT $1::uuid, $2::uuid, u.an, u.et, u.c,
               u.sid, u.tn, u.md::jsonb,
               CASE WHEN u.att IS NULL THEN NULL ELSE u.att::jsonb END,
               u.ts
        FROM UNNEST(
            $3::varchar[], $4::varchar[], $5::text[],
            $6::varchar[], $7::varchar[],
            $8::text[], $9::text[], $10::timestamptz[]
        ) AS u(an, et, c, sid, tn, md, att, ts)
        RETURNING id, owner_user_id, created_by, agent_name, event_type,
                  session_id, tool_name, content, metadata, attachments, created_at
        """,
        owner_user_id,
        created_by,
        agent_names,
        event_types,
        contents,
        session_ids,
        tool_names,
        metadatas,
        attachments,
        timestamps,
    )
    results = [dict(r) for r in rows]
    await _upsert_sessions_for_events(owner_user_id, created_by, events)
    if embedding_service.is_configured() and results:
        ids = [r["id"] for r in results]
        contents_for_embed = [r["content"] for r in results]
        asyncio.create_task(_embed_events_batch(ids, contents_for_embed))
    return results


async def _upsert_sessions_for_events(
    owner_user_id: UUID | None,
    created_by: UUID,
    events: list[dict],
) -> None:
    if owner_user_id is None:
        return

    sessions: dict[str, dict] = {}
    for event in events:
        session_id = event.get("session_id")
        if not session_id or session_id in sessions:
            continue
        metadata = event.get("metadata") or {}
        sessions[session_id] = {
            "agent_name": event.get("agent_name") or "",
            "cwd": metadata.get("cwd") if isinstance(metadata.get("cwd"), str) else None,
        }

    for session_id, session in sessions.items():
        row = await session_service.upsert_session(
            owner_user_id,
            session_id,
            agent_name=session["agent_name"],
            cwd=session["cwd"],
            created_by=created_by,
        )
        contents = [
            event.get("content") or "" for event in events if event.get("session_id") == session_id
        ]
        if linear_ticket_service.has_ticket_hint(contents):
            await linear_ticket_service.sync_session_labels(owner_user_id, row["id"], session_id)
        if github_pr_service.has_pull_request_hint(contents):
            github_pr_service.enqueue_session_discovery(row["id"])


def readable_session_event_condition(event_alias: str, user_arg: int) -> str:
    """SQL predicate: may user ${user_arg} read the session this history_events
    row belongs to? Resolves the row to its session and delegates to the one
    access predicate for 'session' (owner / a live session or session-folder
    share / a public session folder) — no duplicated share logic."""
    session_access = permission_service.readable_content_condition(
        "session", "readable_session", user_arg
    )
    return f"""
        (
          EXISTS (
            SELECT 1
            FROM sessions readable_session
            WHERE readable_session.owner_user_id = {event_alias}.owner_user_id
              AND readable_session.session_id = {event_alias}.session_id
              AND readable_session.deleted_at IS NULL
              AND {session_access}
          )
        )
    """


async def can_read_session(owner_user_id: UUID, session_id: str, user_id: UUID) -> bool:
    session = await session_service.get_session(owner_user_id, session_id)
    if not session:
        return False
    return await permission_service.check_access(
        "session",
        session["id"],
        user_id,
        owner_user_id=owner_user_id,
    )


# Event types the session viewer renders as turns. The user/assistant split
# lives in transcripts._event_role; this is the single source of truth for
# which rows count as renderable turns, shared by the paginated reader's
# LIMIT/OFFSET so a page offset equals a turn ordinal.
USER_EVENT_TYPES = ("user_message", "prompt", "user")
ASSISTANT_EVENT_TYPES = ("assistant_message", "assistant", "tool_use", "tool_call", "tool_result")
RENDERABLE_EVENT_TYPES = USER_EVENT_TYPES + ASSISTANT_EVENT_TYPES


async def read_session_events(
    owner_user_id: UUID,
    session_id: str,
    user_id: UUID | None = None,
) -> list[dict]:
    """Ordered events for a session within a scope. The canonical
    source for session-thread rendering — replaces reading the R2 transcript
    blob."""
    if user_id is not None and not await can_read_session(owner_user_id, session_id, user_id):
        return []

    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, agent_name, event_type, tool_name, content, metadata, created_at "
        "FROM history_events WHERE owner_user_id = $1 AND session_id = $2 "
        "ORDER BY created_at, id",
        owner_user_id,
        session_id,
    )
    return [dict(r) for r in rows]


async def read_session_events_page(
    owner_user_id: UUID,
    session_id: str,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """One page of renderable session events (oldest first) plus the total
    renderable count, for the lazily-loaded transcript viewer. Filtering to
    renderable event types keeps the offset aligned with the turn ordinal the
    viewer shows. Callers enforce readability."""
    pool = get_pool()
    total = await pool.fetchval(
        "SELECT COUNT(*) FROM history_events "
        "WHERE owner_user_id = $1 AND session_id = $2 AND event_type = ANY($3::text[])",
        owner_user_id,
        session_id,
        list(RENDERABLE_EVENT_TYPES),
    )
    rows = await pool.fetch(
        "SELECT id, agent_name, event_type, tool_name, content, metadata, created_at "
        "FROM history_events "
        "WHERE owner_user_id = $1 AND session_id = $2 AND event_type = ANY($3::text[]) "
        "ORDER BY created_at, id LIMIT $4 OFFSET $5",
        owner_user_id,
        session_id,
        list(RENDERABLE_EVENT_TYPES),
        limit,
        offset,
    )
    return [dict(r) for r in rows], total


async def list_scope_sessions(owner_user_id: UUID, user_id: UUID) -> list[dict]:
    """One row per session_id in this scope. Powers the spine sessions
    list — replaces a SELECT against session_transcripts."""
    pool = get_pool()
    rows = await pool.fetch(
        "WITH title_sources AS ( "
        "  SELECT DISTINCT ON (ht.owner_user_id, ht.session_id) "
        "    ht.owner_user_id, "
        "    ht.session_id, "
        "    LEFT(ht.content, 240) AS title_source "
        "  FROM history_events ht "
        "  WHERE ht.owner_user_id = $1 "
        "    AND ht.session_id IS NOT NULL "
        "    AND NULLIF(BTRIM(ht.content), '') IS NOT NULL "
        "  ORDER BY ht.owner_user_id, ht.session_id, CASE "
        "    WHEN ht.event_type IN ('user_message', 'user_prompt', 'prompt', 'message', 'user') THEN 0 "
        "    WHEN ht.event_type IN ('assistant_message', 'assistant') THEN 1 "
        "    ELSE 2 "
        "  END, ht.created_at, ht.id "
        ") "
        "SELECT h.session_id, "
        "       s.id::text AS id, "
        f"       {linear_ticket_service.sql_json_agg('s')} AS linear_tickets, "
        "       MAX(h.agent_name) AS agent_name, "
        "       (ARRAY_AGG(NULLIF(u.display_name, '') ORDER BY h.created_at) "
        "        FILTER (WHERE NULLIF(u.display_name, '') IS NOT NULL))[1] AS user_name, "
        "       title_sources.title_source, "
        "       COUNT(*)::INT AS event_count, "
        "       SUM(LENGTH(h.content))::BIGINT AS size_bytes, "
        "       MIN(h.created_at) AS started_at, "
        "       MAX(h.created_at) AS last_at "
        "FROM history_events h "
        "JOIN sessions s ON s.owner_user_id = h.owner_user_id AND s.session_id = h.session_id "
        "LEFT JOIN title_sources ON title_sources.owner_user_id = h.owner_user_id "
        "  AND title_sources.session_id = h.session_id "
        "LEFT JOIN users u ON u.id = h.created_by "
        "WHERE h.owner_user_id = $1 AND h.session_id IS NOT NULL "
        f"AND {readable_session_event_condition('h', 2)} "
        "GROUP BY h.session_id, s.id, title_sources.title_source "
        "ORDER BY last_at DESC, user_name ASC, session_id ASC",
        owner_user_id,
        user_id,
    )
    sessions = [dict(r) for r in rows]
    for session in sessions:
        if not session["user_name"]:
            raise RuntimeError(f"Session {session['session_id']} has no author display_name")
    return sessions


async def get_scope_event(event_id: UUID, owner_user_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM history_events he WHERE he.id = $1 AND he.owner_user_id = $2 "
        f"AND {readable_session_event_condition('he', 3)}",
        event_id,
        owner_user_id,
        user_id,
    )
    return dict(row) if row else None


async def get_personal_event(event_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM history_events "
        "WHERE id = $1 AND owner_user_id IS NULL AND created_by = $2",
        event_id,
        user_id,
    )
    return dict(row) if row else None


def _build_event_filters(
    base_condition: str,
    base_args: list,
    agent_name: str | None,
    session_id: str | None,
    event_type: str | None,
    after: datetime | None,
    before: datetime | None,
) -> tuple[str, list, int]:
    """Append optional filters to a base scope condition. Returns (where, args, next_idx)."""
    conditions = [base_condition]
    args = list(base_args)
    idx = len(args) + 1

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
        args.append(_normalize_ts(after))
        idx += 1
    if before:
        conditions.append(f"created_at < ${idx}")
        args.append(_normalize_ts(before))
        idx += 1

    return " AND ".join(conditions), args, idx


async def _query_events(
    where: str,
    args: list,
    limit_idx: int,
    limit: int,
    order: str = "desc",
) -> tuple[list[dict], bool]:
    pool = get_pool()
    direction = "ASC" if order == "asc" else "DESC"
    args = [*args, limit + 1]
    rows = await pool.fetch(
        f"SELECT id, owner_user_id, created_by, agent_name, event_type, session_id, "
        f"tool_name, content, metadata, attachments, created_at "
        f"FROM history_events WHERE {where} "
        f"ORDER BY created_at {direction} LIMIT ${limit_idx}",
        *args,
    )
    events = [dict(r) for r in rows]
    has_more = len(events) > limit
    if has_more:
        events = events[:limit]
    return events, has_more


async def query_scope_events(
    owner_user_id: UUID,
    user_id: UUID,
    agent_name: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    limit: int = 50,
    order: str = "desc",
) -> tuple[list[dict], bool]:
    """Query events in a scope. Returns (events, has_more)."""
    limit = min(limit, 200)
    where, args, next_idx = _build_event_filters(
        f"owner_user_id = $1 AND {readable_session_event_condition('history_events', 2)}",
        [owner_user_id, user_id],
        agent_name,
        session_id,
        event_type,
        after,
        before,
    )
    return await _query_events(where, args, next_idx, limit, order=order)


async def query_personal_events(
    user_id: UUID,
    agent_name: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    limit: int = 50,
    order: str = "desc",
) -> tuple[list[dict], bool]:
    """Query personal (non-scope) events for a user. Returns (events, has_more)."""
    limit = min(limit, 200)
    where, args, next_idx = _build_event_filters(
        "owner_user_id IS NULL AND created_by = $1",
        [user_id],
        agent_name,
        session_id,
        event_type,
        after,
        before,
    )
    return await _query_events(where, args, next_idx, limit, order=order)


async def search_scope_events(
    owner_user_id: UUID,
    user_id: UUID,
    query: str,
    limit: int = 50,
) -> list[dict]:
    """Full-text search on scope events."""
    pool = get_pool()
    limit = min(limit, 200)
    rows = await pool.fetch(
        "SELECT id, owner_user_id, created_by, agent_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at, "
        "ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', $2)) AS rank "
        "FROM history_events "
        "WHERE owner_user_id = $1 "
        f"AND {readable_session_event_condition('history_events', 4)} "
        "AND to_tsvector('english', content) @@ websearch_to_tsquery('english', $2) "
        "ORDER BY rank DESC LIMIT $3",
        owner_user_id,
        query,
        limit,
        user_id,
    )
    return [dict(r) for r in rows]


async def recent_scope_events(
    owner_user_id: UUID,
    user_id: UUID,
    days: int = 7,
    limit: int = 20,
) -> list[dict]:
    """Most recent readable events in a window — the temporal counterpart to
    full-text search, for "what was I working on lately" questions."""
    pool = get_pool()
    limit = min(limit, 100)
    rows = await pool.fetch(
        "SELECT id, agent_name, event_type, session_id, tool_name, content, created_at "
        "FROM history_events "
        "WHERE owner_user_id = $1 "
        f"AND {readable_session_event_condition('history_events', 4)} "
        "AND created_at >= now() - ($2 || ' days')::interval "
        "ORDER BY created_at DESC LIMIT $3",
        owner_user_id,
        str(days),
        limit,
        user_id,
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
        "SELECT id, owner_user_id, created_by, agent_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at, "
        "ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', $2)) AS rank "
        "FROM history_events "
        "WHERE owner_user_id IS NULL AND created_by = $1 "
        "AND to_tsvector('english', content) @@ websearch_to_tsquery('english', $2) "
        "ORDER BY rank DESC LIMIT $3",
        user_id,
        query,
        limit,
    )
    return [dict(r) for r in rows]


async def search_scope_events_vector(
    owner_user_id: UUID,
    user_id: UUID,
    query_embedding: np.ndarray,
    limit: int = 20,
) -> list[dict]:
    """Semantic vector search on scope events."""
    pool = get_pool()
    limit = min(limit, 200)
    rows = await pool.fetch(
        "SELECT id, owner_user_id, created_by, agent_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at, "
        "1 - (embedding <=> $2) AS similarity "
        "FROM history_events "
        "WHERE owner_user_id = $1 "
        f"AND {readable_session_event_condition('history_events', 4)} "
        "AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        owner_user_id,
        query_embedding,
        limit,
        user_id,
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
        "SELECT id, owner_user_id, created_by, agent_name, event_type, session_id, "
        "tool_name, content, metadata, attachments, created_at, "
        "1 - (embedding <=> $2) AS similarity "
        "FROM history_events "
        "WHERE owner_user_id IS NULL AND created_by = $1 AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        user_id,
        query_embedding,
        limit,
    )
    return [dict(r) for r in rows]


# --- Aggregate queries ---


async def query_all_user_events(
    user_id: UUID,
    agent_name: str | None = None,
    event_type: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    limit: int = 50,
    order: str = "desc",
) -> tuple[list[dict], bool]:
    """Events across ALL accessible scopes + personal, with filters."""
    pool = get_pool()
    limit = min(limit, 200)
    direction = "ASC" if order == "asc" else "DESC"

    conditions = [
        f"(he.owner_user_id IN {permission_service.accessible_scope_ids_sql(1)} "
        "OR (he.owner_user_id IS NULL AND he.created_by = $1))",
        f"(he.owner_user_id IS NULL OR {readable_session_event_condition('he', 1)})",
    ]
    args: list = [user_id]
    idx = 2

    if agent_name:
        conditions.append(f"he.agent_name = ${idx}")
        args.append(agent_name)
        idx += 1
    if event_type:
        conditions.append(f"he.event_type = ${idx}")
        args.append(event_type)
        idx += 1
    if after:
        conditions.append(f"he.created_at > ${idx}")
        args.append(_normalize_ts(after))
        idx += 1
    if before:
        conditions.append(f"he.created_at < ${idx}")
        args.append(_normalize_ts(before))
        idx += 1

    where = " AND ".join(conditions)
    args.append(limit + 1)

    rows = await pool.fetch(
        f"SELECT he.id, he.owner_user_id, he.created_by, he.agent_name, he.event_type, "
        f"he.session_id, he.tool_name, he.content, he.metadata, he.created_at, "
        f"owner.display_name AS owner_name, "
        f"u.display_name AS created_by_name "
        f"FROM history_events he "
        f"LEFT JOIN users owner ON owner.id = he.owner_user_id "
        f"LEFT JOIN users u ON u.id = he.created_by "
        f"WHERE {where} "
        f"ORDER BY he.created_at {direction} LIMIT ${idx}",
        *args,
    )

    events = [dict(r) for r in rows]
    has_more = len(events) > limit
    if has_more:
        events = events[:limit]
    return events, has_more


async def delete_scope_agent_events(agent_name: str, owner_user_id: UUID) -> int:
    """Delete all scope events for a given agent. Returns count deleted."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM history_events WHERE agent_name = $1 AND owner_user_id = $2",
        agent_name,
        owner_user_id,
    )
    return int(result.split()[-1]) if result else 0


async def delete_personal_agent_events(agent_name: str, user_id: UUID) -> int:
    """Delete all personal events for a given agent. Returns count deleted."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM history_events WHERE agent_name = $1 AND owner_user_id IS NULL AND created_by = $2",
        agent_name,
        user_id,
    )
    return int(result.split()[-1]) if result else 0


async def get_scope_event_count(owner_user_id: UUID) -> int:
    """Count events in a scope."""
    pool = get_pool()
    return (
        await pool.fetchval(
            "SELECT COUNT(*) FROM history_events WHERE owner_user_id = $1",
            owner_user_id,
        )
        or 0
    )
