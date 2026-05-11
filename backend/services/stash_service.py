"""Stashes: shareable archive of a coding session."""

from __future__ import annotations

import secrets
from uuid import UUID

from ..database import get_pool


def _generate_slug() -> str:
    return f"b-{secrets.token_urlsafe(12)}"


async def create_stash(
    workspace_id: UUID,
    session_id: str,
    created_by: UUID,
    agent_name: str = "",
    cwd: str | None = None,
    files_touched: list[str] | None = None,
) -> dict:
    pool = get_pool()
    slug = _generate_slug()
    row = await pool.fetchrow(
        "INSERT INTO stashes "
        "(workspace_id, session_id, slug, agent_name, cwd, files_touched, created_by) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7) "
        "RETURNING id, workspace_id, session_id, slug, agent_name, cwd, status, "
        "summary, files_touched, created_by, created_at, updated_at",
        workspace_id,
        session_id,
        slug,
        agent_name,
        cwd,
        files_touched or [],
        created_by,
    )
    return dict(row)


async def get_stash_by_slug(slug: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT s.id, s.workspace_id, s.session_id, s.slug, s.agent_name, s.cwd, "
        "s.status, s.summary, s.files_touched, s.transcript_storage_key, "
        "s.created_by, s.created_at, s.updated_at, "
        "(SELECT COUNT(*) FROM stash_artifacts sa WHERE sa.stash_id = s.id) AS artifact_count "
        "FROM stashes s WHERE s.slug = $1",
        slug,
    )
    if not row:
        return None
    d = dict(row)
    d["has_transcript"] = bool(d.pop("transcript_storage_key", None))
    return d


async def get_stash_by_id(stash_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT s.id, s.workspace_id, s.session_id, s.slug, s.agent_name, s.cwd, "
        "s.status, s.summary, s.files_touched, s.transcript_storage_key, "
        "s.created_by, s.created_at, s.updated_at, "
        "(SELECT COUNT(*) FROM stash_artifacts sa WHERE sa.stash_id = s.id) AS artifact_count "
        "FROM stashes s WHERE s.id = $1",
        stash_id,
    )
    if not row:
        return None
    d = dict(row)
    d["has_transcript"] = bool(d.pop("transcript_storage_key", None))
    return d


async def update_stash(stash_id: UUID, **fields) -> dict | None:
    pool = get_pool()
    sets = []
    args = []
    i = 1
    for key in ("summary", "status"):
        if key in fields and fields[key] is not None:
            i += 1
            sets.append(f"{key} = ${i}")
            args.append(fields[key])
    if not sets:
        return await get_stash_by_id(stash_id)
    sets.append("updated_at = now()")
    sql = f"UPDATE stashes SET {', '.join(sets)} WHERE id = $1"
    await pool.execute(sql, stash_id, *args)
    return await get_stash_by_id(stash_id)


async def add_artifact(
    stash_id: UUID,
    file_path: str,
    storage_key: str,
    size_bytes: int,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO stash_artifacts (stash_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, file_path, size_bytes, created_at",
        stash_id,
        file_path,
        storage_key,
        size_bytes,
    )
    return dict(row)


async def list_artifacts(stash_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, file_path, storage_key, size_bytes, created_at "
        "FROM stash_artifacts WHERE stash_id = $1 ORDER BY file_path",
        stash_id,
    )
    return [dict(r) for r in rows]


async def get_artifact(artifact_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT sa.id, sa.stash_id, sa.file_path, sa.storage_key, sa.size_bytes, sa.created_at, "
        "s.slug AS stash_slug "
        "FROM stash_artifacts sa JOIN stashes s ON s.id = sa.stash_id "
        "WHERE sa.id = $1",
        artifact_id,
    )
    return dict(row) if row else None


async def set_transcript_key(stash_id: UUID, storage_key: str) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE stashes SET transcript_storage_key = $2, updated_at = now() WHERE id = $1",
        stash_id,
        storage_key,
    )


async def get_transcript_key(stash_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT transcript_storage_key FROM stashes WHERE id = $1",
        stash_id,
    )
    if not row:
        return None
    return row["transcript_storage_key"]
