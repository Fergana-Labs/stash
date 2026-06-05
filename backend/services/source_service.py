"""Sources: the unified source layer.

A *source* is anything the agent can read. Two are native and always present
per workspace — the **file system** and **session transcripts** (workspace-scoped,
visible to all members). The rest are **connected sources** (GitHub / Drive /
Notion / Slack / Granola) — rows in `workspace_sources`, USER-SCOPED so only the
owner sees them.

This module owns:
- the `workspace_sources` registry (CRUD + sync bookkeeping),
- the per-integration document store. Each source type has its own table
  (migration 0084): most COPY content (FTS + embeddings live in the table —
  github/slack/granola/jira/asana/gong/notion), while drive stores an INDEX ONLY
  and fetches the body lazily from the provider at read time. Every table shares
  the navigation shape (path/name/kind/deleted_at) so the agent's list/read tools
  stay uniform.

This module also owns the unified VFS surface (`source_entries`, `source_document`,
`search_all`) over BOTH native and connected sources — the single codepath the
agent tools and the REST endpoints both call. Native reads delegate to
files_tree_service / memory_service (imported lazily to avoid an import cycle).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from uuid import UUID

from ..database import get_pool

logger = logging.getLogger(__name__)

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
    "jira_project": 1800,
    "asana_project": 1800,
    "gong_calls": 21600,
}

# Which capability each connected source type exposes.
SOURCE_CAPABILITY = {
    "github_repo": "navigable",
    "google_drive": "navigable",
    "notion": "navigable",
    "slack": "searchable",
    "granola": "searchable",
    "jira_project": "searchable",
    "asana_project": "navigable",
    "gong_calls": "searchable",
    # Queryable sources run live read-only SQL; they have no document table or
    # indexer (see source_entries / query_source).
    "snowflake": "queryable",
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
    """Remove a connected source the user owns. Its documents cascade."""
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


# --- per-integration document store -----------------------------------------

# source_type -> the table holding its documents.
SOURCE_TABLE = {
    "github_repo": "github_documents",
    "google_drive": "drive_index",
    "notion": "notion_index",
    "slack": "slack_messages",
    "granola": "granola_notes",
    "jira_project": "jira_documents",
    "asana_project": "asana_documents",
    "gong_calls": "gong_documents",
}

# Tables that COPY content (FTS + embeddings live in them). The rest are
# index-only and fetch their body lazily from the provider at read time.
# Notion copies content too — its crawl already renders each page's text to
# discover sub-pages, so storing it for FTS is nearly free. Jira/Asana/Drive do
# NOT copy: they're index-only and search is federated to the provider's own
# search API (see FEDERATED_SEARCH_TYPES) so we don't duplicate their content.
CONTENT_TABLES = {
    "github_documents",
    "slack_messages",
    "granola_notes",
    "gong_documents",
    "notion_index",
}

# Index-only source types whose `search` is federated live to the provider's
# native search instead of our FTS (no copied content). source_type -> the
# provider search coroutine, resolved lazily to avoid an import cycle.
FEDERATED_SEARCH_TYPES = {"google_drive", "jira_project", "asana_project"}

# Copied-content sources that only cache a bounded recent window. The agent can
# pull OLDER data on demand from the provider for an explicit time range — what
# it fetches is cached (upserted) so it's searchable afterward too.
HISTORY_FETCH_TYPES = {"slack", "gong_calls"}


def _table_for(source_type: str) -> str:
    table = SOURCE_TABLE.get(source_type)
    if table is None:
        raise ValueError(f"no document table for source type {source_type!r}")
    return table


async def upsert_content_document(
    *,
    table: str,
    source_id: UUID,
    workspace_id: UUID,
    path: str,
    name: str,
    kind: str = "file",
    content: str | None = None,
    external_ref: str | None = None,
    external_updated_at=None,
    extra: dict | None = None,
) -> str:
    """Idempotent upsert into a copied-content table (github/slack/granola),
    keyed by (source_id, path). Returns 'unchanged', 'inserted', or 'updated'.
    Flips `embed_stale` only when content changes so the embedding reconciler
    re-embeds exactly what moved. `extra` carries native columns (Slack's
    channel_id/channel_name/ts)."""
    pool = get_pool()
    new_hash = _content_hash(content)
    existing = await pool.fetchrow(
        f"SELECT content_hash, deleted_at FROM {table} WHERE source_id = $1 AND path = $2",
        source_id,
        path,
    )
    if existing and existing["content_hash"] == new_hash and existing["deleted_at"] is None:
        return "unchanged"

    cols = [
        "source_id",
        "workspace_id",
        "path",
        "name",
        "kind",
        "content",
        "content_hash",
        "external_ref",
        "external_updated_at",
        "embed_stale",
    ]
    vals = [
        source_id,
        workspace_id,
        path,
        name,
        kind,
        content,
        new_hash,
        external_ref,
        external_updated_at,
        True,
    ]
    for col, val in (extra or {}).items():
        cols.append(col)
        vals.append(val)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(vals)))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("source_id", "path"))
    await pool.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (source_id, path) DO UPDATE SET {updates}, "
        f"deleted_at = NULL, updated_at = now()",
        *vals,
    )
    return "inserted" if existing is None else "updated"


async def upsert_index_row(
    *,
    table: str,
    source_id: UUID,
    workspace_id: UUID,
    path: str,
    name: str,
    kind: str = "file",
    external_ref: str | None = None,
    external_updated_at=None,
) -> str:
    """Idempotent upsert into an index-only table (drive/notion). Stores just
    the path/name + the provider's external_ref; the body is fetched lazily."""
    pool = get_pool()
    existing = await pool.fetchrow(
        f"SELECT external_ref, external_updated_at, deleted_at FROM {table} "
        f"WHERE source_id = $1 AND path = $2",
        source_id,
        path,
    )
    if (
        existing
        and existing["deleted_at"] is None
        and existing["external_ref"] == external_ref
        and existing["external_updated_at"] == external_updated_at
    ):
        return "unchanged"
    await pool.execute(
        f"INSERT INTO {table} "
        f"(source_id, workspace_id, path, name, kind, external_ref, external_updated_at) "
        f"VALUES ($1, $2, $3, $4, $5, $6, $7) "
        f"ON CONFLICT (source_id, path) DO UPDATE SET "
        f"name = EXCLUDED.name, kind = EXCLUDED.kind, external_ref = EXCLUDED.external_ref, "
        f"external_updated_at = EXCLUDED.external_updated_at, deleted_at = NULL, updated_at = now()",
        source_id,
        workspace_id,
        path,
        name,
        kind,
        external_ref,
        external_updated_at,
    )
    return "inserted" if existing is None else "updated"


