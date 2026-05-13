"""Session-share + session-artifact helpers.

The legacy name `stash_service` survives because the `/api/v1/stashes/*`
workspace-alias routes still reference it (and the codebase calls
workspaces "stashes" in the product). But the data this service touches
moved: `stashes` table → `sessions` + `share_links`; `stash_artifacts`
table → `session_artifacts`.

This module is the thin compatibility layer that the share_session
endpoint family (`/b/{slug}` legacy URL, the share_session router)
needs to operate on the new tables while keeping the public API
surface stable for one release.
"""

from __future__ import annotations

import secrets
from uuid import UUID

from ..database import get_pool


def _generate_slug() -> str:
    return f"b-{secrets.token_urlsafe(12)}"


async def create_session_share(
    workspace_id: UUID,
    session_id: str,
    created_by: UUID,
    agent_name: str = "",
    cwd: str | None = None,
    files_touched: list[str] | None = None,
) -> dict:
    """Create (or return) a public share-link targeting an agent session.

    Idempotent: a second call for the same (workspace_id, session_id)
    re-uses the existing slug + share link rather than minting a new one.
    """
    from . import session_service

    pool = get_pool()
    # Ensure the session row exists, with metadata.
    session = await session_service.upsert_session(
        workspace_id,
        session_id,
        agent_name=agent_name,
        cwd=cwd,
        created_by=created_by,
    )
    if files_touched:
        await session_service.set_files_touched(session["id"], files_touched)

    # Is there already a session-share link for this session? Reuse it.
    existing = await pool.fetchrow(
        "SELECT token, slug, target_type, target_id, workspace_id, created_by, created_at "
        "FROM share_links "
        "WHERE target_type = 'session' AND target_id = $1 AND revoked_at IS NULL "
        "ORDER BY created_at LIMIT 1",
        session["id"],
    )
    if existing:
        return _share_to_session_dict(dict(existing), session)

    slug = _generate_slug()
    token = secrets.token_urlsafe(16)
    row = await pool.fetchrow(
        "INSERT INTO share_links "
        "(token, workspace_id, created_by, permission, target_type, target_id, slug) "
        "VALUES ($1, $2, $3, 'view', 'session', $4, $5) "
        "RETURNING token, slug, target_type, target_id, workspace_id, created_by, created_at",
        token,
        workspace_id,
        created_by,
        session["id"],
        slug,
    )
    return _share_to_session_dict(dict(row), session)


def _share_to_session_dict(share: dict, session: dict) -> dict:
    """Stitch the share-link row + session row into one dict shaped like
    the legacy `stashes` row that some callers still expect.

    `artifact_count` defaults to 0; callers that care set it explicitly
    after computing it via a separate query."""
    return {
        "id": share["target_id"],
        "workspace_id": share["workspace_id"],
        "session_id": session["session_id"],
        "slug": share["slug"],
        "agent_name": session.get("agent_name") or "",
        "cwd": session.get("cwd"),
        "summary_status": session.get("summary_status"),
        "summary": session.get("summary"),
        "files_touched": session.get("files_touched") or [],
        "created_by": share["created_by"],
        "created_at": share["created_at"],
        "updated_at": share["created_at"],
        "has_transcript": True,
        "artifact_count": 0,
    }


async def get_session_share_by_slug(slug: str) -> dict | None:
    """Returns the legacy stash-shaped dict for a public slug, or None."""
    from . import session_service

    pool = get_pool()
    share = await pool.fetchrow(
        "SELECT token, slug, target_type, target_id, workspace_id, created_by, created_at "
        "FROM share_links "
        "WHERE slug = $1 AND target_type = 'session' AND revoked_at IS NULL",
        slug,
    )
    if not share:
        return None
    session = await session_service.get_session_by_id(share["target_id"])
    if not session:
        return None
    out = _share_to_session_dict(dict(share), session)
    artifacts = await pool.fetchval(
        "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
        session["id"],
    )
    out["artifact_count"] = int(artifacts or 0)
    return out


async def get_session_share_by_id(target_id: UUID) -> dict | None:
    """`target_id` is the sessions.id UUID."""
    from . import session_service

    pool = get_pool()
    session = await session_service.get_session_by_id(target_id)
    if not session:
        return None
    share = await pool.fetchrow(
        "SELECT token, slug, target_type, target_id, workspace_id, created_by, created_at "
        "FROM share_links "
        "WHERE target_type = 'session' AND target_id = $1 AND revoked_at IS NULL "
        "ORDER BY created_at LIMIT 1",
        target_id,
    )
    if not share:
        return None
    out = _share_to_session_dict(dict(share), session)
    artifacts = await pool.fetchval(
        "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
        target_id,
    )
    out["artifact_count"] = int(artifacts or 0)
    return out


# Backward-compat aliases for legacy callers.
get_stash_by_slug = get_session_share_by_slug
get_stash_by_id = get_session_share_by_id
create_stash = create_session_share


async def update_session_share(
    session_row_id: UUID,
    *,
    summary: str | None = None,
) -> dict | None:
    """The only field a session-share's PATCH currently exposes is the
    summary. The summarizer worker owns summary_status; clients no longer
    drive it directly."""
    from . import session_service

    if summary is not None:
        await session_service.set_summary(session_row_id, summary)
    return await get_session_share_by_id(session_row_id)


update_stash = update_session_share


async def add_artifact(
    session_id: UUID,
    file_path: str,
    storage_key: str,
    size_bytes: int,
) -> dict:
    """Insert a session_artifact row. `session_id` here is `sessions.id` UUID."""
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, file_path, size_bytes, created_at",
        session_id,
        file_path,
        storage_key,
        size_bytes,
    )
    return dict(row)


async def list_artifacts(session_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, file_path, storage_key, size_bytes, created_at "
        "FROM session_artifacts WHERE session_id = $1 ORDER BY file_path",
        session_id,
    )
    return [dict(r) for r in rows]


async def get_artifact(artifact_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT sa.id, sa.session_id, sa.file_path, sa.storage_key, sa.size_bytes, sa.created_at, "
        "sl.slug AS stash_slug "
        "FROM session_artifacts sa "
        "LEFT JOIN share_links sl "
        "  ON sl.target_type = 'session' AND sl.target_id = sa.session_id "
        "WHERE sa.id = $1",
        artifact_id,
    )
    return dict(row) if row else None
