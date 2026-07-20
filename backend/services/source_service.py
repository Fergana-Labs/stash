"""Sources: the unified source layer.

A *source* is anything the agent can read. Two are native — the **file system**
and **session transcripts** — readable by the owner and anyone they're shared
with. The rest are **connected sources** (GitHub / Drive / Gmail / Notion /
Slack / Granola) — rows in `user_sources`, owned by the connecting user and
read-shareable: a recipient reads the source's content through Stash using the
OWNER's token (delegated), but never sees the token, and management/sync stay
owner-only.

This module owns:
- the `user_sources` registry (CRUD + sync bookkeeping),
- the per-integration document store. Each source type has its own table
  (migration 0084): some COPY content (FTS + embeddings live in the table —
  github/slack/granola/gong/notion), while drive/gmail/jira/asana store an INDEX
  ONLY and fetch the body lazily from the provider at read time. Every table
  shares the navigation shape (path/name/kind/deleted_at) so the agent's
  list/read tools stay uniform.

This module also owns the unified VFS surface (`source_entries`, `source_document`,
`search_all`) over BOTH native and connected sources — the single codepath the
agent tools and the REST endpoints both call. Native reads delegate to
files_tree_service / memory_service (imported lazily to avoid an import cycle).
Connected-source reads resolve through get_readable_source (owner or a share).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import HTTPException

from ..database import get_pool
from . import permission_service, security_audit_service

logger = logging.getLogger(__name__)


class SourceSyncUserError(Exception):
    """A sync failure the owner can act on. The message is stored verbatim in
    user_sources.sync_error and shown in the UI, so it must never contain
    tokens or provider payloads — raw exceptions stay behind the redacted
    constant (see tasks/sources.py)."""


# A Linear issue identifier (FER-199). Any such ref is readable live from the
# API, so reads work even before a sync has indexed the issue.
LINEAR_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")

# Native source handles. Connected sources use their user_sources.id (str).
NATIVE_FILES = "files"
NATIVE_SESSIONS = "sessions"

# Default sync cadence per source type (seconds). Push sources (slack/granola)
# get their freshness from webhooks; the interval is just the safety re-backfill.
DEFAULT_SYNC_INTERVAL_S = {
    "github_repo": 3600,
    "gmail": 1800,
    "google_drive": 1800,
    "google_drive_folder": 1800,
    "notion": 1800,
    "slack": 21600,
    "granola": 21600,
    "jira_project": 1800,
    "asana_project": 1800,
    "linear": 1800,
    "posthog_project": 1800,
    "gong_calls": 21600,
    # NB: heavi_learnings is intentionally absent — reads are live against the
    # customer endpoint and there is no local index yet (deferred until the
    # unified-search work, PR #860, settles what search wants from sources).
    # Freshness comes from extension pushes (which kick a sync); the interval
    # is the retry pass for failed hydrations.
    "instagram_saves": 1800,
    "x_saves": 1800,
}

# Which capability each connected source type exposes.
SOURCE_CAPABILITY = {
    "github_repo": "navigable",
    "gmail": "searchable",
    "google_drive": "navigable",
    "google_drive_folder": "navigable",
    "notion": "navigable",
    "slack": "searchable",
    "granola": "searchable",
    "jira_project": "searchable",
    "asana_project": "navigable",
    "linear": "navigable",
    "posthog_project": "navigable",
    "gong_calls": "searchable",
    "heavi_learnings": "navigable",
    "instagram_saves": "searchable",
    # Navigable so the browse UI shows the Bookmarks/Posts/Replies/Articles
    # folders; FTS still works (search keys off CONTENT_TABLES, not capability).
    "x_saves": "navigable",
}

PROVIDER_SOURCE_TYPES = {
    "github": ("github_repo",),
    "google": ("google_drive", "google_drive_folder"),
    "gmail": ("gmail",),
    "notion": ("notion",),
    "slack": ("slack",),
    "granola": ("granola",),
    "jira": ("jira_project",),
    "asana": ("asana_project",),
    "linear": ("linear",),
    "posthog": ("posthog_project",),
    "gong": ("gong_calls",),
    "heavi": ("heavi_learnings",),
    # Provider-less groupings: no OAuth integration — the extension pushes the
    # saved-item links and ScrapeCreators hydrates them.
    "instagram": ("instagram_saves",),
    "x": ("x_saves",),
}

SOURCE_TYPE_PROVIDER = {
    source_type: provider
    for provider, source_types in PROVIDER_SOURCE_TYPES.items()
    for source_type in source_types
}

_JIRA_PROJECT_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def parse_jira_project_ref(external_ref: str) -> tuple[str, str]:
    cloud_id, separator, project_key = external_ref.partition(":")
    if not separator or not cloud_id or not project_key:
        raise ValueError("Jira external_ref must be {cloudId}:{projectKey}")
    if ":" in cloud_id or any(ch.isspace() for ch in cloud_id):
        raise ValueError("Jira cloudId cannot contain whitespace or ':'")
    if not _JIRA_PROJECT_KEY_RE.fullmatch(project_key):
        raise ValueError("Jira projectKey must contain only letters, numbers, and underscores")
    return cloud_id, project_key


def validate_source_external_ref(source_type: str, external_ref: str) -> None:
    if source_type == "jira_project":
        parse_jira_project_ref(external_ref)
    # A Linear source always covers every issue the connected user can read, so
    # there is one canonical ref; the router resolves it before we get here.
    if source_type == "linear" and external_ref != "me":
        raise ValueError("Linear external_ref must be 'me'")
    if source_type == "posthog_project" and external_ref != "project":
        raise ValueError("PostHog external_ref must be 'project'")


def _clean_string_list(value, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must be a list of non-empty strings")
        item = item.strip()
        if item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def normalize_source_settings(source_type: str, settings: dict | None) -> dict:
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")

    if source_type == "gong_calls":
        unsupported = set(settings) - {"allowed_workspace_ids"}
        if unsupported:
            raise ValueError(f"unsupported Gong setting: {sorted(unsupported)[0]}")
        return {
            "allowed_workspace_ids": _clean_string_list(
                settings.get("allowed_workspace_ids", []), "allowed_workspace_ids"
            )
        }

    if source_type != "slack":
        if settings:
            raise ValueError("settings are not supported for this source type")
        return {}

    unsupported = set(settings) - {"allowed_channel_ids"}
    if unsupported:
        raise ValueError(f"unsupported Slack setting: {sorted(unsupported)[0]}")

    allowed_channel_ids = _clean_string_list(
        settings.get("allowed_channel_ids", []), "allowed_channel_ids"
    )
    if not allowed_channel_ids:
        raise ValueError("allowed_channel_ids must include at least one Slack channel")

    return {"allowed_channel_ids": allowed_channel_ids}


def slack_allowed_channel_ids(source: dict) -> list[str]:
    settings = source.get("settings")
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    return _clean_string_list(settings.get("allowed_channel_ids", []), "allowed_channel_ids")


def gong_allowed_workspace_ids(source: dict) -> list[str]:
    settings = source.get("settings")
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    return _clean_string_list(settings.get("allowed_workspace_ids", []), "allowed_workspace_ids")


def _content_hash(content: str | None) -> str:
    return hashlib.sha256((content or "").encode()).hexdigest()


def _source_row(row) -> dict:
    return {
        "id": str(row["id"]),
        "owner_user_id": str(row["owner_user_id"]),
        "source_type": row["source_type"],
        "external_ref": row["external_ref"],
        "display_name": row["display_name"],
        "capability": row["capability"],
        "sync_enabled": row["sync_enabled"],
        "sync_status": row["sync_status"],
        "sync_error": row["sync_error"],
        "last_synced_at": row["last_synced_at"].isoformat() if row["last_synced_at"] else None,
        "settings": row["settings"] or {},
    }


def _source_search_hint(source: dict) -> str | None:
    return None


# --- user_sources registry --------------------------------------------


async def create_source(
    *,
    owner_user_id: UUID,
    source_type: str,
    external_ref: str,
    display_name: str,
    settings: dict | None = None,
) -> dict:
    """Register a connected source (idempotent on the natural key). For synced
    types the first sync runs immediately because `next_sync_at` defaults to
    now(). Types without a scheduled-sync interval (search-driven) have no
    indexer and must NOT enroll in the sync queue: the reconciler skips
    them without advancing next_sync_at, so an enabled row would sit "due"
    forever at the front of the due_sources window and starve real syncs."""
    validate_source_external_ref(source_type, external_ref)
    capability = SOURCE_CAPABILITY.get(source_type, "navigable")
    interval = DEFAULT_SYNC_INTERVAL_S.get(source_type, 3600)
    normalized_settings = normalize_source_settings(source_type, settings)
    sync_enabled = source_type in DEFAULT_SYNC_INTERVAL_S
    row = await get_pool().fetchrow(
        """
        INSERT INTO user_sources (
            owner_user_id, source_type, external_ref,
            display_name, capability, sync_interval_s, sync_enabled, settings
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        ON CONFLICT (owner_user_id, source_type, external_ref)
        DO UPDATE SET
            display_name = EXCLUDED.display_name,
            settings = EXCLUDED.settings,
            updated_at = now()
        RETURNING *
        """,
        owner_user_id,
        source_type,
        external_ref,
        display_name,
        capability,
        interval,
        sync_enabled,
        normalized_settings,
    )
    source = _source_row(row)
    await purge_disallowed_copied_documents(source)
    return source


async def purge_disallowed_copied_documents(source: dict) -> int:
    source_type = source["source_type"]
    source_id = UUID(source["id"])

    if source_type == "slack":
        allowed_channel_ids = slack_allowed_channel_ids(source)
        if not allowed_channel_ids:
            result = await get_pool().execute(
                "DELETE FROM slack_messages WHERE source_id = $1",
                source_id,
            )
        else:
            result = await get_pool().execute(
                "DELETE FROM slack_messages "
                "WHERE source_id = $1 "
                "AND (channel_id IS NULL OR channel_id <> ALL($2::text[]))",
                source_id,
                allowed_channel_ids,
            )
        return int(result.rsplit(" ", 1)[-1])

    if source_type == "gong_calls":
        allowed_workspace_ids = gong_allowed_workspace_ids(source)
        if not allowed_workspace_ids:
            result = await get_pool().execute(
                "DELETE FROM gong_documents WHERE source_id = $1",
                source_id,
            )
        else:
            result = await get_pool().execute(
                "DELETE FROM gong_documents "
                "WHERE source_id = $1 "
                "AND (gong_account_id IS NULL OR gong_account_id <> ALL($2::text[]))",
                source_id,
                allowed_workspace_ids,
            )
        return int(result.rsplit(" ", 1)[-1])

    return 0


async def list_connected_sources(user_id: UUID) -> list[dict]:
    """Connected sources `user_id` can read: the ones they own, plus any shared
    with them. Each row keeps its real owner_user_id, so reads of a shared source
    delegate to the source owner's token."""
    predicate = permission_service.readable_content_condition("source", "obj", 1)
    rows = await get_pool().fetch(
        f"SELECT obj.* FROM user_sources obj WHERE {predicate} "
        "ORDER BY obj.source_type, obj.display_name",
        user_id,
    )
    return [_source_row(r) for r in rows]


async def get_owned_source(source_id: UUID, user_id: UUID) -> dict | None:
    """Fetch a connected source only if `user_id` OWNS it — the gate for
    management and sync (reconfigure, delete, trigger re-index). Reads go through
    get_readable_source, which also honours shares."""
    row = await get_pool().fetchrow(
        "SELECT * FROM user_sources WHERE id = $1 AND owner_user_id = $2",
        source_id,
        user_id,
    )
    return _source_row(row) if row else None


async def get_source_by_type(owner_user_id: UUID, source_type: str) -> dict | None:
    """The owner's source of a given type, or None. Used for the single-per-user
    source types (x_saves, instagram_saves) that the extension pushes to without
    knowing the source id."""
    row = await get_pool().fetchrow(
        "SELECT * FROM user_sources WHERE owner_user_id = $1 AND source_type = $2",
        owner_user_id,
        source_type,
    )
    return _source_row(row) if row else None


async def get_readable_source(source_id: UUID, user_id: UUID) -> dict | None:
    """Fetch a connected source `user_id` may READ — they own it, or it was
    shared with them. The row keeps its real owner_user_id, so downstream reads
    fetch content with the OWNER's token (delegated access — the sharee never
    sees the token). Management/sync stay owner-only via get_owned_source."""
    predicate = permission_service.readable_content_condition("source", "obj", 2)
    row = await get_pool().fetchrow(
        f"SELECT obj.* FROM user_sources obj WHERE obj.id = $1 AND {predicate}",
        source_id,
        user_id,
    )
    return _source_row(row) if row else None


async def delete_source(source_id: UUID, user_id: UUID) -> bool:
    """Remove a connected source the user owns. Its documents cascade."""
    result = await get_pool().execute(
        "DELETE FROM user_sources WHERE id = $1 AND owner_user_id = $2",
        source_id,
        user_id,
    )
    return result.endswith("1")


async def delete_sources_for_provider(user_id: UUID, provider: str) -> list[dict]:
    """Remove all connected sources backed by one disconnected provider.
    Returns the deleted rows so callers audit exactly what was removed."""
    source_types = PROVIDER_SOURCE_TYPES.get(provider)
    if source_types is None:
        raise ValueError(f"unknown provider source mapping: {provider}")

    rows = await get_pool().fetch(
        "DELETE FROM user_sources "
        "WHERE owner_user_id = $1 AND source_type = ANY($2::text[]) "
        "RETURNING *",
        user_id,
        list(source_types),
    )
    return [_source_row(row) for row in rows]


async def get_source_for_sync(source_id: UUID) -> dict | None:
    """Everything a sync task needs to crawl one source. Not owner-gated —
    sync runs server-side on behalf of the owner via their stored token."""
    row = await get_pool().fetchrow(
        "SELECT id, owner_user_id, source_type, external_ref, sync_cursor, settings "
        "FROM user_sources WHERE id = $1",
        source_id,
    )
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "owner_user_id": str(row["owner_user_id"]),
        "source_type": row["source_type"],
        "external_ref": row["external_ref"],
        "sync_cursor": row["sync_cursor"],
        "settings": row["settings"] or {},
    }