async def soft_delete_missing(table: str, source_id: UUID, present_paths: list[str]) -> int:
    """Soft-delete live docs whose path wasn't in the latest crawl — the tail
    of an idempotent re-sync. Returns the number removed."""
    result = await get_pool().execute(
        f"UPDATE {table} SET deleted_at = now() "
        f"WHERE source_id = $1 AND deleted_at IS NULL AND path <> ALL($2::text[])",
        source_id,
        present_paths,
    )
    return int(result.split()[-1]) if result.startswith("UPDATE") else 0


async def list_documents(source: dict, prefix: str = "", limit: int = 200) -> list[dict]:
    """List a source's live documents, optionally under a path prefix. `source`
    is the registry row (from get_owned_source / get_source_for_sync)."""
    table = _table_for(source["source_type"])
    rows = await get_pool().fetch(
        f"SELECT path, name, kind FROM {table} "
        f"WHERE source_id = $1 AND deleted_at IS NULL AND path LIKE $2 "
        f"ORDER BY path LIMIT $3",
        UUID(source["id"]),
        f"{prefix}%",
        limit,
    )
    return [{"path": r["path"], "name": r["name"], "kind": r["kind"]} for r in rows]


async def read_document(source: dict, path: str) -> dict | None:
    """Read one document. Content tables return their stored body; index-only
    tables (drive/notion) fetch it lazily from the provider with the owner's
    token."""
    table = _table_for(source["source_type"])
    if table in CONTENT_TABLES:
        row = await get_pool().fetchrow(
            f"SELECT path, name, kind, content FROM {table} "
            f"WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL",
            UUID(source["id"]),
            path,
        )
        if not row:
            return None
        return {
            "path": row["path"],
            "name": row["name"],
            "kind": row["kind"],
            "content": row["content"] or "",
        }

    row = await get_pool().fetchrow(
        f"SELECT path, name, kind, external_ref FROM {table} "
        f"WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL",
        UUID(source["id"]),
        path,
    )
    if not row:
        return None
    content = await _lazy_fetch(
        source["source_type"], UUID(source["owner_user_id"]), row["external_ref"]
    )
    return {"path": row["path"], "name": row["name"], "kind": row["kind"], "content": content}


