"""AI session title generation tasks."""

from __future__ import annotations

from uuid import UUID

from ..celery_app import celery
from ..config import settings
from ..database import get_pool
from ..services import session_title_service
from ._celery_helpers import run_async

MAX_SOURCE_CHARS = 2_000
RECONCILE_BATCH_SIZE = 25


def _clean_text(text: str) -> str:
    return " ".join(text.split())


def _clean_title(text: str) -> str:
    return session_title_service.clean_generated_title(text)


async def _session_stats(workspace_id: UUID, session_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT
          h.session_id,
          COUNT(*)::INT AS event_count,
          MAX(h.created_at) AS last_at
        FROM history_events h
        JOIN sessions s ON s.workspace_id = h.workspace_id AND s.session_id = h.session_id
        WHERE h.workspace_id = $1
          AND h.session_id = $2
          AND NULLIF(BTRIM(h.content), '') IS NOT NULL
          AND s.deleted_at IS NULL
        GROUP BY h.session_id
        """,
        workspace_id,
        session_id,
    )
    return dict(row) if row else None


async def _session_source(workspace_id: UUID, session_id: str) -> str:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT event_type, tool_name, content
        FROM history_events
        WHERE workspace_id = $1
          AND session_id = $2
          AND NULLIF(BTRIM(content), '') IS NOT NULL
        ORDER BY created_at ASC, id ASC
        LIMIT 16
        """,
        workspace_id,
        session_id,
    )
    parts: list[str] = []
    for row in rows:
        label = row["event_type"] or "event"
        if row["tool_name"]:
            label = f"{label}:{row['tool_name']}"
        content = _clean_text(row["content"] or "")
        if content:
            parts.append(f"{label}: {content[:600]}")
    return "\n".join(parts)[:MAX_SOURCE_CHARS]


async def _generate_title(source: str) -> str:
    if not settings.ANTHROPIC_API_KEY:
        return ""

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=settings.ANTHROPIC_FAST_MODEL,
        max_tokens=48,
        system=(
            "Generate a concise title for a coding-agent session. "
            "Use 3 to 8 words. Name the specific task or outcome. "
            "Do not include ticket IDs, agent names, session IDs, dates, or the word session. "
            "Return only the title text."
        ),
        messages=[{"role": "user", "content": source}],
    )
    text = "\n".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    return _clean_title(text)


async def _generate_for_session(workspace_id: UUID, session_id: str) -> str:
    stats = await _session_stats(workspace_id, session_id)
    if not stats:
        return "missing"

    source_hash = session_title_service.source_hash(stats)
    pool = get_pool()
    cached = await pool.fetchrow(
        "SELECT source_hash, user_set FROM session_titles "
        "WHERE workspace_id = $1 AND session_id = $2",
        workspace_id,
        session_id,
    )
    if cached and cached["user_set"]:
        return "user-set"
    if cached and cached["source_hash"] == source_hash:
        return "fresh"

    source = await _session_source(workspace_id, session_id)
    if not source:
        return "empty"

    title = await _generate_title(source)
    if not title:
        return "unconfigured"

    await pool.execute(
        """
        INSERT INTO session_titles (workspace_id, session_id, title, source_hash)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (workspace_id, session_id) DO UPDATE SET
          title = EXCLUDED.title,
          source_hash = EXCLUDED.source_hash,
          updated_at = now()
        """,
        workspace_id,
        session_id,
        title,
        source_hash,
    )
    return "generated"


@celery.task(name="backend.tasks.session_titles.generate_session_title")
def generate_session_title(workspace_id: str, session_id: str) -> str:
    return run_async(_generate_for_session(UUID(workspace_id), session_id))


async def _reconcile_missing() -> int:
    if not settings.ANTHROPIC_API_KEY:
        return 0

    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT h.workspace_id, h.session_id
        FROM history_events h
        JOIN sessions s ON s.workspace_id = h.workspace_id AND s.session_id = h.session_id
        LEFT JOIN session_titles st
          ON st.workspace_id = h.workspace_id AND st.session_id = h.session_id
        WHERE h.workspace_id IS NOT NULL
          AND h.session_id IS NOT NULL
          AND st.session_id IS NULL
          AND s.deleted_at IS NULL
          AND NULLIF(BTRIM(h.content), '') IS NOT NULL
        GROUP BY h.workspace_id, h.session_id
        ORDER BY MAX(h.created_at) DESC
        LIMIT $1
        """,
        RECONCILE_BATCH_SIZE,
    )
    for row in rows:
        generate_session_title.delay(str(row["workspace_id"]), row["session_id"])
    return len(rows)


@celery.task(name="backend.tasks.session_titles.reconcile_missing")
def reconcile_missing() -> int:
    return run_async(_reconcile_missing())
