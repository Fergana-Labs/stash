"""Sessions: lightweight metadata table for an agent's coding session."""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool
from . import security_audit_service, session_folder_service

_SELECT_COLS = (
    "id, owner_user_id, session_id, agent_name, cwd, files_touched, "
    "started_at, finished_at, created_by"
)


async def upsert_session(
    owner_user_id: UUID,
    session_id: str,
    *,
    agent_name: str = "",
    cwd: str | None = None,
    created_by: UUID | None = None,
    session_folder_id: UUID | None = None,
) -> dict:
    """Idempotent: return the session row, creating it if missing.

    The CLI calls this lazily — first event for a session writes the row.

    Every session is born into a folder: the one it was pushed to (the repo's
    pinned folder, streamed on every event), or the workspace's Default. We
    resolve the Default only when the row doesn't exist yet. The folder is set
    once at insert and never touched on update, so a manual move — including a
    move to root (session_folder_id = NULL) — sticks even as the agent keeps
    streaming the pin.
    """
    pool = get_pool()
    if session_folder_id is None:
        exists = await pool.fetchval(
            "SELECT 1 FROM sessions WHERE owner_user_id = $1 AND session_id = $2",
            owner_user_id,
            session_id,
        )
        if not exists:
            default_folder = await session_folder_service.ensure_default_folder(owner_user_id)
            session_folder_id = UUID(default_folder["id"])
    row = await pool.fetchrow(
        "INSERT INTO sessions (owner_user_id, session_id, agent_name, cwd, created_by, session_folder_id) "
        "VALUES ($1, $2, $3, $4, $5, $6) "
        "ON CONFLICT (owner_user_id, session_id) DO UPDATE SET "
        "  agent_name = COALESCE(NULLIF(EXCLUDED.agent_name, ''), sessions.agent_name), "
        "  cwd = COALESCE(EXCLUDED.cwd, sessions.cwd), "
        "  created_by = COALESCE(sessions.created_by, EXCLUDED.created_by) "
        f"RETURNING {_SELECT_COLS}",
        owner_user_id,
        session_id,
        agent_name,
        cwd,
        created_by,
        session_folder_id,
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
    """All workspace rows for an external session id, newest first.

    session_id is only unique per workspace — the same session can exist in
    several workspaces (re-import, repo reconnected elsewhere). Callers pick
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
