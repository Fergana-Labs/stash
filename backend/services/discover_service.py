"""Curated public catalog of Stashes.

Discover lists workspaces that are both public (`is_public=true`) and selected
for the catalog (`discoverable=true`). Public-but-unlisted and link-shared
workspaces remain readable through the permission-aware public endpoints.
"""

import base64
from datetime import datetime
from uuid import UUID

from ..database import get_pool

# `is_public` is derived from object_permissions — the legacy boolean
# column on workspaces is gone.
_IS_PUBLIC_EXPR = (
    "EXISTS("
    "  SELECT 1 FROM object_permissions op "
    "  WHERE op.object_type = 'workspace' AND op.object_id = w.id "
    "    AND op.visibility = 'public'"
    ")"
)

_CATALOG_SELECT = f"""
SELECT
    w.id, w.name, w.summary, w.description, {_IS_PUBLIC_EXPR} AS is_public,
    w.tags, w.category, w.discoverable, w.featured, w.cover_image_url,
    w.creator_id, u.name AS creator_name, u.display_name AS creator_display_name,
    w.fork_count, w.forked_from_workspace_id, w.created_at, w.updated_at,
    (SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count,
    (SELECT COUNT(*) FROM pages p WHERE p.workspace_id = w.id) AS page_count,
    (SELECT COUNT(*) FROM tables t WHERE t.workspace_id = w.id) AS table_count,
    (SELECT COUNT(*) FROM files f WHERE f.workspace_id = w.id) AS file_count,
    (SELECT COUNT(*) FROM history_events he WHERE he.workspace_id = w.id) AS history_event_count
FROM workspaces w
JOIN users u ON u.id = w.creator_id
"""

# Fixed page size keeps the cursor format simple.
PAGE_SIZE = 24


async def list_catalog(
    *,
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    sort: str = "trending",
    cursor: str | None = None,
) -> tuple[list[dict], str | None]:
    pool = get_pool()
    where = ["EXISTS(SELECT 1 FROM object_permissions op WHERE op.object_type = 'workspace' AND op.object_id = w.id AND op.visibility = 'public')", "w.discoverable = true"]
    args: list = []
    idx = 1

    if query:
        where.append(
            f"(w.name ILIKE ${idx} OR w.summary ILIKE ${idx} OR w.description ILIKE ${idx})"
        )
        args.append(f"%{query}%")
        idx += 1
    if category:
        where.append(f"w.category = ${idx}")
        args.append(category)
        idx += 1
    if tag:
        where.append(f"${idx} = ANY(w.tags)")
        args.append(tag)
        idx += 1

    if sort == "newest":
        order = "w.created_at DESC, w.id DESC"
        cursor_col = "w.created_at"
    elif sort == "forks":
        order = "w.fork_count DESC, w.created_at DESC, w.id DESC"
        cursor_col = "w.fork_count"
    else:
        # trending: featured first, then recently updated.
        order = "w.featured DESC, w.updated_at DESC, w.id DESC"
        cursor_col = "w.updated_at"

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            where.append(f"{cursor_col} < ${idx}")
            args.append(decoded)
            idx += 1

    sql = f"{_CATALOG_SELECT} WHERE {' AND '.join(where)} ORDER BY {order} LIMIT {PAGE_SIZE + 1}"
    rows = await pool.fetch(sql, *args)
    items = [dict(r) for r in rows[:PAGE_SIZE]]

    next_cursor = None
    if len(rows) > PAGE_SIZE:
        last = items[-1]
        if sort == "forks":
            next_cursor = _encode_cursor(last["fork_count"])
        elif sort == "newest":
            next_cursor = _encode_cursor(last["created_at"])
        else:
            next_cursor = _encode_cursor(last["updated_at"])
    return items, next_cursor


async def get_featured() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        f"{_CATALOG_SELECT} WHERE EXISTS(SELECT 1 FROM object_permissions op WHERE op.object_type = 'workspace' AND op.object_id = w.id AND op.visibility = 'public') AND w.discoverable = true "
        "AND w.featured = true "
        "ORDER BY w.updated_at DESC LIMIT 12"
    )
    return [dict(r) for r in rows]