async def due_sources(limit: int = 50) -> list[dict]:
    """Pull sources whose scheduled sync is due (for the Beat reconciler). Also
    reclaims sources stuck in 'syncing' for over 10 minutes: a sync killed
    mid-run (e.g. a worker redeploy) never reaches mark_sync_done, so without
    this the source would sit 'syncing' forever and never re-sync."""
    rows = await get_pool().fetch(
        "SELECT id, owner_user_id, source_type, external_ref, sync_cursor, settings "
        "FROM user_sources "
        "WHERE sync_enabled AND ("
        "  next_sync_at <= now() "
        "  OR (sync_status = 'syncing' AND updated_at < now() - interval '10 minutes')"
        ") "
        "ORDER BY next_sync_at LIMIT $1",
        limit,
    )
    return [
        {
            "id": str(r["id"]),
            "owner_user_id": str(r["owner_user_id"]),
            "source_type": r["source_type"],
            "external_ref": r["external_ref"],
            "sync_cursor": r["sync_cursor"],
            "settings": r["settings"] or {},
        }
        for r in rows
    ]


async def mark_sync_started(source_id: UUID) -> None:
    await get_pool().execute(
        "UPDATE user_sources SET sync_status = 'syncing', sync_error = NULL, "
        "next_sync_at = now() + (sync_interval_s || ' seconds')::interval, updated_at = now() "
        "WHERE id = $1",
        source_id,
    )


async def mark_sync_done(source_id: UUID, cursor: str | None) -> None:
    await get_pool().execute(
        "UPDATE user_sources SET sync_status = 'idle', sync_cursor = COALESCE($2, sync_cursor), "
        "last_synced_at = now(), updated_at = now() WHERE id = $1",
        source_id,
        cursor,
    )


async def mark_sync_failed(source_id: UUID, error: str) -> None:
    await get_pool().execute(
        "UPDATE user_sources SET sync_status = 'failed', sync_error = $2, updated_at = now() "
        "WHERE id = $1",
        source_id,
        error[:500],
    )


# --- per-integration document store -----------------------------------------

# source_type -> the table holding its documents.
SOURCE_TABLE = {
    "github_repo": "github_documents",
    "gmail": "gmail_index",
    "google_drive": "drive_index",
    "google_drive_folder": "drive_documents",
    "notion": "notion_index",
    "slack": "slack_messages",
    "granola": "granola_notes",
    "jira_project": "jira_documents",
    "asana_project": "asana_documents",
    "linear": "linear_index",
    "posthog_project": "posthog_index",
    "gong_calls": "gong_documents",
    "heavi_learnings": "heavi_learning_docs",
    "instagram_saves": "instagram_save_docs",
    "x_saves": "x_save_docs",
}

