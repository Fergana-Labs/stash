"""Sessions: lightweight metadata table for an agent's coding session."""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool

_SELECT_COLS = (
    "id, workspace_id, session_id, agent_name, cwd, files_touched, "
    "started_at, finished_at, created_by"
)


async def upsert_session(
    workspace_id: UUID,
    session_id: str,
    *,
    agent_name: str = "",
    cwd: str | None = None,
    created_by: UUID | None = None,
    session_folder_id: UUID | None = None,
) -> dict:
    """Idempotent: return the session row, creating it if missing.

    The CLI calls this lazily — first event for a session writes the row. The
    folder is set once and never re-homed by a later upsert, so a manual move
    sticks even if the agent keeps streaming.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, cwd, created_by, session_folder_id) "
        "VALUES ($1, $2, $3, $4, $5, $6) "
        "ON CONFLICT (workspace_id, session_id) DO UPDATE SET "
        "  agent_name = COALESCE(NULLIF(EXCLUDED.agent_name, ''), sessions.agent_name), "
        "  cwd = COALESCE(EXCLUDED.cwd, sessions.cwd), "
        "  created_by = COALESCE(sessions.created_by, EXCLUDED.created_by), "
        "  session_folder_id = COALESCE(sessions.session_folder_id, EXCLUDED.session_folder_id) "
        f"RETURNING {_SELECT_COLS}",
        workspace_id,
        session_id,
        agent_name,
        cwd,
        created_by,
        session_folder_id,
    )
    return dict(row)


async def get_session(workspace_id: UUID, session_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_SELECT_COLS} FROM sessions "
        "WHERE workspace_id = $1 AND session_id = $2 AND deleted_at IS NULL",
        workspace_id,
        session_id,
    )
    return dict(row) if row else None


async def get_session_by_id(session_row_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_SELECT_COLS} FROM sessions WHERE id = $1 AND deleted_at IS NULL",
        session_row_id,
    )
    return dict(row) if row else None


async def set_files_touched(session_row_id: UUID, files: list[str]) -> None:
    import json

    pool = get_pool()
    await pool.execute(
        "UPDATE sessions SET files_touched = $1::jsonb WHERE id = $2",
        json.dumps(files),
        session_row_id,
    )


async def delete_session(session_row_id: UUID, workspace_id: UUID, deleted_by: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE sessions SET deleted_at = NOW(), deleted_by = $3 "
        "WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL",
        session_row_id,
        workspace_id,
        deleted_by,
    )
    return result == "UPDATE 1"


async def restore_session(session_row_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE sessions SET deleted_at = NULL, deleted_by = NULL "
        "WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NOT NULL",
        session_row_id,
        workspace_id,
    )
    return result == "UPDATE 1"


async def purge_session(session_row_id: UUID, workspace_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM sessions WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NOT NULL",
        session_row_id,
        workspace_id,
    )
    return result == "DELETE 1"


async def list_trashed_session_artifact_storage_keys(
    session_row_id: UUID,
    workspace_id: UUID,
) -> list[str]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT sa.storage_key "
        "FROM session_artifacts sa "
        "JOIN sessions s ON s.id = sa.session_id "
        "WHERE s.id = $1 AND s.workspace_id = $2 AND s.deleted_at IS NOT NULL "
        "ORDER BY sa.created_at, sa.id",
        session_row_id,
        workspace_id,
    )
    return [row["storage_key"] for row in rows]


async def list_trashed_sessions(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, session_id, agent_name, started_at, "
        "finished_at, deleted_at, deleted_by "
        "FROM sessions WHERE workspace_id = $1 AND deleted_at IS NOT NULL "
        "ORDER BY deleted_at DESC",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def get_trashed_session(session_row_id: UUID, workspace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_SELECT_COLS} FROM sessions "
        "WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NOT NULL",
        session_row_id,
        workspace_id,
    )
    return dict(row) if row else None