async def get_public_detail(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    ws_row = await pool.fetchrow(
        f"{_CATALOG_SELECT} WHERE w.id = $1 AND EXISTS(SELECT 1 FROM object_permissions op WHERE op.object_type = 'workspace' AND op.object_id = w.id AND op.visibility = 'public') " "AND w.discoverable = true",
        workspace_id,
    )
    if not ws_row:
        return None

    folders = await pool.fetch(
        "SELECT f.id, f.name, f.parent_folder_id, f.updated_at, "
        "(SELECT COUNT(*) FROM pages p WHERE p.folder_id = f.id) AS page_count "
        "FROM folders f WHERE f.workspace_id = $1 ORDER BY f.parent_folder_id NULLS FIRST, f.name",
        workspace_id,
    )
    root_pages = await pool.fetch(
        "SELECT id, name, updated_at FROM pages "
        "WHERE workspace_id = $1 AND folder_id IS NULL ORDER BY name",
        workspace_id,
    )
    tables = await pool.fetch(
        "SELECT t.id, t.name, t.updated_at, "
        "(SELECT COUNT(*) FROM table_rows tr WHERE tr.table_id = t.id) AS row_count "
        "FROM tables t WHERE t.workspace_id = $1 ORDER BY t.updated_at DESC",
        workspace_id,
    )
    files = await pool.fetch(
        "SELECT id, name, COALESCE(size_bytes, 0) AS size_bytes, created_at "
        "FROM files WHERE workspace_id = $1 ORDER BY created_at DESC LIMIT 200",
        workspace_id,
    )
    return {
        "workspace": dict(ws_row),
        "folders": [dict(r) for r in folders],
        "root_pages": [dict(r) for r in root_pages],
        "tables": [dict(r) for r in tables],
        "files": [dict(r) for r in files],
    }


async def list_admin_candidates(
    *,
    query: str | None = None,
    status: str = "all",
    limit: int = 100,
) -> list[dict]:
    """List public workspaces available to curate into Discover."""
    pool = get_pool()
    where = ["EXISTS(SELECT 1 FROM object_permissions op WHERE op.object_type = 'workspace' AND op.object_id = w.id AND op.visibility = 'public')"]
    args: list = []
    idx = 1

    if query:
        where.append(
            f"(w.name ILIKE ${idx} OR w.summary ILIKE ${idx} OR w.description ILIKE ${idx})"
        )
        args.append(f"%{query}%")
        idx += 1

    if status == "curated":
        where.append("w.discoverable = true")
    elif status == "uncurated":
        where.append("w.discoverable = false")

    args.append(limit)
    sql = (
        f"{_CATALOG_SELECT} WHERE {' AND '.join(where)} "
        "ORDER BY w.discoverable DESC, w.featured DESC, w.updated_at DESC, w.id DESC "
        f"LIMIT ${idx}"
    )
    rows = await pool.fetch(sql, *args)
    return [dict(r) for r in rows]


class CatalogCurationError(ValueError):
    """Raised when a requested Discover curation state is invalid."""


async def curate_workspace(
    workspace_id: UUID,
    *,
    discoverable: bool | None = None,
    featured: bool | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
    cover_image_url: str | None = None,
) -> dict | None:
    """Update Discover catalog metadata for a workspace."""
    pool = get_pool()
    current = await pool.fetchrow(
        "SELECT w.discoverable, "
        f"{_IS_PUBLIC_EXPR} AS is_public "
        "FROM workspaces w WHERE w.id = $1",
        workspace_id,
    )
    if not current:
        return None

    target_discoverable = (
        discoverable if discoverable is not None else bool(current["discoverable"])
    )
    if target_discoverable and not current["is_public"]:
        raise CatalogCurationError("Only public workspaces can be listed in Discover")
    if featured is True and not target_discoverable:
        raise CatalogCurationError("Featured workspaces must be listed in Discover")

    sets, args, idx = [], [], 1
    for col, val in (
        ("discoverable", discoverable),
        ("featured", featured),
        ("summary", summary),
        ("tags", tags),
        ("category", category),
        ("cover_image_url", cover_image_url),
    ):
        if val is not None:
            sets.append(f"{col} = ${idx}")
            args.append(val)
            idx += 1

    if discoverable is False and featured is None:
        sets.append(f"featured = ${idx}")
        args.append(False)
        idx += 1

    if sets:
        sets.append("updated_at = now()")
        args.append(workspace_id)
        await pool.execute(
            f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ${idx}",
            *args,
        )

    row = await pool.fetchrow(f"{_CATALOG_SELECT} WHERE w.id = $1", workspace_id)
    return dict(row) if row else None


def _encode_cursor(value: datetime | int) -> str:
    raw = value.isoformat() if isinstance(value, datetime) else str(value)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(token: str) -> datetime | int | None:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        try:
            return int(raw)
        except ValueError:
            return datetime.fromisoformat(raw)
    except (ValueError, UnicodeDecodeError):
        return None
