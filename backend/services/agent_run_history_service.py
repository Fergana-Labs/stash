"""Run history for a named agent — a paginated list of its past scheduled runs.

A scheduled run is one full turn into a fresh per-run session, and each turn is
already persisted as `history_events` under a per-run session id:

  - Memory curator:  `agent-curate-{agent_id}-{stamp}`
  - other scheduled: `agent-sched-{agent_id}-{stamp}`

(see sprite_agent_service.build_scheduled_turn for the canonical prefixes).

This service derives a run's status, timing, and tool count from those events
plus the live turn lock in Redis — no new storage. The endpoints sit on the
agents router because every run belongs to exactly one agent.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ..config import settings
from ..database import get_pool
from . import agent_service, sprite_agent_service

# Status values a run can surface to the UI.
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_RUNNING = "running"
STATUS_INTERRUPTED = "interrupted"
STATUS_STOPPED = "stopped"

# Failure marker written by sprite_agent_service._record_run_failure. Any
# assistant_message in a run's session whose content starts with this is the
# run's terminal error, not a real answer.
_FAILURE_PREFIX = "⚠️ Agent run failed:"

# The note sprite_agent_service writes when a turn is stopped mid-run
# (TurnStopped). A scheduled run whose terminal assistant_message is this
# was stopped, not completed — the user must be able to tell them apart.
_STOPPED_NOTE = "⏹ Stopped by user."

# Per-run session id prefixes (must match sprite_agent_service.build_scheduled_turn).
_CURATE_PREFIX = "agent-curate-"
_SCHED_PREFIX = "agent-sched-"


def _scheduled_session_prefixes(agent_id: UUID) -> tuple[str, str]:
    """The two per-run session id prefixes for this agent's scheduled runs."""
    id_str = str(agent_id)
    return f"{_CURATE_PREFIX}{id_str}-", f"{_SCHED_PREFIX}{id_str}-"


async def list_runs(user_id: UUID, agent_id: UUID, limit: int, offset: int) -> dict:
    """Paginated past scheduled runs of one agent, newest first.

    Each run is derived from the history_events of its per-run session:

      - started_at  — the session's first event timestamp (always the
        user_message carrying the run's prompt).
      - finished_at — the session's last event timestamp, but only when the
        run recorded a terminal event (completed or failed). Null while a turn
        is still running, and for an interrupted run whose last event is just
        mid-turn activity rather than an end.
      - duration_seconds — finished_at - started_at, or null when the run
        has not ended (running or interrupted).
      - event_count / tool_count — straight COUNTs over the session's events.
      - status — failed when the session's final assistant_message is the
        failure marker; stopped when it is the user-stop note; completed when
        it is any other assistant_message; else running when the turn lock is
        held; else interrupted (the turn died before recording any terminal
        event — e.g. a worker kill mid-run).
      - error — the failure marker's text, only when status is failed.

    Only the agent's owner can read these runs: the router authorizes via
    agent_service.get_agent first.
    """
    await agent_service.get_agent(user_id, agent_id)

    curate_prefix, sched_prefix = _scheduled_session_prefixes(agent_id)

    pool = get_pool()
    rows = await pool.fetch(
        """
        WITH run_sessions AS (
            SELECT DISTINCT session_id
            FROM history_events
            WHERE owner_user_id = $1
              AND session_id IS NOT NULL
              AND (session_id LIKE $2 OR session_id LIKE $3)
        ),
        per_session AS (
            SELECT
                he.session_id,
                MAX(he.agent_name) AS agent_name,
                MIN(he.created_at) AS started_at,
                MAX(he.created_at) AS finished_at,
                COUNT(*)::int AS event_count,
                COUNT(*) FILTER (WHERE he.event_type = 'tool_use')::int AS tool_count,
                -- the terminal assistant_message: the last one in the session
                (ARRAY_AGG(he.content ORDER BY he.created_at DESC, he.id DESC)
                 FILTER (WHERE he.event_type = 'assistant_message'))[1] AS final_text
            FROM history_events he
            JOIN run_sessions rs ON rs.session_id = he.session_id
            WHERE he.owner_user_id = $1
            GROUP BY he.session_id
        )
        SELECT session_id, agent_name, started_at, finished_at,
               event_count, tool_count, final_text
        FROM per_session
        ORDER BY started_at DESC, session_id DESC
        LIMIT $4 OFFSET $5
        """,
        user_id,
        curate_prefix + "%",
        sched_prefix + "%",
        limit,
        offset,
    )

    runs = []
    running_sessions = await _running_sessions([r["session_id"] for r in rows])
    for row in rows:
        session_id = row["session_id"]
        status, error = _derive_status(row["final_text"], running_sessions.get(session_id))
        started_at: datetime = row["started_at"]
        last_event_at: datetime = row["finished_at"]
        # finished_at / duration mean "the run ended here". Only a run that
        # recorded a real terminal event (completed, failed, or stopped)
        # ended; a running or interrupted run's last-event time is just the
        # latest activity, not an end, so the UI must not present it as one.
        if status in (STATUS_COMPLETED, STATUS_FAILED, STATUS_STOPPED):
            finished_at = last_event_at
            duration = (last_event_at - started_at).total_seconds()
        else:
            finished_at = None
            duration = None
        runs.append(
            {
                "session_id": session_id,
                "agent_name": row["agent_name"],
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_seconds": duration,
                "event_count": row["event_count"],
                "tool_count": row["tool_count"],
                "status": status,
                "error": error,
                "app_url": _run_app_url(session_id),
            }
        )

    total = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT session_id)
        FROM history_events
        WHERE owner_user_id = $1
          AND session_id IS NOT NULL
          AND (session_id LIKE $2 OR session_id LIKE $3)
        """,
        user_id,
        curate_prefix + "%",
        sched_prefix + "%",
    )

    has_more = (offset + len(runs)) < total
    return {"runs": runs, "has_more": has_more}


async def _running_sessions(session_ids: list[str]) -> dict[str, bool]:
    """Which of these run sessions currently hold the per-session turn lock.

    The lock is keyed `agent-turn:{session_id}` in Redis and set by
    sprite_agent_service._TurnLock for the whole duration of a turn.
    Checking each key individually keeps the lock semantics the source of
    truth (a sessions.status column would have to mirror it and could drift).
    """
    if not session_ids:
        return {}
    active = {}
    for session_id in session_ids:
        if await sprite_agent_service.turn_running(session_id):
            active[session_id] = True
    return active


def _derive_status(final_text: str | None, is_running: bool | None) -> tuple[str, str | None]:
    """Map a run's terminal assistant_message + live lock to a UI status.

    A terminal event is the source of truth that a run has ended: it is written
    inside the turn lock, and the lock is only released after the block exits,
    so checking the terminal event before the lock avoids a brief window where
    a just-finished run would still read as running. A run with neither a
    terminal event nor a live turn ended without recording one (worker kill,
    sprite crash mid-run) — 'interrupted', not 'completed', so a user can tell
    a real empty answer apart from a run that never finished.
    """
    if final_text is not None:
        if final_text.startswith(_FAILURE_PREFIX):
            return STATUS_FAILED, final_text[len(_FAILURE_PREFIX) :].strip() or None
        if final_text == _STOPPED_NOTE:
            return STATUS_STOPPED, None
        return STATUS_COMPLETED, None
    if is_running:
        return STATUS_RUNNING, None
    return STATUS_INTERRUPTED, None


def _run_app_url(session_id: str) -> str:
    return f"{settings.PUBLIC_URL.rstrip('/')}/sessions/{session_id}"