# Tables that COPY content (FTS + embeddings live in them). The rest are
# index-only and fetch their body lazily from the provider at read time.
# Notion copies content too — its crawl already renders each page's text to
# discover sub-pages, so storing it for FTS is nearly free. Gmail/Jira/Asana/
# Drive do NOT copy: they're index-only and search is federated to the
# provider's own search API (see FEDERATED_SEARCH_TYPES) so we don't duplicate
# their content.
CONTENT_TABLES = {
    "github_documents",
    "slack_messages",
    "granola_notes",
    "gong_documents",
    "notion_index",
    # A picked Drive folder is bounded, so its bodies are extracted once at sync
    # (OCR included) and stored. A whole-Drive source is not, and stays index-only.
    "drive_documents",
    # Extension-captured saves are an archive: content is hydrated once and
    # stored, so it survives the post being deleted or the account going private.
    "instagram_save_docs",
    "x_save_docs",
    # NB: heavi_learning_docs is intentionally absent — the table exists but
    # stays empty (no indexer); see the note on DEFAULT_SYNC_INTERVAL_S.
}

# Index-only source types whose `search` is federated live to the provider's
# native search instead of our FTS (no copied content). source_type -> the
# provider search coroutine, resolved lazily to avoid an import cycle.
FEDERATED_SEARCH_TYPES = {
    "gmail",
    "google_drive",
    "jira_project",
    "asana_project",
    "linear",
    "posthog_project",
}

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
    owner_user_id: UUID,
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
    extra = extra or {}
    existing_cols = ["content_hash", "deleted_at", *extra.keys()]
    existing = await pool.fetchrow(
        f"SELECT {', '.join(existing_cols)} FROM {table} WHERE source_id = $1 AND path = $2",
        source_id,
        path,
    )
    if (
        existing
        and existing["content_hash"] == new_hash
        and existing["deleted_at"] is None
        and all(existing[col] == value for col, value in extra.items())
    ):
        return "unchanged"

    cols = [
        "source_id",
        "owner_user_id",
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
        owner_user_id,
        path,
        name,
        kind,
        content,
        new_hash,
        external_ref,
        external_updated_at,
        True,
    ]
    for col, val in extra.items():
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
    owner_user_id: UUID,
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
        f"SELECT name, external_ref, external_updated_at, deleted_at FROM {table} "
        f"WHERE source_id = $1 AND path = $2",
        source_id,
        path,
    )
    if (
        existing
        and existing["deleted_at"] is None
        # name is part of the freshness check: some providers' names derive
        # from mutable fields (a tweet's name embeds the author's username)
        # without external_updated_at changing, and stale names would surface
        # in list/search results forever.
        and existing["name"] == name
        and existing["external_ref"] == external_ref
        and existing["external_updated_at"] == external_updated_at
    ):
        return "unchanged"
    await pool.execute(
        f"INSERT INTO {table} "
        f"(source_id, owner_user_id, path, name, kind, external_ref, external_updated_at) "
        f"VALUES ($1, $2, $3, $4, $5, $6, $7) "
        f"ON CONFLICT (source_id, path) DO UPDATE SET "
        f"name = EXCLUDED.name, kind = EXCLUDED.kind, external_ref = EXCLUDED.external_ref, "
        f"external_updated_at = EXCLUDED.external_updated_at, deleted_at = NULL, updated_at = now()",
        source_id,
        owner_user_id,
        path,
        name,
        kind,
        external_ref,
        external_updated_at,
    )
    return "inserted" if existing is None else "updated"


# Extraction outcomes that are final for a given version of the file: re-running
# on the same bytes reproduces the same outcome, so a sync re-queues these only
# when Drive's `modifiedTime` moves. Without this, an unsupported 200 MB video
# would be re-downloaded on every 30-minute sync, forever. 'pending' and
# 'processing' are in-flight, not settled — the sweep and claim in
# `tasks/drive_extraction.py` own their retry.
SETTLED_EXTRACTION_STATUSES = ("done", "unsupported", "too_large", "failed")


async def upsert_drive_document(
    *,
    source_id: UUID,
    owner_user_id: UUID,
    path: str,
    name: str,
    external_ref: str,
    external_updated_at,
) -> UUID | None:
    """Record a Drive folder file, and say whether its body needs extracting.

    Returns the row id when the file is new or has changed in Drive since we last
    extracted it, and None when its extraction is settled. Extraction is
    expensive — a scanned catalog is a Claude-vision call — so it is keyed on
    Drive's own `modifiedTime` rather than re-run on every sync. A 'failed' row
    rests once retries are spent; only a new version of the file revives it."""
    pool = get_pool()
    existing = await pool.fetchrow(
        "SELECT id, name, external_ref, external_updated_at, extraction_status, deleted_at "
        "FROM drive_documents WHERE source_id = $1 AND path = $2",
        source_id,
        path,
    )
    unchanged = (
        existing
        and existing["deleted_at"] is None
        and existing["name"] == name
        and existing["external_ref"] == external_ref
        and existing["external_updated_at"] == external_updated_at
        and existing["extraction_status"] in SETTLED_EXTRACTION_STATUSES
    )
    if unchanged:
        return None

    row = await pool.fetchrow(
        "INSERT INTO drive_documents "
        "(source_id, owner_user_id, path, name, kind, external_ref, external_updated_at, "
        " extraction_status, extraction_attempts) "
        "VALUES ($1, $2, $3, $4, 'file', $5, $6, 'pending', 0) "
        "ON CONFLICT (source_id, path) DO UPDATE SET "
        "name = EXCLUDED.name, external_ref = EXCLUDED.external_ref, "
        "external_updated_at = EXCLUDED.external_updated_at, "
        # Any text we already hold stays put while the new extraction runs. It is
        # at most one sync interval stale, which beats making the document
        # unreadable for the minutes an OCR pass takes.
        "extraction_status = 'pending', extraction_error = NULL, extraction_attempts = 0, "
        "locked_at = NULL, deleted_at = NULL, updated_at = now() "
        "RETURNING id",
        source_id,
        owner_user_id,
        path,
        name,
        external_ref,
        external_updated_at,
    )
    return row["id"]


async def remove_missing_documents(table: str, source_id: UUID, present_paths: list[str]) -> int:
    """Remove live docs whose path was absent from the latest crawl.

    Copied-content tables hold customer text and embeddings, so missing rows are
    physically deleted. Index-only tables hold provider refs with no copied body,
    so soft-delete keeps navigation state cheap to resurrect on the next sync.
    """
    if table in CONTENT_TABLES:
        result = await get_pool().execute(
            f"DELETE FROM {table} WHERE source_id = $1 AND path <> ALL($2::text[])",
            source_id,
            present_paths,
        )
        return int(result.split()[-1]) if result.startswith("DELETE") else 0

    result = await get_pool().execute(
        f"UPDATE {table} SET deleted_at = now() "
        f"WHERE source_id = $1 AND deleted_at IS NULL AND path <> ALL($2::text[])",
        source_id,
        present_paths,
    )
    return int(result.split()[-1]) if result.startswith("UPDATE") else 0


ENTRIES_LIMIT = 200


