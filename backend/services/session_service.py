"""Sessions: lightweight metadata table for an agent's coding session.

Replaces the session-bundle bits that used to live on the `stashes`
table (which was overloaded with the workspace "stash" naming).
"""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool


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
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, cwd, created_by) "
        "VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (workspace_id, session_id) DO UPDATE SET "
        "  agent_name = COALESCE(NULLIF(EXCLUDED.agent_name, ''), sessions.agent_name), "
        "  cwd = COALESCE(EXCLUDED.cwd, sessions.cwd) "
        "RETURNING id, workspace_id, session_id, agent_name, cwd, summary, status, "
        "files_touched, started_at, finished_at, created_by",
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
        "SELECT id, workspace_id, session_id, agent_name, cwd, summary, status, "
        "files_touched, started_at, finished_at, created_by "
        "FROM sessions WHERE workspace_id = $1 AND session_id = $2",
        workspace_id,
        session_id,
    )
    return dict(row) if row else None


async def get_session_by_id(session_row_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, session_id, agent_name, cwd, summary, status, "
        "files_touched, started_at, finished_at, created_by "
        "FROM sessions WHERE id = $1",
        session_row_id,
    )
    return dict(row) if row else None


async def set_summary(session_row_id: UUID, summary: str, status: str = "ready") -> None:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE sessions SET summary = $1, status = $2, finished_at = COALESCE(finished_at, now()) "
        "WHERE id = $3 RETURNING workspace_id",
        summary,
        status,
        session_row_id,
    )
    if row:
        import asyncio as _asyncio

        from . import handoff_curator

        _asyncio.create_task(handoff_curator.mark_stale(row["workspace_id"]))


async def set_files_touched(session_row_id: UUID, files: list[str]) -> None:
    import json

    pool = get_pool()
    await pool.execute(
        "UPDATE sessions SET files_touched = $1::jsonb WHERE id = $2",
        json.dumps(files),
        session_row_id,
    )


async def set_status(session_row_id: UUID, status: str) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE sessions SET status = $1 WHERE id = $2",
        status,
        session_row_id,
    )
