"""Sessions: lightweight metadata table for an agent's coding session."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ..database import get_pool
from . import security_audit_service

_SELECT_COLS = (
    "id, owner_user_id, session_id, agent_name, cwd, files_touched, "
    "started_at, finished_at, created_by, end_user_id, last_event_at"
)


async def upsert_session(
    owner_user_id: UUID,
    session_id: str,
    *,
    agent_name: str = "",
    cwd: str | None = None,
    created_by: UUID | None = None,
    end_user_id: UUID | None = None,
    session_folder_id: UUID | None = None,
    started_at: datetime | None = None,
    last_event_at: datetime | None = None,
) -> dict:
    """Idempotent: return the session row, creating it if missing.

    The CLI calls this lazily — first event for a session writes the row.

    `started_at` is when the session actually began. Only a transcript upload
    knows it, because the transcript carries the original event times and a
    history import can replay a conversation from months ago. Live callers
    create the row as the session starts, so insert time is the start and they
    pass nothing. It is set at insert only: a later event stream must never
    restamp an imported session to now().

    `end_user_id` (External Multiplayer) is set at insert only: the end user a session
    was born into is its privacy boundary and never changes.

    `session_folder_id` is the LEGACY filing lane, kept for installed clients
    (Heavi's backend foremost). Set at insert only, honored only when sent —
    nothing on the platform reads it, and no default folder is resolved.

    `last_event_at` is the recency the sessions list orders by. Event pushes
    pass their newest event time; it only ever moves forward (GREATEST), so a
    replayed old transcript never rewinds a session's recency.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO sessions "
        "  (owner_user_id, session_id, agent_name, cwd, created_by, end_user_id, "
        "   session_folder_id, started_at, last_event_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, COALESCE($8, now()), "
        "        COALESCE($9, $8, now())) "
        "ON CONFLICT (owner_user_id, session_id) DO UPDATE SET "
        "  agent_name = COALESCE(NULLIF(EXCLUDED.agent_name, ''), sessions.agent_name), "
        "  cwd = COALESCE(EXCLUDED.cwd, sessions.cwd), "
        "  created_by = COALESCE(sessions.created_by, EXCLUDED.created_by), "
        "  last_event_at = GREATEST(sessions.last_event_at, "
        "                           COALESCE($9, sessions.last_event_at)) "
        f"RETURNING {_SELECT_COLS}",
        owner_user_id,
        session_id,
        agent_name,
        cwd,
        created_by,
        end_user_id,
        session_folder_id,
        started_at,
        last_event_at,
    )
    return dict(row)


async def get_session(owner_user_id: UUID, session_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_SELECT_COLS} FROM sessions "
        "WHERE owner_user_id = $1 AND session_id = $2 AND deleted_at IS NULL",
        owner_user_id,
        session_id,
    )
    return dict(row) if row else None


async def list_sessions_for_session_id(session_id: str) -> list[dict]:
    """All scope rows for an external session id, newest first.

    session_id is only unique per scope — the same session can exist in
    several scopes (re-import, repo reconnected elsewhere). Callers pick
    the first row the user is allowed to read.
    """
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT {_SELECT_COLS} FROM sessions "
        "WHERE session_id = $1 AND deleted_at IS NULL ORDER BY started_at DESC",
        session_id,
    )
    return [dict(row) for row in rows]


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


async def delete_session(session_row_id: UUID, owner_user_id: UUID, deleted_by: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE sessions SET deleted_at = NOW(), deleted_by = $3 "
        "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
        session_row_id,
        owner_user_id,
        deleted_by,
    )
    if result != "UPDATE 1":
        return False
    # Audited here so every front door (REST, batch, agent tools) leaves a trail.
    await security_audit_service.record_content_lifecycle_event(
        operation="deleted",
        actor_user_id=deleted_by,
        owner_user_id=owner_user_id,
        target_type="session",
        target_id=session_row_id,
    )
    return True


async def restore_session(session_row_id: UUID, owner_user_id: UUID, restored_by: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE sessions SET deleted_at = NULL, deleted_by = NULL "
        "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NOT NULL",
        session_row_id,
        owner_user_id,
    )
    if result != "UPDATE 1":
        return False
    await security_audit_service.record_content_lifecycle_event(
        operation="restored",
        actor_user_id=restored_by,
        owner_user_id=owner_user_id,
        target_type="session",
        target_id=session_row_id,
    )
    return True


async def purge_session(session_row_id: UUID, owner_user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM sessions WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NOT NULL",
        session_row_id,
        owner_user_id,
    )
    return result == "DELETE 1"


async def list_trashed_session_artifact_storage_keys(
    session_row_id: UUID,
    owner_user_id: UUID,
) -> list[str]:
    pool = get_pool()
    # Forks copy storage_key by reference (shared_skill_service._fork_session), so
    # one S3 object can back artifacts in other sessions or files. Only return
    # keys nothing else points at; deleting a shared key would 502 those reads.
    rows = await pool.fetch(
        "SELECT sa.storage_key "
        "FROM session_artifacts sa "
        "JOIN sessions s ON s.id = sa.session_id "
        "WHERE s.id = $1 AND s.owner_user_id = $2 AND s.deleted_at IS NOT NULL "
        "AND NOT EXISTS ("
        "    SELECT 1 FROM files f WHERE f.storage_key = sa.storage_key"
        ") "
        "AND NOT EXISTS ("
        "    SELECT 1 FROM session_artifacts sa2 "
        "    WHERE sa2.storage_key = sa.storage_key AND sa2.session_id <> $1"
        ") "
        "ORDER BY sa.created_at, sa.id",
        session_row_id,
        owner_user_id,
    )
    return [row["storage_key"] for row in rows]


async def list_trashed_sessions(owner_user_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, owner_user_id, session_id, agent_name, started_at, "
        "finished_at, deleted_at, deleted_by "
        "FROM sessions WHERE owner_user_id = $1 AND deleted_at IS NOT NULL "
        "ORDER BY deleted_at DESC",
        owner_user_id,
    )
    return [dict(r) for r in rows]


async def get_trashed_session(session_row_id: UUID, owner_user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_SELECT_COLS} FROM sessions "
        "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NOT NULL",
        session_row_id,
        owner_user_id,
    )
    return dict(row) if row else None
