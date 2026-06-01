"""Sources: the unified source layer.

A *source* is anything the agent can read. Two are native and always present
per workspace — the **file system** and **session transcripts** (workspace-scoped,
visible to all members). The rest are **connected sources** (GitHub / Drive /
Notion / Slack / Granola) — rows in `workspace_sources`, USER-SCOPED so only the
owner sees them.

This module owns:
- the `workspace_sources` registry (CRUD + sync bookkeeping),
- the `source_documents` index store (idempotent upsert, soft-delete, navigate,
  search) where connected-source content lives, separate from pages/files.

Native adapters (files, sessions) live in the source tools in agent_runtime and
delegate to files_tree_service / memory_service; this module is the connected-
source half plus `list_sources`, which composes both.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from ..database import get_pool

# Native source handles. Connected sources use their workspace_sources.id (str).
NATIVE_FILES = "files"
NATIVE_SESSIONS = "sessions"

# Default sync cadence per source type (seconds). Push sources (slack/granola)
# get their freshness from webhooks; the interval is just the safety re-backfill.
DEFAULT_SYNC_INTERVAL_S = {
    "github_repo": 3600,
    "google_drive": 1800,
    "notion": 1800,
    "slack": 21600,
    "granola": 21600,
}

# Which capability each connected source type exposes.
SOURCE_CAPABILITY = {
    "github_repo": "navigable",
    "google_drive": "navigable",
    "notion": "navigable",
    "slack": "searchable",
    "granola": "searchable",
}


def _content_hash(content: str | None) -> str:
    return hashlib.sha256((content or "").encode()).hexdigest()


def _source_row(row) -> dict:
    return {
        "id": str(row["id"]),
        "workspace_id": str(row["workspace_id"]),
        "owner_user_id": str(row["owner_user_id"]),
        "source_type": row["source_type"],
        "external_ref": row["external_ref"],
        "display_name": row["display_name"],
        "capability": row["capability"],
        "sync_enabled": row["sync_enabled"],
        "sync_status": row["sync_status"],
        "sync_error": row["sync_error"],
        "last_synced_at": row["last_synced_at"].isoformat() if row["last_synced_at"] else None,
    }


# --- workspace_sources registry --------------------------------------------


async def create_source(
    *,
    workspace_id: UUID,
    owner_user_id: UUID,
    source_type: str,
    external_ref: str,
    display_name: str,
) -> dict:
    """Register a connected source (idempotent on the natural key). The first
    sync runs immediately because `next_sync_at` defaults to now()."""
    capability = SOURCE_CAPABILITY.get(source_type, "navigable")
    interval = DEFAULT_SYNC_INTERVAL_S.get(source_type, 3600)
    row = await get_pool().fetchrow(
        """
        INSERT INTO workspace_sources (
            workspace_id, owner_user_id, source_type, external_ref,
            display_name, capability, sync_interval_s
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (workspace_id, owner_user_id, source_type, external_ref)
        DO UPDATE SET display_name = EXCLUDED.display_name, updated_at = now()
        RETURNING *
        """,
        workspace_id,
        owner_user_id,
        source_type,
        external_ref,
        display_name,
        capability,
        interval,
    )
    return _source_row(row)


async def list_connected_sources(workspace_id: UUID, user_id: UUID) -> list[dict]:
    """The user's own connected sources in this workspace. User-scoped: a
    member never sees another member's connected sources."""
    rows = await get_pool().fetch(
        "SELECT * FROM workspace_sources "
        "WHERE workspace_id = $1 AND owner_user_id = $2 "
        "ORDER BY source_type, display_name",
        workspace_id,
        user_id,
    )
    return [_source_row(r) for r in rows]


async def get_owned_source(source_id: UUID, user_id: UUID) -> dict | None:
    """Fetch a connected source only if `user_id` owns it — the single
    enforcement point for user-scoping on every read."""
    row = await get_pool().fetchrow(
        "SELECT * FROM workspace_sources WHERE id = $1 AND owner_user_id = $2",
        source_id,
        user_id,
    )
    return _source_row(row) if row else None


async def delete_source(source_id: UUID, user_id: UUID) -> bool:
    """Remove a connected source the user owns. `source_documents` cascade."""
    result = await get_pool().execute(
        "DELETE FROM workspace_sources WHERE id = $1 AND owner_user_id = $2",
        source_id,
        user_id,
    )
    return result.endswith("1")


async def get_source_for_sync(source_id: UUID) -> dict | None:
    """Everything a sync task needs to crawl one source. Not owner-gated —
    sync runs server-side on behalf of the owner via their stored token."""
    row = await get_pool().fetchrow(
        "SELECT id, workspace_id, owner_user_id, source_type, external_ref, sync_cursor "
        "FROM workspace_sources WHERE id = $1",
        source_id,
    )
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "workspace_id": str(row["workspace_id"]),
        "owner_user_id": str(row["owner_user_id"]),
        "source_type": row["source_type"],
        "external_ref": row["external_ref"],
        "sync_cursor": row["sync_cursor"],
    }