async def _lazy_fetch(source_type: str, owner_user_id: UUID, external_ref: str | None) -> str:
    """Fetch an index-only document's body from the provider. Local import keeps
    the integration indexers (which import this module) free of a cycle."""
    if not external_ref:
        return ""
    if source_type == "google_drive":
        from ..integrations.google.indexer import fetch_drive_content

        return await fetch_drive_content(owner_user_id, external_ref)
    if source_type == "jira_project":
        from ..integrations.jira.indexer import fetch_jira_content

        return await fetch_jira_content(owner_user_id, external_ref)
    if source_type == "asana_project":
        from ..integrations.asana.indexer import fetch_asana_content

        return await fetch_asana_content(owner_user_id, external_ref)
    return ""


async def index_paths_for_refs(
    table: str, source_id: UUID, external_refs: list[str]
) -> dict[str, tuple[str, str]]:
    """Map provider external_refs back to (path, name) for a source's live index
    rows. Federated search returns provider ids; this resolves them to the paths
    `read_source` understands (and drops anything not in our index)."""
    if not external_refs:
        return {}
    rows = await get_pool().fetch(
        f"SELECT external_ref, path, name FROM {table} "
        f"WHERE source_id = $1 AND external_ref = ANY($2) AND deleted_at IS NULL",
        source_id,
        external_refs,
    )
    return {r["external_ref"]: (r["path"], r["name"]) for r in rows}


async def _federated_search(source: dict, query: str, limit: int) -> list[dict]:
    """Run a federated source's native provider search. Returns unified hits
    ({source, source_name, ref, name, snippet}); never raises — a provider error
    (e.g. Asana on a free tier) logs and yields no hits so search stays alive."""
    source_type = source["source_type"]
    try:
        if source_type == "google_drive":
            from ..integrations.google.indexer import search_drive as fn
        elif source_type == "jira_project":
            from ..integrations.jira.indexer import search_jira as fn
        elif source_type == "asana_project":
            from ..integrations.asana.indexer import search_asana as fn
        else:
            return []
        hits = await fn(source, query, limit)
    except Exception:
        logger.warning("federated search failed for source %s", source["id"], exc_info=True)
        return []
    return [
        {
            "source": source["id"],
            "source_name": source["display_name"],
            "ref": h["ref"],
            "name": h.get("name", ""),
            "snippet": h.get("snippet", ""),
        }
        for h in hits
    ]


async def search_documents(
    *,
    workspace_id: UUID,
    user_id: UUID,
    query: str,
    source: dict | None = None,
    limit: int = 20,
) -> list[dict]:
    """FTS over the user's own copied-content sources (github/slack/granola),
    UNIONed across their tables. The owner join is the user-scoping guard. Pass
    `source` to scope to one; an index-only source has nothing to FTS, so it
    returns []."""
    limit = min(limit, 100)
    tables = sorted(CONTENT_TABLES)
    source_id: UUID | None = None
    if source is not None:
        table = _table_for(source["source_type"])
        if table not in CONTENT_TABLES:
            return []
        tables = [table]
        source_id = UUID(source["id"])

    parts = [f"""
        SELECT d.source_id, d.path, d.name, LEFT(d.content, 400) AS snippet,
               ts_rank(to_tsvector('english', coalesce(d.content, '')),
                       websearch_to_tsquery('english', $3)) AS rank
        FROM {t} d
        JOIN workspace_sources s ON s.id = d.source_id
        WHERE d.workspace_id = $1 AND s.owner_user_id = $2 AND d.deleted_at IS NULL
          AND ($4::uuid IS NULL OR d.source_id = $4)
          AND to_tsvector('english', coalesce(d.content, ''))
              @@ websearch_to_tsquery('english', $3)
        """ for t in tables]
    union = " UNION ALL ".join(parts)
    rows = await get_pool().fetch(
        f"SELECT u.source_id, ws.display_name AS source_name, u.path, u.name, u.snippet "
        f"FROM ({union}) u JOIN workspace_sources ws ON ws.id = u.source_id "
        f"ORDER BY u.rank DESC LIMIT $5",
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
                # Sync bookkeeping for the per-integration page (the sidebar
                # ignores these). Already on the row — no extra query.
                "external_ref": s["external_ref"],
                "sync_status": s["sync_status"],
                "sync_error": s["sync_error"],
                "last_synced_at": s["last_synced_at"],
            }
        )
    return sources


