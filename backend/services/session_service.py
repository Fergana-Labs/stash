"""Sessions: lightweight metadata table for an agent's coding session.

Replaces the session-bundle bits that used to live on the `stashes`
table (which was overloaded with the workspace "stash" naming).

`summary_status` (need_summary | in_progress | failed | done) is purely
about the summarizer worker's progress on this session.
"""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool

_SELECT_COLS = (
    "id, workspace_id, session_id, agent_name, cwd, summary, summary_status, "
    "files_touched, started_at, finished_at, created_by"
)


async def upsert_session(
    workspace_id: UUID,
    session_id: str,
    *,
    agent_name: str = "",
    cwd: str | None = None,
    created_by: UUID | None = None,
) -> dict:
    """Idempotent: return the session row, creating it if missing.

    The CLI calls this lazily — first event for a session writes the row.
    New rows land in summary_status='need_summary' by default, eligible
    for the summarizer worker on its next tick.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, cwd, created_by) "
        "VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (workspace_id, session_id) DO UPDATE SET "
        "  agent_name = COALESCE(NULLIF(EXCLUDED.agent_name, ''), sessions.agent_name), "
        "  cwd = COALESCE(EXCLUDED.cwd, sessions.cwd) "
        f"RETURNING {_SELECT_COLS}",
        workspace_id,
        session_id,
        agent_name,
        cwd,
        created_by,
    )
    return dict(row)


async def get_session(workspace_id: UUID, session_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_SELECT_COLS} " "FROM sessions WHERE workspace_id = $1 AND session_id = $2",
        workspace_id,
        session_id,
    )
    return dict(row) if row else None


async def get_session_by_id(session_row_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_SELECT_COLS} FROM sessions WHERE id = $1",
        session_row_id,
    )
    return dict(row) if row else None


async def set_summary(session_row_id: UUID, summary: str) -> None:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE sessions SET summary = $1, summary_status = 'done', "
        "finished_at = COALESCE(finished_at, now()) "
        "WHERE id = $2 RETURNING workspace_id",
        summary,
        session_row_id,
    )
    if row:
        from . import handoff_writer

        handoff_writer.mark_stale_bg(row["workspace_id"])


async def set_files_touched(session_row_id: UUID, files: list[str]) -> None:
    import json

    pool = get_pool()
    await pool.execute(
        "UPDATE sessions SET files_touched = $1::jsonb WHERE id = $2",
        json.dumps(files),
        session_row_id,
    )
