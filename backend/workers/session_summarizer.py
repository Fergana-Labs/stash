"""Server-side session summarizer worker.

Claims sessions with summary_status='need_summary', assembles a transcript
from session events, and runs one Haiku call through the agent runtime to
populate `sessions.summary`.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..config import settings
from ..database import get_pool
from ..services import agent_runtime, memory_service, prompts

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _advisory_lock(namespace: int, resource: str):
    """Yield the connection holding a pg advisory lock, or None if not acquired.

    Advisory locks are connection-scoped, so we hold a dedicated connection
    for the duration. `hashtext` returns int4, which pg_try_advisory_lock(int, int)
    expects, so locks are keyed by (namespace, hashtext(resource)).
    """
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


TICK_SECONDS = 10.0
ERROR_SLEEP_SECONDS = 30.0
MAX_ATTEMPTS = 4
ERROR_BACKOFF_BASE = timedelta(minutes=1)
BATCH_SIZE = 5
LOCK_NAMESPACE = 0x53554D52  # 'SUMR'
TRANSCRIPT_CHAR_BUDGET = 150_000
MAX_TOKENS = 2048
PER_CALL_TIMEOUT = 60.0


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


async def summarize_one(session_id: UUID, workspace_id: UUID, session_external_id: str) -> bool:
    if not await _claim_session(session_id):
        return False

    events = await memory_service.read_session_events(workspace_id, session_external_id)
    if not events:
        await get_pool().execute(
            "UPDATE sessions SET summary_status = 'failed', "
            "summary_last_attempt_at = now(), "
            "summary_last_error = 'no session events' "
            "WHERE id = $1",
            session_id,
        )
        return False

    transcript = _events_to_text(events)
    if len(transcript) > TRANSCRIPT_CHAR_BUDGET:
        transcript = transcript[:TRANSCRIPT_CHAR_BUDGET] + "\n\n[... transcript truncated ...]"

    user = prompts.render_session_summary_user(transcript, source_label="session events")

    started = datetime.now(UTC)
    try:
        result = await asyncio.wait_for(
            agent_runtime.run_agent(
                tier=agent_runtime.ModelTier.FAST,
                system=prompts.SESSION_SUMMARY_SYSTEM,
                prompt=user,
                workspace_id=workspace_id,
                tool_set=(),
                max_turns=1,
                max_output_tokens=MAX_TOKENS,
            ),
            timeout=PER_CALL_TIMEOUT,
        )
    except Exception as exc:
        logger.exception("session summarizer failed for %s: %s", session_id, exc)
        await _record_attempt(session_id, f"{type(exc).__name__}: {exc}")
        return False

    text = (result.text or "").strip()
    if not text:
        await _record_attempt(session_id, "empty summary returned")
        return False

    await _write_summary(session_id, text, result)
    latency = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "session summarizer: summarized %s (%s, in=%d out=%d, %.1fs)",
        session_id,
        result.model,
        result.input_tokens,
        result.output_tokens,
        latency,
    )
    return True


async def _tick() -> int:
    pool = get_pool()
    rows = await pool.fetch(
        """
        UPDATE sessions
        SET summary_status = 'in_progress'
        WHERE id IN (
            SELECT id FROM sessions
            WHERE summary IS NULL
              AND summary_status = 'need_summary'
              AND deleted_at IS NULL
              AND summary_attempts < $1
              AND (
                    summary_last_attempt_at IS NULL
                    OR summary_last_attempt_at <= now() - ($2::interval * power(2, LEAST(summary_attempts, 6)))
              )
            ORDER BY started_at ASC
            LIMIT $3
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, workspace_id, session_id
        """,
        MAX_ATTEMPTS,
        ERROR_BACKOFF_BASE,
        BATCH_SIZE,
    )
    if not rows:
        return 0

    done = 0
    for r in rows:
        async with _advisory_lock(LOCK_NAMESPACE, str(r["id"])) as conn:
            if conn is None:
                continue
            try:
                ok = await summarize_one(r["id"], r["workspace_id"], r["session_id"])
                if ok:
                    done += 1
            except Exception:
                logger.exception("session summarizer unexpected error for %s", r["id"])
    return done


async def run() -> None:
    if not _has_api_key():
        logger.warning("session summarizer: ANTHROPIC_API_KEY unset — worker idle")
    logger.info("session summarizer worker started")
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("session summarizer tick failed")
            await asyncio.sleep(ERROR_SLEEP_SECONDS)
            continue
        await asyncio.sleep(TICK_SECONDS)


def _has_api_key() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)
