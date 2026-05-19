"""Session summarizer task.

Replaces `workers/session_summarizer.py`.

Two tasks here:
- `summarize_session(session_id)` — runs the LLM summary for one session.
  Called on-demand via `.delay()`, and also dispatched by `enqueue_pending`.
- `enqueue_pending` — Beat-scheduled (every 10s in `celery_app.py`).
  Finds sessions in `summary_status='need_summary'` (with attempt backoff
  matching the previous worker) and dispatches `summarize_session.delay()`.

Sessions are upserted incrementally as events stream in (see
`services/session_service.upsert_session`), so there's no single
"upload finished" hook to attach a `.delay()` to — periodic discovery
matches the existing semantics most faithfully.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..celery_app import celery
from ..config import settings
from ..database import get_pool
from ..services import agent_runtime, memory_service, prompts
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
ERROR_BACKOFF_BASE = timedelta(minutes=1)
BATCH_SIZE = 5
LOCK_NAMESPACE = 0x53554D52  # 'SUMR'
TRANSCRIPT_CHAR_BUDGET = 150_000
MAX_TOKENS = 2048
PER_CALL_TIMEOUT = 60.0


@asynccontextmanager
async def _advisory_lock(namespace: int, resource: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        got = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1, hashtext($2))",
            namespace,
            resource,
        )
        if not got:
            yield None
            return
        try:
            yield conn
        finally:
            try:
                await conn.execute(
                    "SELECT pg_advisory_unlock($1, hashtext($2))",
                    namespace,
                    resource,
                )
            except Exception:
                pass


def _events_to_text(events: list[dict]) -> str:
    lines = []
    for ev in events:
        label = ev.get("event_type") or ""
        tool = ev.get("tool_name") or ""
        if tool:
            label = f"{label}:{tool}"
        content = ev.get("content") or ""
        created_at = ev.get("created_at")
        ts = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at or "")
        lines.append(f"[{ts}] {label}\n{content}")
    return "\n\n---\n\n".join(lines)


async def _record_attempt(session_id: UUID, error: str | None) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE sessions SET summary_attempts = summary_attempts + 1, "
        "summary_last_attempt_at = now(), summary_last_error = $2 "
        "WHERE id = $1",
        session_id,
        error,
    )


async def _claim_session(session_id: UUID) -> bool:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE sessions SET summary_status = 'in_progress' "
        "WHERE id = $1 "
        "AND summary IS NULL "
        "AND summary_status IN ('need_summary', 'in_progress') "
        "RETURNING id",
        session_id,
    )
    return row is not None


async def _write_summary(
    session_id: UUID,
    summary: str,
    result: agent_runtime.AgentResult,
) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE sessions SET summary = $1, summary_status = 'done', "
        "finished_at = COALESCE(finished_at, now()), "
        "summary_model = $2, summary_input_tokens = $3, summary_output_tokens = $4, "
        "summary_last_error = NULL "
        "WHERE id = $5",
        summary,
        result.model,
        result.input_tokens,
        result.output_tokens,
        session_id,
    )


async def _summarize_one(session_row_id: UUID) -> bool:
    pool = get_pool()
    sess = await pool.fetchrow(
        "SELECT id, workspace_id, session_id FROM sessions WHERE id = $1",
        session_row_id,
    )
    if not sess:
        return False

    async with _advisory_lock(LOCK_NAMESPACE, str(sess["id"])) as conn:
        if conn is None:
            return False

        if not await _claim_session(sess["id"]):
            return False

        events = await memory_service.read_session_events(sess["workspace_id"], sess["session_id"])
        if not events:
            await pool.execute(
                "UPDATE sessions SET summary_status = 'failed', "
                "summary_last_attempt_at = now(), "
                "summary_last_error = 'no session events' "
                "WHERE id = $1",
                sess["id"],
            )
            return False

        transcript = _events_to_text(events)
        if len(transcript) > TRANSCRIPT_CHAR_BUDGET:
            transcript = transcript[:TRANSCRIPT_CHAR_BUDGET] + "\n\n[... transcript truncated ...]"

        user_prompt = prompts.render_session_summary_user(transcript, source_label="session events")

        started = datetime.now(UTC)
        try:
            result = await asyncio.wait_for(
                agent_runtime.run_agent(
                    tier=agent_runtime.ModelTier.FAST,
                    system=prompts.SESSION_SUMMARY_SYSTEM,
                    prompt=user_prompt,
                    workspace_id=sess["workspace_id"],
                    tool_set=(),
                    max_turns=1,
                    max_output_tokens=MAX_TOKENS,
                ),
                timeout=PER_CALL_TIMEOUT,
            )
        except Exception as exc:
            logger.exception("session summarizer failed for %s: %s", sess["id"], exc)
            await _record_attempt(sess["id"], f"{type(exc).__name__}: {exc}")
            return False

        text = (result.text or "").strip()
        if not text:
            await _record_attempt(sess["id"], "empty summary returned")
            return False

        await _write_summary(sess["id"], text, result)
        latency = (datetime.now(UTC) - started).total_seconds()
        logger.info(
            "session summarizer: summarized %s (%s, in=%d out=%d, %.1fs)",
            sess["id"],
            result.model,
            result.input_tokens,
            result.output_tokens,
            latency,
        )
        return True


@celery.task(name="backend.tasks.summarize.summarize_session")
def summarize_session(session_row_id: str) -> bool:
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("session summarizer: ANTHROPIC_API_KEY unset — skipping")
        return False
    return run_async(_summarize_one(UUID(session_row_id)))


async def _enqueue_pending() -> int:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id FROM sessions
        WHERE summary IS NULL
          AND summary_status = 'need_summary'
          AND summary_attempts < $1
          AND (
                summary_last_attempt_at IS NULL
                OR summary_last_attempt_at <= now() - ($2::interval * power(2, LEAST(summary_attempts, 6)))
          )
        ORDER BY started_at ASC
        LIMIT $3
        """,
        MAX_ATTEMPTS,
        ERROR_BACKOFF_BASE,
        BATCH_SIZE,
    )
    for r in rows:
        summarize_session.delay(str(r["id"]))
    return len(rows)


@celery.task(name="backend.tasks.summarize.enqueue_pending")
def enqueue_pending() -> int:
    return run_async(_enqueue_pending())