async def list_documents(
    source: dict, prefix: str = "", limit: int = ENTRIES_LIMIT, after: str = ""
) -> list[dict]:
    """List a source's live documents, optionally under a path prefix. `source`
    is the registry row (from get_owned_source / get_source_for_sync). `after`
    is a keyset cursor: only paths strictly greater (in the ORDER BY path
    ordering) are returned, so callers page through big sources by passing the
    last path of the previous page."""
    table = _table_for(source["source_type"])
    if table == "slack_messages":
        allowed_channel_ids = slack_allowed_channel_ids(source)
        if not allowed_channel_ids:
            return []
        # Slack's document projection is one transcript per channel per UTC day
        # (rows stay per-message). Cap-disclosure notices pass through as their
        # own documents; their 0000- leaf sorts them first in the channel.
        rows = await get_pool().fetch(
            """
            SELECT * FROM (
                SELECT channel_name || '/' || day AS path,
                       '#' || channel_name || ' ' || day AS name,
                       'transcript' AS kind,
                       NULL AS external_ref,
                       to_timestamp(last_ts) AS external_updated_at,
                       size
                FROM (
                    SELECT channel_name,
                           to_char(to_timestamp(ts::float8) AT TIME ZONE 'UTC',
                                   'YYYY-MM-DD') AS day,
                           max(ts::float8) AS last_ts,
                           sum(length(coalesce(content, ''))) AS size
                    FROM slack_messages
                    WHERE source_id = $1 AND deleted_at IS NULL AND kind = 'message'
                      AND channel_id = ANY($5::text[])
                    GROUP BY channel_name, day
                ) days
                UNION ALL
                SELECT path, name, kind, external_ref,
                       external_updated_at,
                       length(coalesce(content, '')) AS size
                FROM slack_messages
                WHERE source_id = $1 AND deleted_at IS NULL AND kind = 'notice'
                  AND channel_id = ANY($5::text[])
            ) docs
            WHERE path LIKE $2 AND path > $4
            ORDER BY path LIMIT $3
            """,
            UUID(source["id"]),
            f"{prefix}%",
            limit,
            after,
            allowed_channel_ids,
        )
        return [_entry_row(r) for r in rows]

    if table == "gong_documents":
        allowed_workspace_ids = gong_allowed_workspace_ids(source)
        if not allowed_workspace_ids:
            return []
        rows = await get_pool().fetch(
            f"SELECT path, name, kind, external_ref, external_updated_at, "
            f"length(coalesce(content, '')) AS size FROM {table} "
            f"WHERE source_id = $1 AND deleted_at IS NULL AND path LIKE $2 AND path > $4 "
            f"AND gong_account_id = ANY($5::text[]) "
            f"ORDER BY path LIMIT $3",
            UUID(source["id"]),
            f"{prefix}%",
            limit,
            after,
            allowed_workspace_ids,
        )
        return [_entry_row(r) for r in rows]

    is_content = table in CONTENT_TABLES
    size_column = "length(coalesce(content, ''))" if is_content else "NULL::bigint"
    # First paragraph of the copied content, whitespace-collapsed — a one-line
    # preview for the browse list (e.g. the tweet text for an X save).
    # E'\n\n' is a real double-newline; '\s+' must be a *standard* string literal
    # so the backslash reaches the regex engine (in an E-string \s isn't an
    # escape and silently collapses to 's').
    snippet_column = (
        "left(regexp_replace(split_part(coalesce(content, ''), E'\\n\\n', 1), '\\s+', ' ', 'g'), 200)"
        if is_content
        else "NULL::text"
    )
    rows = await get_pool().fetch(
        f"SELECT path, name, kind, external_ref, external_updated_at, "
        f"{size_column} AS size, {snippet_column} AS snippet FROM {table} "
        f"WHERE source_id = $1 AND deleted_at IS NULL AND path LIKE $2 AND path > $4 "
        f"ORDER BY path LIMIT $3",
        UUID(source["id"]),
        f"{prefix}%",
        limit,
        after,
    )
    return [_entry_row(r) for r in rows]


def _entry_row(r) -> dict:
    external_updated_at = r["external_updated_at"]
    return {
        "path": r["path"],
        "name": r["name"],
        "kind": r["kind"],
        "external_ref": r["external_ref"],
        "external_updated_at": (external_updated_at.isoformat() if external_updated_at else None),
        "size": r["size"],
        "snippet": r["snippet"] if "snippet" in r.keys() else None,
    }


_SLACK_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLACK_TS_RE = re.compile(r"^\d+\.\d+$")


async def _read_slack_document(
    source: dict, path: str, allowed_channel_ids: list[str]
) -> dict | None:
    """Read one Slack document. `{channel}/{YYYY-MM-DD}` returns that day's
    transcript; a per-message ref `{channel}/{ts}` (what search and
    fetch-history return) resolves to the transcript of the day it belongs to;
    anything else (cap-disclosure notices) reads its row directly."""
    channel, _, leaf = path.rpartition("/")
    if channel and _SLACK_TS_RE.match(leaf):
        day = datetime.fromtimestamp(float(leaf), UTC).strftime("%Y-%m-%d")
        return await _render_slack_day(source, channel, day, allowed_channel_ids)
    if channel and _SLACK_DAY_RE.match(leaf):
        return await _render_slack_day(source, channel, leaf, allowed_channel_ids)

    row = await get_pool().fetchrow(
        "SELECT path, name, kind, content FROM slack_messages "
        "WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL "
        "AND channel_id = ANY($3::text[])",
        UUID(source["id"]),
        path,
        allowed_channel_ids,
    )
    if not row:
        return None
    return {
        "path": row["path"],
        "name": row["name"],
        "kind": row["kind"],
        "content": row["content"] or "",
    }


async def _render_slack_day(
    source: dict, channel: str, day: str, allowed_channel_ids: list[str]
) -> dict | None:
    rows = await get_pool().fetch(
        """
        SELECT ts, author, content FROM slack_messages
        WHERE source_id = $1 AND deleted_at IS NULL AND kind = 'message'
          AND channel_id = ANY($2::text[]) AND channel_name = $3
          AND to_char(to_timestamp(ts::float8) AT TIME ZONE 'UTC', 'YYYY-MM-DD') = $4
        ORDER BY ts::float8
        """,
        UUID(source["id"]),
        allowed_channel_ids,
        channel,
        day,
    )
    if not rows:
        return None
    lines = [f"# #{channel} — {day} (UTC)", ""]
    for row in rows:
        clock = datetime.fromtimestamp(float(row["ts"]), UTC).strftime("%H:%M")
        # Continuation lines are indented so a line-leading HH:MM always means
        # a new message.
        text = (row["content"] or "").replace("\n", "\n    ")
        author = row["author"] or ""
        lines.append(f"{clock} {author}: {text}" if author else f"{clock} {text}")
    return {
        "path": f"{channel}/{day}",
        "name": f"#{channel} {day}",
        "kind": "transcript",
        "content": "\n".join(lines) + "\n",
    }


async def _read_linear_live_ref(source: dict, identifier: str) -> dict | None:
    from ..integrations.linear.indexer import fetch_linear_content

    owner_user_id = UUID(source["owner_user_id"])
    doc = {"path": identifier, "name": identifier, "kind": "issue"}
    try:
        content = await fetch_linear_content(owner_user_id, identifier)
    except Exception as exc:
        logger.warning(
            "source document fetch failed source=%s source_type=%s exception_type=%s",
            source["id"],
            source["source_type"],
            type(exc).__name__,
        )
        return {**doc, "content": "", "error": "source document fetch failed"}
    if not content:
        return None
    return {**doc, "content": content, "external_ref": identifier}


async def _read_heavi_live(source: dict, path: str) -> dict | None:
    """Every heavi read is live: the customer's endpoint is the source of
    truth, so we refetch the rules and resolve `path` (a rule path or a raw
    rule id) against them — never the cached copy."""
    from ..integrations.heavi.client import fetch_learnings
    from ..integrations.heavi.render import find_rule, rule_content, rule_name, rule_path

    rules = await fetch_learnings(UUID(source["owner_user_id"]))
    rule = find_rule(rules, path)
    if rule is None:
        return None
    return {
        "path": rule_path(rule),
        "name": rule_name(rule),
        "kind": "rule",
        "content": rule_content(rule),
        "external_ref": rule["id"],
    }