async def due_sources(limit: int = 50) -> list[dict]:
    """Pull sources whose scheduled sync is due (for the Beat reconciler)."""
    rows = await get_pool().fetch(
        "SELECT id, workspace_id, owner_user_id, source_type, external_ref, sync_cursor "
        "FROM workspace_sources "
        "WHERE sync_enabled AND next_sync_at <= now() "
        "ORDER BY next_sync_at LIMIT $1",
        limit,
    )
    return [
        {
            "id": str(r["id"]),
            "workspace_id": str(r["workspace_id"]),
            "owner_user_id": str(r["owner_user_id"]),
            "source_type": r["source_type"],
            "external_ref": r["external_ref"],
            "sync_cursor": r["sync_cursor"],
        }
        for r in rows
    ]


async def mark_sync_started(source_id: UUID) -> None:
    await get_pool().execute(
        "UPDATE workspace_sources SET sync_status = 'syncing', sync_error = NULL, "
        "next_sync_at = now() + (sync_interval_s || ' seconds')::interval, updated_at = now() "
        "WHERE id = $1",
        source_id,
    )


async def mark_sync_done(source_id: UUID, cursor: str | None) -> None:
    await get_pool().execute(
        "UPDATE workspace_sources SET sync_status = 'idle', sync_cursor = COALESCE($2, sync_cursor), "
        "last_synced_at = now(), updated_at = now() WHERE id = $1",
        source_id,
        cursor,
    )


async def mark_sync_failed(source_id: UUID, error: str) -> None:
    await get_pool().execute(
        "UPDATE workspace_sources SET sync_status = 'failed', sync_error = $2, updated_at = now() "
        "WHERE id = $1",
        source_id,
        error[:500],
    )


# --- source_documents index store ------------------------------------------


async def upsert_document(
    *,
    source_id: UUID,
    workspace_id: UUID,
    path: str,
    name: str,
    kind: str = "file",
    content: str | None = None,
    blob_storage_key: str | None = None,
    external_ref: str | None = None,
    external_updated_at=None,
) -> str:
    """Idempotent upsert keyed by (source_id, path). Returns 'unchanged',
    'inserted', or 'updated'. Flips `embed_stale` only when content changes so
    the embedding reconciler re-embeds exactly what moved."""
    pool = get_pool()
    new_hash = _content_hash(content)
    existing = await pool.fetchrow(
        "SELECT content_hash, deleted_at FROM source_documents "
        "WHERE source_id = $1 AND path = $2",
        source_id,
        path,
    )
    if existing and existing["content_hash"] == new_hash and existing["deleted_at"] is None:
        return "unchanged"

    await pool.execute(
        """
        INSERT INTO source_documents (
            source_id, workspace_id, path, name, kind, content, content_hash,
            blob_storage_key, external_ref, external_updated_at, embed_stale
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, TRUE)
        ON CONFLICT (source_id, path) DO UPDATE SET
            name = EXCLUDED.name,
            kind = EXCLUDED.kind,
            content = EXCLUDED.content,
            content_hash = EXCLUDED.content_hash,
            blob_storage_key = EXCLUDED.blob_storage_key,
            external_ref = EXCLUDED.external_ref,
            external_updated_at = EXCLUDED.external_updated_at,
            embed_stale = TRUE,
            deleted_at = NULL,
            updated_at = now()
        """,
        source_id,
        workspace_id,
        path,
        name,
        kind,
        content,
        new_hash,
        blob_storage_key,
        external_ref,
        external_updated_at,
    )
    return "inserted" if existing is None else "updated"


