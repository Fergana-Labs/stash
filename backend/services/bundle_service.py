"""Session bundles: shareable archive of a coding session."""

from __future__ import annotations

import secrets
from uuid import UUID

from ..database import get_pool


def _generate_slug() -> str:
    return f"b-{secrets.token_urlsafe(12)}"


async def create_bundle(
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
        "INSERT INTO session_bundles "
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


async def get_bundle_by_slug(slug: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT b.id, b.workspace_id, b.session_id, b.slug, b.agent_name, b.cwd, "
        "b.status, b.summary, b.files_touched, b.transcript_storage_key, "
        "b.created_by, b.created_at, b.updated_at, "
        "(SELECT COUNT(*) FROM bundle_artifacts ba WHERE ba.bundle_id = b.id) AS artifact_count "
        "FROM session_bundles b WHERE b.slug = $1",
        slug,
    )
    if not row:
        return None
    d = dict(row)
    d["has_transcript"] = bool(d.pop("transcript_storage_key", None))
    return d


async def get_bundle_by_id(bundle_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT b.id, b.workspace_id, b.session_id, b.slug, b.agent_name, b.cwd, "
        "b.status, b.summary, b.files_touched, b.transcript_storage_key, "
        "b.created_by, b.created_at, b.updated_at, "
        "(SELECT COUNT(*) FROM bundle_artifacts ba WHERE ba.bundle_id = b.id) AS artifact_count "
        "FROM session_bundles b WHERE b.id = $1",
        bundle_id,
    )
    if not row:
        return None
    d = dict(row)
    d["has_transcript"] = bool(d.pop("transcript_storage_key", None))
    return d


async def update_bundle(bundle_id: UUID, **fields) -> dict | None:
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
        return await get_bundle_by_id(bundle_id)
    sets.append("updated_at = now()")
    sql = f"UPDATE session_bundles SET {', '.join(sets)} WHERE id = $1"
    await pool.execute(sql, bundle_id, *args)
    return await get_bundle_by_id(bundle_id)


async def add_artifact(
    bundle_id: UUID, file_path: str, storage_key: str, size_bytes: int,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO bundle_artifacts (bundle_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, file_path, size_bytes, created_at",
        bundle_id, file_path, storage_key, size_bytes,
    )
    return dict(row)


async def list_artifacts(bundle_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, file_path, storage_key, size_bytes, created_at "
        "FROM bundle_artifacts WHERE bundle_id = $1 ORDER BY file_path",
        bundle_id,
    )
    return [dict(r) for r in rows]


async def get_artifact(artifact_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT ba.id, ba.bundle_id, ba.file_path, ba.storage_key, ba.size_bytes, ba.created_at, "
        "sb.slug AS bundle_slug "
        "FROM bundle_artifacts ba JOIN session_bundles sb ON sb.id = ba.bundle_id "
        "WHERE ba.id = $1",
        artifact_id,
    )
    return dict(row) if row else None


async def set_transcript_key(bundle_id: UUID, storage_key: str) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE session_bundles SET transcript_storage_key = $2, updated_at = now() WHERE id = $1",
        bundle_id, storage_key,
    )


async def get_transcript_key(bundle_id: UUID) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT transcript_storage_key FROM session_bundles WHERE id = $1",
        bundle_id,
    )
    if not row:
        return None
    return row["transcript_storage_key"]