async def read_document(source: dict, path: str) -> dict | None:
    """Read one document. Content tables return their stored body; index-only
    tables fetch it lazily from the provider with the owner's token."""
    if source["source_type"] == "heavi_learnings":
        return await _read_heavi_live(source, path)

    # Any Linear identifier is readable live, even one not yet in the index.
    if source["source_type"] == "linear" and LINEAR_IDENTIFIER_RE.match(path):
        return await _read_linear_live_ref(source, path)

    table = _table_for(source["source_type"])
    if table in CONTENT_TABLES:
        if table == "slack_messages":
            allowed_channel_ids = slack_allowed_channel_ids(source)
            if not allowed_channel_ids:
                return None
            return await _read_slack_document(source, path, allowed_channel_ids)

        if table == "gong_documents":
            allowed_workspace_ids = gong_allowed_workspace_ids(source)
            if not allowed_workspace_ids:
                return None
            row = await get_pool().fetchrow(
                f"SELECT path, name, kind, content, external_ref FROM {table} "
                f"WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL "
                f"AND gong_account_id = ANY($3::text[])",
                UUID(source["id"]),
                path,
                allowed_workspace_ids,
            )
            if not row:
                return None
            return {
                "path": row["path"],
                "name": row["name"],
                "kind": row["kind"],
                "content": row["content"] or "",
                "external_ref": row["external_ref"],
            }

        if table == "drive_documents":
            return await _read_drive_document(UUID(source["id"]), path)

        if table == "instagram_save_docs":
            return await _read_instagram_save(UUID(source["id"]), path)

        if table == "x_save_docs":
            return await _read_x_save(UUID(source["id"]), path)

        row = await get_pool().fetchrow(
            f"SELECT path, name, kind, content, external_ref FROM {table} "
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
            "external_ref": row["external_ref"],
        }

    row = await get_pool().fetchrow(
        f"SELECT path, name, kind, external_ref FROM {table} "
        f"WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL",
        UUID(source["id"]),
        path,
    )
    if not row:
        return None
    try:
        content = await _lazy_fetch(source, row["external_ref"])
    except Exception as exc:
        logger.warning(
            "source document fetch failed source=%s source_type=%s exception_type=%s",
            source["id"],
            source["source_type"],
            type(exc).__name__,
        )
        return {
            "path": row["path"],
            "name": row["name"],
            "kind": row["kind"],
            "content": "",
            "error": "source document fetch failed",
        }
    return {
        "path": row["path"],
        "name": row["name"],
        "kind": row["kind"],
        "content": content,
        "external_ref": row["external_ref"],
    }


# extraction_status -> the HTTP status a read deserves when the row has no body.
DRIVE_UNREADABLE_STATUS = {
    "pending": 409,  # sync has seen it; the extraction child hasn't run yet
    "processing": 409,
    "unsupported": 415,  # a video, an archive — there is no text to read
    "too_large": 413,
    "failed": 422,  # extraction ran and blew up; the row records why
}


async def _read_drive_document(source_id: UUID, path: str) -> dict | None:
    """A Drive folder document, or a loud explanation of why it has no body.

    The row exists from the moment the sync walk sees the file; the body arrives
    later, from a child process. Returning `content or ""` for a row that has no
    content yet would tell the agent the catalog is blank — which is exactly the
    bug this table was built to kill.

    Text we already hold is served even while a re-extraction is pending: it is
    one sync interval stale at worst, and that is the same contract every other
    copied source has."""
    row = await get_pool().fetchrow(
        "SELECT path, name, kind, content, external_ref, extraction_status, extraction_error "
        "FROM drive_documents WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL",
        source_id,
        path,
    )
    if not row:
        return None
    if row["content"] is None:
        status = row["extraction_status"]
        return {
            "path": row["path"],
            "name": row["name"],
            "kind": row["kind"],
            "content": "",
            "error": row["extraction_error"] or f"extraction {status}",
            "http_status": DRIVE_UNREADABLE_STATUS[status],
        }
    return {
        "path": row["path"],
        "name": row["name"],
        "kind": row["kind"],
        "content": row["content"],
        "external_ref": row["external_ref"],
    }


async def _read_instagram_save(source_id: UUID, path: str) -> dict | None:
    """An Instagram save, or a loud explanation while hydration is pending —
    same contract as drive_documents: never hand back a blank body as if the
    post were empty. Hydrated docs carry a fresh presigned media URL so the
    archived video/image renders in the viewer."""
    from . import storage_service

    row = await get_pool().fetchrow(
        "SELECT path, name, kind, content, external_ref, media_storage_key, "
        "media_content_type, hydration_status, hydration_error "
        "FROM instagram_save_docs WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL",
        source_id,
        path,
    )
    if not row:
        return None
    if row["content"] is None:
        status = row["hydration_status"]
        return {
            "path": row["path"],
            "name": row["name"],
            "kind": row["kind"],
            "content": "",
            "error": row["hydration_error"] or f"hydration {status}",
            "http_status": 422 if status == "failed" else 409,
        }
    doc = {
        "path": row["path"],
        "name": row["name"],
        "kind": row["kind"],
        "content": row["content"],
        "external_ref": row["external_ref"],
    }
    if row["media_storage_key"]:
        doc["media_url"] = await storage_service.get_file_url(row["media_storage_key"])
        doc["media_content_type"] = row["media_content_type"]
    return doc


async def _read_x_save(source_id: UUID, path: str) -> dict | None:
    """A saved tweet, or a loud explanation while hydration is pending. Hydrated
    docs carry fresh presigned URLs for the archived images/video."""
    from . import storage_service

    row = await get_pool().fetchrow(
        "SELECT path, name, kind, content, external_ref, media, "
        "hydration_status, hydration_error "
        "FROM x_save_docs WHERE source_id = $1 AND path = $2 AND deleted_at IS NULL",
        source_id,
        path,
    )
    if not row:
        return None
    if row["content"] is None:
        status = row["hydration_status"]
        return {
            "path": row["path"],
            "name": row["name"],
            "kind": row["kind"],
            "content": "",
            "error": row["hydration_error"] or f"hydration {status}",
            "http_status": 422 if status == "failed" else 409,
        }
    doc = {
        "path": row["path"],
        "name": row["name"],
        "kind": row["kind"],
        "content": row["content"],
        "external_ref": row["external_ref"],
        "url": f"https://x.com/i/status/{row['path'].rsplit('/', 1)[-1]}",
    }
    media = row["media"] or []
    if media:
        doc["media"] = [
            {
                "url": await storage_service.get_file_url(m["storage_key"]),
                "content_type": m.get("content_type"),
            }
            for m in media
        ]
    return doc


async def _lazy_fetch(source: dict, external_ref: str | None) -> str:
    """Fetch an index-only document's body from the provider. Local import keeps
    the integration indexers (which import this module) free of a cycle."""
    if not external_ref:
        return ""
    source_type = source["source_type"]
    owner_user_id = UUID(source["owner_user_id"])
    if source_type == "google_drive":
        from ..integrations.google.indexer import fetch_drive_content

        return await fetch_drive_content(owner_user_id, external_ref)
    if source_type == "gmail":
        from ..integrations.gmail.indexer import fetch_gmail_content

        return await fetch_gmail_content(owner_user_id, source["external_ref"], external_ref)
    if source_type == "jira_project":
        from ..integrations.jira.indexer import fetch_jira_content

        return await fetch_jira_content(owner_user_id, external_ref)
    if source_type == "asana_project":
        from ..integrations.asana.indexer import fetch_asana_content

        return await fetch_asana_content(owner_user_id, external_ref)
    if source_type == "linear":
        from ..integrations.linear.indexer import fetch_linear_content

        return await fetch_linear_content(owner_user_id, external_ref)
    if source_type == "posthog_project":
        from ..integrations.posthog.indexer import fetch_posthog_content

        return await fetch_posthog_content(owner_user_id, external_ref)
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


def _scoped_search_error(source: dict, e: Exception) -> Exception:
    """Map a scoped-search provider failure to an HTTP error the API can serve.
    A provider 401 must not surface as OUR 401 (clients read that as Stash
    session expiry), and provider HTTP errors must not escape as raw 500s."""
    name = source["display_name"] or source["source_type"]
    if isinstance(e, HTTPException) and e.status_code == 401:
        return HTTPException(status_code=409, detail=e.detail)
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 429:
            return HTTPException(
                status_code=429,
                detail=f"{name} rate limit reached — try again in a few minutes",
            )
        if status in (401, 403):
            return HTTPException(
                status_code=409,
                detail=f"{name} rejected the connection — reconnect it in Settings",
            )
        return HTTPException(status_code=502, detail=f"{name} search failed (HTTP {status})")
    return e