async def source_item_count(source: dict) -> int | None:
    """How many live documents a source has indexed. None for queryable sources
    (Snowflake) — they have no document table."""
    table = SOURCE_TABLE.get(source["source_type"])
    if table is None:
        return None
    row = await get_pool().fetchrow(
        f"SELECT count(*) AS n FROM {table} WHERE source_id = $1 AND deleted_at IS NULL",
        UUID(source["id"]),
    )
    return int(row["n"]) if row else 0


# --- unified VFS over native + connected sources ----------------------------


async def _resolve_connected(source: str, user_id: UUID) -> dict | None:
    """A non-native handle is a workspace_sources id, resolved only if `user_id`
    owns it. Returns None for unknown / not-owned (callers surface a not-found,
    never another user's source)."""
    try:
        source_id = UUID(source)
    except ValueError:
        return None
    return await get_owned_source(source_id, user_id)


async def source_entries(
    workspace_id: UUID, user_id: UUID, source: str, prefix: str = ""
) -> list[dict] | None:
    """List a source's entries like a file system. `source` is a handle from
    `list_sources` ('files', 'sessions', or a connected-source id); `prefix`
    scopes connected sources to a path. Returns None for an unknown source."""
    if source == NATIVE_FILES:
        from .files_tree_service import list_workspace_pages

        pages = await list_workspace_pages(workspace_id, user_id)
        return [{"id": str(p["id"]), "name": p["name"], "kind": "page"} for p in pages]

    if source == NATIVE_SESSIONS:
        from .memory_service import list_workspace_sessions

        sessions = await list_workspace_sessions(workspace_id, user_id)
        return [
            {"id": s["session_id"], "name": s.get("agent_name") or "session", "kind": "session"}
            for s in sessions
        ]

    connected = await _resolve_connected(source, user_id)
    if connected is None:
        return None
    if connected["capability"] == "queryable":
        # A queryable source (Snowflake) has no document table — list its tables.
        from ..integrations.snowflake.client import list_tables

        return await list_tables(connected)
    return await list_documents(connected, prefix=prefix)


async def source_document(
    workspace_id: UUID, user_id: UUID, source: str, ref: str
) -> tuple[bool, dict | None]:
    """Read one document. `ref` is a page id (files), a session id (sessions),
    or a document path (connected sources). Returns `(source_ok, doc)`:
    `source_ok` is False when the handle is unknown / not owned, and `doc` is
    None when the source is valid but the document is missing — callers keep the
    two not-found cases distinct (an unowned source must never look like a typo)."""
    if source == NATIVE_FILES:
        from .files_tree_service import get_page

        page = await get_page(UUID(ref), workspace_id, user_id)
        if not page:
            return True, None
        return True, {
            "name": page["name"],
            "content": page.get("content_markdown") or page.get("content_html") or "",
        }

    if source == NATIVE_SESSIONS:
        from .memory_service import read_session_events

        events = await read_session_events(workspace_id, ref, user_id)
        transcript = "\n".join(
            f"[{e.get('event_type')}] {(e.get('content') or '')[:2000]}" for e in events
        )
        return True, {"session": ref, "transcript": transcript[:8000]}

    connected = await _resolve_connected(source, user_id)
    if connected is None:
        return False, None
    if connected["capability"] == "queryable":
        # Reading a "document" from a queryable source means describing a table.
        from ..integrations.snowflake.client import describe_table

        return True, await describe_table(connected, ref)
    return True, await read_document(connected, ref)