async def soft_delete_missing(source_id: UUID, present_paths: list[str]) -> int:
    """Soft-delete live docs whose path wasn't in the latest crawl — the tail
    of an idempotent re-sync. Returns the number removed."""
    result = await get_pool().execute(
        "UPDATE source_documents SET deleted_at = now() "
        "WHERE source_id = $1 AND deleted_at IS NULL AND path <> ALL($2::text[])",
        source_id,
        present_paths,
    )
    return int(result.split()[-1]) if result.startswith("UPDATE") else 0


async def list_documents(source_id: UUID, prefix: str = "", limit: int = 200) -> list[dict]:
    """List a source's live documents, optionally under a path prefix."""
    rows = await get_pool().fetch(
        "SELECT path, name, kind FROM source_documents "
        "WHERE source_id = $1 AND deleted_at IS NULL AND path LIKE $2 "
        "ORDER BY path LIMIT $3",
        source_id,
        f"{prefix}%",
        limit,
    )
    return [{"path": r["path"], "name": r["name"], "kind": r["kind"]} for r in rows]


async def read_document(source_id: UUID, path: str) -> dict | None:
    row = await get_pool().fetchrow(
        "SELECT path, name, kind, content, blob_storage_key FROM source_documents "
        "WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL",
        source_id,
        path,
    )
    if not row:
        return None
    return {
        "path": row["path"],
        "name": row["name"],
        "kind": row["kind"],
        "content": row["content"] or "",
        "has_blob": row["blob_storage_key"] is not None,
    }


async def search_documents(
    *,
    workspace_id: UUID,
    user_id: UUID,
    query: str,
    source_id: UUID | None = None,
    limit: int = 20,
) -> list[dict]:
    """FTS over the user's own connected-source documents. The owner join is
    the user-scoping guard — never returns another member's source content."""
    limit = min(limit, 100)
    rows = await get_pool().fetch(
        "SELECT d.source_id, s.display_name AS source_name, d.path, d.name, "
        "       LEFT(d.content, 400) AS snippet, "
        "       ts_rank(to_tsvector('english', coalesce(d.content, '')), "
        "               websearch_to_tsquery('english', $3)) AS rank "
        "FROM source_documents d "
        "JOIN workspace_sources s ON s.id = d.source_id "
        "WHERE d.workspace_id = $1 AND s.owner_user_id = $2 AND d.deleted_at IS NULL "
        "  AND ($4::uuid IS NULL OR d.source_id = $4) "
        "  AND to_tsvector('english', coalesce(d.content, '')) "
        "      @@ websearch_to_tsquery('english', $3) "
        "ORDER BY rank DESC LIMIT $5",
        workspace_id,
        user_id,
        query,
        source_id,
        limit,
    )
    return [
        {
            "source_id": str(r["source_id"]),
            "source_name": r["source_name"],
            "path": r["path"],
            "name": r["name"],
            "snippet": r["snippet"] or "",
        }
        for r in rows
    ]


# --- list_sources: native + connected --------------------------------------


async def list_sources(workspace_id: UUID, user_id: UUID) -> list[dict]:
    """Every source visible to this user: the two native sources (workspace-
    scoped) plus the user's own connected sources."""
    sources = [
        {
            "source": NATIVE_FILES,
            "type": "native_files",
            "capability": "navigable",
            "display_name": "Files",
        },
        {
            "source": NATIVE_SESSIONS,
            "type": "native_sessions",
            "capability": "searchable",
            "display_name": "Session transcripts",
        },
    ]
    for s in await list_connected_sources(workspace_id, user_id):
        sources.append(
            {
                "source": s["id"],
                "type": s["source_type"],
                "capability": s["capability"],
                "display_name": s["display_name"],
            }
        )
    return sources