async def _federated_search(
    source: dict, query: str, limit: int, *, swallow_errors: bool = True
) -> list[dict]:
    """Run a federated source's native provider search. Returns unified hits
    ({source, source_name, ref, name, snippet}). In the unscoped fan-out a
    provider error (revoked token, rate limit) is logged and returned as a
    single error marker ({source, source_name, error, needs_reconnect}) so the
    rest of the search stays alive while the dead source is still surfaced —
    dropping it silently would read as "no matches" for that source. A SCOPED
    search raises instead, so the API serves an explicit HTTP error.

    Providers cap results (SEARCH_LIMIT); when a provider reports it matched
    more than it returned, a trailing truncation marker ({source, source_name,
    truncated, returned, estimated_total}) is appended so callers disclose the
    cut instead of presenting the top slice as the whole result."""
    source_type = source["source_type"]
    try:
        if source_type == "google_drive":
            from ..integrations.google.indexer import search_drive as fn
        elif source_type == "gmail":
            from ..integrations.gmail.indexer import search_gmail as fn
        elif source_type == "jira_project":
            from ..integrations.jira.indexer import search_jira as fn
        elif source_type == "asana_project":
            from ..integrations.asana.indexer import search_asana as fn
        elif source_type == "linear":
            from ..integrations.linear.indexer import search_linear as fn
        elif source_type == "posthog_project":
            from ..integrations.posthog.indexer import search_posthog as fn
        else:
            return []
        result = await fn(source, query, limit)
    except Exception as exc:
        if not swallow_errors:
            raise _scoped_search_error(source, exc) from exc
        logger.warning(
            "federated search failed source=%s source_type=%s exception_type=%s",
            source["id"],
            source_type,
            type(exc).__name__,
        )
        # Only the classified message is safe to surface — an unmapped exception
        # may carry the token or query in its text, so it gets a generic label.
        mapped = _scoped_search_error(source, exc)
        if isinstance(mapped, HTTPException):
            detail = mapped.detail
            needs_reconnect = mapped.status_code == 409
        else:
            detail = f"{source['display_name'] or source_type} search failed"
            needs_reconnect = False
        return [
            {
                "source": source["id"],
                "source_name": source["display_name"],
                "error": detail,
                "needs_reconnect": needs_reconnect,
            }
        ]
    # Gmail reports truncation as {hits, truncated, estimated_total}; the other
    # providers still return a plain hit list (no truncation signal yet).
    if isinstance(result, dict):
        hits = result["hits"]
        truncated = result["truncated"]
        estimated_total = result.get("estimated_total")
    else:
        hits = result
        truncated = False
        estimated_total = None
    output = [
        {
            "source": source["id"],
            "source_name": source["display_name"],
            "ref": h["ref"],
            "name": h.get("name", ""),
            "snippet": h.get("snippet", ""),
        }
        for h in hits
    ]
    if truncated:
        output.append(
            {
                "source": source["id"],
                "source_name": source["display_name"],
                "truncated": True,
                "returned": len(hits),
                "estimated_total": estimated_total,
            }
        )
    return output