async def query_source(
    workspace_id: UUID, user_id: UUID, source: str, sql: str, limit: int = 200
) -> dict | None:
    """Run a read-only SQL query against a queryable source (Snowflake). Returns
    None when the handle is unknown / not owned, or an error dict when the source
    isn't queryable or the SQL is rejected."""
    connected = await _resolve_connected(source, user_id)
    if connected is None:
        return None
    if connected["capability"] != "queryable":
        return {"error": "source is not queryable"}
    from ..integrations.snowflake.client import run_query

    try:
        return await run_query(connected, sql, limit)
    except ValueError as e:
        return {"error": str(e)}


def _parse_dt(value: str | None):
    """Parse an ISO-8601 date/datetime (with or without 'Z'). Naive → UTC."""
    from datetime import UTC, datetime

    if not value or not value.strip():
        return None
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def fetch_history(
    workspace_id: UUID,
    user_id: UUID,
    source: str,
    since: str,
    until: str | None = None,
    limit: int = 500,
) -> dict | None:
    """Pull older provider data for a time range, beyond the cached window, for a
    copied source that supports it (Slack/Gong). Fetched items are upserted into
    the local table (so they become searchable) and returned. Returns None when
    the handle is unknown / not owned; an error dict for unsupported sources or
    bad input."""
    connected = await _resolve_connected(source, user_id)
    if connected is None:
        return None
    if connected["source_type"] not in HISTORY_FETCH_TYPES:
        return {"error": "source does not support history fetch"}
    try:
        since_dt = _parse_dt(since)
        until_dt = _parse_dt(until)
    except ValueError:
        return {"error": "since/until must be ISO-8601 dates (e.g. 2026-01-01)"}
    if since_dt is None:
        return {"error": "since is required"}

    if connected["source_type"] == "slack":
        from ..integrations.slack.indexer import fetch_history as fn
    else:
        from ..integrations.gong.indexer import fetch_history as fn
    return await fn(connected, since_dt, until_dt, min(limit, 1000))


async def search_all(
    workspace_id: UUID,
    user_id: UUID,
    query: str,
    source: str | None = None,
    limit: int = 20,
) -> list[dict] | None:
    """Search across sources. Omit `source` to search everything the user can
    see (native files + sessions + their connected sources), or pass a handle to
    scope to one. Returns None when a named source is unknown / not owned."""
    results: list[dict] = []

    if source in (None, NATIVE_SESSIONS):
        from .memory_service import search_workspace_events

        events = await search_workspace_events(workspace_id, user_id, query, limit=limit)
        results += [
            {
                "source": NATIVE_SESSIONS,
                "ref": e.get("session_id"),
                "snippet": (e.get("content") or "")[:300],
            }
            for e in events
        ]

    if source in (None, NATIVE_FILES):
        from .files_tree_service import search_pages_fts

        pages = await search_pages_fts(workspace_id, query, limit=limit, user_id=user_id)
        results += [
            {
                "source": NATIVE_FILES,
                "ref": str(p["id"]),
                "name": p["name"],
                "snippet": (p.get("search_text") or p.get("content_markdown") or "")[:300],
            }
            for p in pages
        ]

    # Connected sources: all of the user's own when unscoped, else the one named.
    connected: dict | None = None
    if source not in (None, NATIVE_FILES, NATIVE_SESSIONS):
        connected = await _resolve_connected(source, user_id)
        if connected is None:
            return None
    if source is None or connected is not None:
        # Copied-content sources go through our FTS (returns [] for index-only /
        # federated sources, which have no stored content to match).
        docs = await search_documents(
            workspace_id=workspace_id,
            user_id=user_id,
            query=query,
            source=connected,
            limit=limit,
        )
        results += [
            {
                "source": d["source_id"],
                "source_name": d["source_name"],
                "ref": d["path"],
                "name": d["name"],
                "snippet": d["snippet"],
            }
            for d in docs
        ]

        # Federated sources search the provider's native API live. Scoped → the
        # one source; unscoped → fan out across the user's federated sources
        # (each call is independent and already swallows its own errors).
        if connected is not None:
            if connected["source_type"] in FEDERATED_SEARCH_TYPES:
                results += await _federated_search(connected, query, limit)
        else:
            federated = [
                s
                for s in await list_connected_sources(workspace_id, user_id)
                if s["source_type"] in FEDERATED_SEARCH_TYPES
            ]
            for hits in await asyncio.gather(
                *(_federated_search(s, query, limit) for s in federated)
            ):
                results += hits

    return results