async def search_documents(
    *,
    user_id: UUID,
    query: str,
    source: dict | None = None,
    limit: int = 20,
) -> list[dict]:
    """FTS over copied-content sources the user can read — their own or shared
    with them (github/slack/granola), UNIONed across their tables. Pass `source`
    to scope to one; an index-only source has nothing to FTS, so it returns []."""
    limit = min(limit, 100)
    tables = sorted(CONTENT_TABLES)
    source_id: UUID | None = None
    if source is not None:
        table = _table_for(source["source_type"])
        if table not in CONTENT_TABLES:
            return []
        tables = [table]
        source_id = UUID(source["id"])

    def visibility_clause(table: str) -> str:
        if table == "slack_messages":
            return (
                "AND d.channel_id = ANY(ARRAY("
                "SELECT jsonb_array_elements_text("
                "COALESCE(s.settings->'allowed_channel_ids', '[]'::jsonb)"
                ")))"
            )
        if table == "gong_documents":
            return (
                "AND d.gong_account_id = ANY(ARRAY("
                "SELECT jsonb_array_elements_text("
                "COALESCE(s.settings->'allowed_workspace_ids', '[]'::jsonb)"
                ")))"
            )
        return ""

    source_readable = permission_service.readable_content_condition("source", "s", 1)
    parts = [
        f"""
        SELECT d.source_id, d.path, d.name, LEFT(d.content, 400) AS snippet,
               ts_rank(to_tsvector('english', coalesce(d.content, '')),
                       websearch_to_tsquery('english', $2)) AS rank
        FROM {t} d
        JOIN user_sources s ON s.id = d.source_id
        WHERE {source_readable} AND d.deleted_at IS NULL
          AND ($3::uuid IS NULL OR d.source_id = $3)
          AND to_tsvector('english', coalesce(d.content, ''))
              @@ websearch_to_tsquery('english', $2)
          {visibility_clause(t)}
        """
        for t in tables
    ]
    union = " UNION ALL ".join(parts)
    rows = await get_pool().fetch(
        f"SELECT u.source_id, ws.display_name AS source_name, u.path, u.name, u.snippet "
        f"FROM ({union}) u JOIN user_sources ws ON ws.id = u.source_id "
        f"ORDER BY u.rank DESC LIMIT $4",
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


async def list_sources(owner_user_id: UUID, user_id: UUID) -> list[dict]:
    """Every source in this scope's view: the two native sources plus the
    scope's connected sources. In personal scope (owner == user) that is the
    caller's own view; in a workspace scope it is the workspace's connections
    (the org Drive etc.), readable by every member."""
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
    for s in await list_connected_sources(owner_user_id):
        item = {
            "source": s["id"],
            "provider": SOURCE_TYPE_PROVIDER[s["source_type"]],
            "type": s["source_type"],
            "capability": s["capability"],
            "display_name": s["display_name"],
            # Sync bookkeeping for the per-integration page (the sidebar
            # ignores these). Already on the row — no extra query.
            "external_ref": s["external_ref"],
            "sync_enabled": s["sync_enabled"],
            "sync_status": s["sync_status"],
            "sync_error": s["sync_error"],
            "last_synced_at": s["last_synced_at"],
            "settings": s["settings"],
        }
        hint = _source_search_hint(s)
        if hint:
            item["search_hint"] = hint
        sources.append(item)
    return sources


async def source_item_count(source: dict) -> int | None:
    """How many live documents a source has indexed. None for a source type with
    no document table."""
    table = SOURCE_TABLE.get(source["source_type"])
    if table is None:
        return None
    if table == "slack_messages":
        allowed_channel_ids = slack_allowed_channel_ids(source)
        if not allowed_channel_ids:
            return 0
        row = await get_pool().fetchrow(
            f"SELECT count(*) AS n FROM {table} "
            f"WHERE source_id = $1 AND deleted_at IS NULL AND channel_id = ANY($2::text[])",
            UUID(source["id"]),
            allowed_channel_ids,
        )
        return int(row["n"]) if row else 0

    if table == "gong_documents":
        allowed_workspace_ids = gong_allowed_workspace_ids(source)
        if not allowed_workspace_ids:
            return 0
        row = await get_pool().fetchrow(
            f"SELECT count(*) AS n FROM {table} "
            f"WHERE source_id = $1 AND deleted_at IS NULL "
            f"AND gong_account_id = ANY($2::text[])",
            UUID(source["id"]),
            allowed_workspace_ids,
        )
        return int(row["n"]) if row else 0

    row = await get_pool().fetchrow(
        f"SELECT count(*) AS n FROM {table} WHERE source_id = $1 AND deleted_at IS NULL",
        UUID(source["id"]),
    )
    return int(row["n"]) if row else 0


# --- unified VFS over native + connected sources ----------------------------


async def _resolve_connected(source: str, owner_user_id: UUID, user_id: UUID) -> dict | None:
    """Resolve a connected-source handle for READING — the owner or anyone the
    source was shared with. Reads delegate to the source owner's token."""
    try:
        source_id = UUID(source)
    except ValueError:
        return None
    return await get_readable_source(source_id, user_id)


async def _audit_source_read(
    *,
    action: str,
    owner_user_id: UUID,
    user_id: UUID,
    source: str | None,
    connected: dict | None,
    metadata: dict,
) -> None:
    """Audit a successful source read. Lives here — not in the routers — so
    every front door to the same data (REST, agent tools) hits the same trail."""
    target_type = "source"
    target_id = source
    source_type = None
    provider = None
    if source is None:
        target_type = "source_collection"
        target_id = None
    elif source in (NATIVE_FILES, NATIVE_SESSIONS):
        source_type = source
    elif connected is not None:
        target_id = connected["id"]
        source_type = connected["source_type"]
        provider = SOURCE_TYPE_PROVIDER.get(source_type)
        # Delegated read: a recipient reads a shared source through Stash, but the
        # data belongs to the source owner. Attribute the trail to the owner so it
        # lands in the OWNER's audit log — that's how they see who read what they
        # shared. The reader is still recorded as the actor.
        owner_user_id = UUID(connected["owner_user_id"])

    await security_audit_service.record_event(
        action=action,
        actor_user_id=user_id,
        owner_user_id=owner_user_id,
        target_type=target_type,
        target_id=target_id,
        provider=provider,
        source_type=source_type,
        metadata=metadata,
    )


async def source_entries(
    owner_user_id: UUID,
    user_id: UUID,
    source: str,
    prefix: str = "",
    limit: int = ENTRIES_LIMIT,
    after: str = "",
) -> list[dict] | None:
    """List a source's entries like a file system. `source` is a handle from
    `list_sources` ('files', 'sessions', or a connected-source id); `prefix`
    scopes connected sources to a path. `after` pages through path-ordered
    document listings (see list_documents); listings that aren't path-ordered
    (native files/sessions) return everything on the first
    page, so any later page is empty for them.
    Returns None for an unknown source."""
    connected = None
    if source == NATIVE_FILES:
        from .files_tree_service import list_scope_pages

        pages = [] if after else await list_scope_pages(owner_user_id, user_id)
        entries = [{"id": str(p["id"]), "name": p["name"], "kind": "page"} for p in pages]
    elif source == NATIVE_SESSIONS:
        from .memory_service import list_scope_sessions

        sessions = [] if after else await list_scope_sessions(owner_user_id, user_id)
        entries = [
            {"id": s["session_id"], "name": s.get("agent_name") or "session", "kind": "session"}
            for s in sessions
        ]
    else:
        connected = await _resolve_connected(source, owner_user_id, user_id)
        if connected is None:
            return None
        if connected["source_type"] == "heavi_learnings":
            # Fully live: the listing comes from the customer's endpoint, not
            # the cached table, so a rule added or deleted upstream shows up
            # on the next ls. Everything fits one page (dozens of rules).
            from ..integrations.heavi.client import fetch_learnings
            from ..integrations.heavi.render import rule_entries

            rules = [] if after else await fetch_learnings(UUID(connected["owner_user_id"]))
            entries = rule_entries(rules, prefix)
        else:
            entries = await list_documents(connected, prefix=prefix, limit=limit, after=after)

    await _audit_source_read(
        action="source.entries_listed",
        owner_user_id=owner_user_id,
        user_id=user_id,
        source=source,
        connected=connected,
        metadata={
            "path_hash": security_audit_service.hash_value(prefix),
            "result_count": len(entries),
        },
    )
    return entries


# --- sources tree: the whole scope as one filesystem -------------------------

# Per-source row budget when building the tree. ORDER BY path means a source
# bigger than this shows a path-ordered slice; the per-directory caps below
# keep the rendered tree honest about what's hidden.
TREE_DOC_LIMIT = 5000


def build_entry_tree(entries: list[dict], depth: int, per_dir: int) -> list[dict]:
    """Nest flat path-keyed entries ({path, name, kind}) into a tree trimmed to
    `depth` levels, with at most `per_dir` children per directory. Directories
    are synthesized from path segments; a capped directory gets a final
    {"kind": "truncated", "hidden": n} child so renderers can say '+n more'."""
    root: dict[str, dict] = {}
    for entry in entries:
        parts = [part for part in entry["path"].split("/") if part]
        if not parts:
            continue
        children = root
        for index, part in enumerate(parts[:depth]):
            is_entry = index == len(parts) - 1
            node = children.get(part)
            if node is None:
                node = {"name": part, "kind": "folder", "children": {}}
                children[part] = node
            if is_entry:
                node["kind"] = entry["kind"]
                node["path"] = entry["path"]
                # Display the document's name, not the raw path segment — path
                # leaves carry sort keys and id suffixes (Gmail's "06 1430 …"),
                # while the name is the human label (the subject).
                node["name"] = entry["name"] or part
            children = node["children"]
    return _finalize_tree(root, per_dir)


def _finalize_tree(children: dict[str, dict], per_dir: int) -> list[dict]:
    nodes = []
    names = sorted(children)
    for name in names[:per_dir]:
        node = children[name]
        out = {"name": node["name"], "kind": node["kind"]}
        if "path" in node:
            out["path"] = node["path"]
        kids = _finalize_tree(node["children"], per_dir)
        if kids:
            out["children"] = kids
        nodes.append(out)
    hidden = len(names) - per_dir
    if hidden > 0:
        nodes.append({"name": "", "kind": "truncated", "hidden": hidden})
    return nodes


def _capped_flat_tree(entries: list[dict], per_dir: int) -> list[dict]:
    nodes = entries[:per_dir]
    hidden = len(entries) - per_dir
    if hidden > 0:
        nodes.append({"name": "", "kind": "truncated", "hidden": hidden})
    return nodes


def _session_title(session: dict) -> str:
    """A human-readable session label: the first user message, one line."""
    title = " ".join((session.get("title_source") or "").split())
    if len(title) > 80:
        title = title[:77] + "…"
    return title or session.get("agent_name") or "session"


async def _member_tree(source: dict, depth: int, per_dir: int) -> list[dict]:
    """The document tree for one connected source (one repo, one account)."""
    entries = await list_documents(source, limit=TREE_DOC_LIMIT)
    return build_entry_tree(entries, depth, per_dir)


async def _provider_tree_node(provider: str, members: list[dict], depth: int, per_dir: int) -> dict:
    """One provider folder for the sources filesystem. A single connection
    collapses — its documents sit directly in the provider folder. Multiple
    connections each become a subfolder named after the connection."""
    members = sorted(members, key=lambda m: m["display_name"])
    node = {
        "source": provider,
        "type": "provider",
        "provider": provider,
        "display_name": provider,
        # Connection handles, so a caller drilling into the tree knows which
        # source to read each path against (the provider key is not a handle).
        "members": [{"handle": m["id"], "display_name": m["display_name"]} for m in members],
    }
    if len(members) == 1:
        node["tree"] = await _member_tree(members[0], depth, per_dir)
        node["sync_status"] = members[0]["sync_status"]
        node["last_synced_at"] = members[0]["last_synced_at"]
        return node

    children = []
    for member in members:
        children.append(
            {
                "name": member["display_name"],
                "kind": "folder",
                "source": member["id"],
                "sync_status": member["sync_status"],
                "children": await _member_tree(member, max(1, depth - 1), per_dir),
            }
        )
    node["tree"] = _capped_flat_tree(children, per_dir)
    return node


async def sources_tree(
    owner_user_id: UUID, user_id: UUID, depth: int = 3, per_dir: int = 50
) -> list[dict]:
    """Every source the user can see, each with a nested entry tree — one call
    renders the whole scope as a filesystem (`stash ls`)."""
    from .files_tree_service import list_scope_pages
    from .memory_service import list_scope_sessions

    depth = max(1, min(depth, 10))
    pages = await list_scope_pages(owner_user_id, user_id)
    sessions = await list_scope_sessions(owner_user_id, user_id)
    out = [
        {
            "source": NATIVE_FILES,
            "type": "native_files",
            "display_name": "Files",
            "tree": _capped_flat_tree(
                [{"name": p["name"], "kind": "page", "ref": str(p["id"])} for p in pages],
                per_dir,
            ),
        },
        {
            "source": NATIVE_SESSIONS,
            "type": "native_sessions",
            "display_name": "Session transcripts",
            "tree": _capped_flat_tree(
                [
                    {
                        "name": _session_title(s),
                        "kind": "session",
                        "ref": s["session_id"],
                    }
                    for s in sessions
                ],
                per_dir,
            ),
        },
    ]

    # Group connected sources under their provider — the top tier of the
    # filesystem. The provider folder is the unit ("github", "granola"); the
    # individual connections (repos, accounts) live inside it.
    by_provider: dict[str, list[dict]] = {}
    for source in await list_connected_sources(owner_user_id):
        provider = SOURCE_TYPE_PROVIDER[source["source_type"]]
        by_provider.setdefault(provider, []).append(source)

    for provider in sorted(by_provider):
        out.append(await _provider_tree_node(provider, by_provider[provider], depth, per_dir))

    await _audit_source_read(
        action="source.tree_listed",
        owner_user_id=owner_user_id,
        user_id=user_id,
        source=None,
        connected=None,
        metadata={"source_count": len(out)},
    )
    return out


def source_document_url(
    source_type: str,
    external_ref: str | None,
    path: str,
    extra: dict | None = None,
) -> str | None:
    """Canonical provider URL for one document, so the UI can deep-link back to
    the original. `external_ref` is the SOURCE row's ref (e.g. github "owner/repo"),
    `path` is the document handle, and `extra` carries any stored provider metadata.
    Returns None when a link can't be derived. Jira is NOT handled here — it needs a
    network lookup for the site URL, so `source_document` builds it (see site_url)."""
    extra = extra or {}
    if source_type == "github_repo" and external_ref:
        return f"https://github.com/{external_ref}/blob/HEAD/{path}"
    if source_type == "asana_project":
        return f"https://app.asana.com/0/0/{path}"
    if source_type == "notion":
        if extra.get("url"):
            return extra["url"]
        return f"https://www.notion.so/{path.replace('-', '')}"
    if source_type == "google_drive":
        link = extra.get("web_view_link") or extra.get("webViewLink")
        if link:
            return link
        return f"https://drive.google.com/file/d/{path}/view"
    if source_type == "gmail":
        mailbox = quote(external_ref or "0", safe="")
        return f"https://mail.google.com/mail/u/{mailbox}/#all/{path}"
    if source_type == "x_saves":
        return f"https://x.com/i/status/{path.rsplit('/', 1)[-1]}"
    if source_type == "instagram_saves":
        return f"https://www.instagram.com/p/{path}/"
    # slack, granola, gong_calls: deep link TODO — needs team domain / note url / gong subdomain.
    return None


async def source_document(
    owner_user_id: UUID, user_id: UUID, source: str, ref: str
) -> tuple[bool, dict | None]:
    """Read one document. `ref` is a page id (files), a session id (sessions),
    or a document path (connected sources). Returns `(source_ok, doc)`:
    `source_ok` is False when the handle is unknown / not owned, and `doc` is
    None when the source is valid but the document is missing — callers keep the
    two not-found cases distinct (an unowned source must never look like a typo)."""
    connected = None
    if source == NATIVE_FILES:
        from .files_tree_service import get_page

        page = await get_page(UUID(ref), owner_user_id, user_id)
        doc = (
            {
                "name": page["name"],
                "content": page.get("content_markdown") or page.get("content_html") or "",
            }
            if page
            else None
        )
    elif source == NATIVE_SESSIONS:
        from .memory_service import read_session_events

        events = await read_session_events(owner_user_id, ref, user_id)
        transcript = "\n".join(
            f"[{e.get('event_type')}] {(e.get('content') or '')[:2000]}" for e in events
        )
        doc = {"session": ref, "transcript": transcript[:8000]}
    else:
        connected = await _resolve_connected(source, owner_user_id, user_id)
        if connected is None:
            return False, None
        doc = await read_document(connected, ref)
        if doc is not None and "error" not in doc:
            doc["url"] = await _deep_link(connected, doc)

    if doc is not None:
        await _audit_source_read(
            action="source.document_read",
            owner_user_id=owner_user_id,
            user_id=user_id,
            source=source,
            connected=connected,
            metadata={"ref_hash": security_audit_service.hash_value(ref)},
        )
    return True, doc


async def _deep_link(source: dict, doc: dict) -> str | None:
    """The provider URL for one read document. Jira needs a network lookup for the
    site URL; everything else derives from stored refs (see source_document_url).
    Any failure (e.g. Jira lookup) yields no link rather than failing the read."""
    source_type = source["source_type"]
    doc_ref = doc.get("external_ref")

    if source_type == "github_repo":
        return source_document_url("github_repo", source["external_ref"], doc["path"])
    if source_type == "instagram_saves":
        return f"https://www.instagram.com/p/{doc['path']}/"
    if source_type == "asana_project":
        # The task gid lives in external_ref; the path is "Section/Name (gid)".
        return source_document_url("asana_project", None, doc_ref)
    if source_type in ("notion", "google_drive"):
        # The page/file id lives on the document row, not the source row.
        return source_document_url(source_type, None, doc_ref or doc["path"])
    if source_type == "gmail":
        # The message id lives in external_ref; the path is date-foldered.
        return source_document_url(source_type, source["external_ref"], doc_ref)
    if source_type == "jira_project":
        from ..integrations.jira.indexer import site_url

        try:
            base = await site_url(source)
        except Exception as exc:
            logger.warning(
                "jira site_url lookup failed source=%s exception_type=%s",
                source["id"],
                type(exc).__name__,
            )
            return None
        if not base:
            return None
        # The real issue key lives in external_ref ("{cloudId}:{key}"); the path
        # is the zero-padded listing key, which Jira wouldn't resolve.
        _, _, key = (doc_ref or "").partition(":")
        return f"{base}/browse/{key}"
    return source_document_url(source_type, source.get("external_ref"), doc["path"])


def _parse_dt(value: str | None):
    """Parse an ISO-8601 date/datetime (with or without 'Z'). Naive → UTC."""
    from datetime import UTC, datetime

    if not value or not value.strip():
        return None
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def fetch_history(
    owner_user_id: UUID,
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
    connected = await _resolve_connected(source, owner_user_id, user_id)
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
    try:
        result = await fn(connected, since_dt, until_dt, min(limit, 1000))
    except Exception as exc:
        logger.warning(
            "source history fetch failed source=%s source_type=%s exception_type=%s",
            connected["id"],
            connected["source_type"],
            type(exc).__name__,
        )
        result = {"error": "source history fetch failed"}
    await _audit_source_read(
        action="source.history_fetched",
        owner_user_id=owner_user_id,
        user_id=user_id,
        source=source,
        connected=connected,
        metadata={
            "since_hash": security_audit_service.hash_value(since),
            "until_hash": security_audit_service.hash_value(until),
            "limit": limit,
            "fetched": result.get("fetched"),
            "error": bool(result.get("error")),
        },
    )
    return result


async def _external_ref_matches(sources: list[dict], query: str, limit: int) -> list[dict]:
    """Documents whose provider id (`external_ref`) exactly equals the query,
    across the given sources' document tables."""
    query = query.strip()
    if not query:
        return []
    hits: list[dict] = []
    for s in sources:
        table = SOURCE_TABLE.get(s["source_type"])
        if table is None:
            continue
        rows = await get_pool().fetch(
            f"SELECT path, name FROM {table} "
            f"WHERE source_id = $1 AND external_ref = $2 AND deleted_at IS NULL LIMIT $3",
            UUID(s["id"]),
            query,
            limit,
        )
        hits += [
            {
                "source": s["id"],
                "source_name": s["display_name"],
                "ref": r["path"],
                "name": r["name"],
                "snippet": "",
            }
            for r in rows
        ]
    return hits


async def search_all(
    owner_user_id: UUID,
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
        from .memory_service import search_scope_events

        events = await search_scope_events(owner_user_id, user_id, query, limit=limit)
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

        pages = await search_pages_fts(owner_user_id, query, limit=limit, user_id=user_id)
        results += [
            {
                "source": NATIVE_FILES,
                "ref": str(p["id"]),
                "name": p["name"],
                "snippet": (p.get("search_text") or p.get("content_markdown") or "")[:300],
            }
            for p in pages
        ]

    # Connected sources: all of the scope's own when unscoped, else the one named.
    connected: dict | None = None
    if source not in (None, NATIVE_FILES, NATIVE_SESSIONS):
        connected = await _resolve_connected(source, owner_user_id, user_id)
        if connected is None:
            return None
    if source is None or connected is not None:
        searched_sources = (
            [connected] if connected is not None else await list_connected_sources(owner_user_id)
        )

        # A query that IS a provider id (a Drive file id, a Gmail message id, …)
        # resolves to the indexed document directly. This is how an agent holding
        # only a provider URL finds the document's Stash path.
        results += await _external_ref_matches(searched_sources, query, limit)

        # Copied-content sources go through our FTS (returns [] for index-only /
        # federated sources, which have no stored content to match).
        docs = await search_documents(
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
        # one source, raising on provider errors so a dead connection is never
        # mistaken for "no matches"; unscoped → fan out across the user's
        # federated sources (each call keeps search alive by returning its own
        # error as a marker instead of raising).
        if connected is not None:
            if connected["source_type"] in FEDERATED_SEARCH_TYPES:
                results += await _federated_search(connected, query, limit, swallow_errors=False)
        else:
            federated = [s for s in searched_sources if s["source_type"] in FEDERATED_SEARCH_TYPES]
            for hits in await asyncio.gather(
                *(_federated_search(s, query, limit) for s in federated)
            ):
                results += hits

    await _audit_source_read(
        action="source.searched",
        owner_user_id=owner_user_id,
        user_id=user_id,
        source=source,
        connected=connected,
        metadata={
            "query_hash": security_audit_service.hash_value(query),
            "limit": limit,
            "result_count": len(results),
        },
    )
    return results
