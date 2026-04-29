"""Public catalog of Stashes (workspaces with is_public=true)."""

import base64
from datetime import datetime
from uuid import UUID

from ..database import get_pool

_CATALOG_SELECT = """
SELECT
    w.id, w.name, w.summary, w.description, w.is_public,
    w.tags, w.category, w.featured, w.cover_image_url,
    w.creator_id, u.name AS creator_name, u.display_name AS creator_display_name,
    w.fork_count, w.forked_from_workspace_id, w.created_at, w.updated_at,
    (SELECT COUNT(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) AS member_count,
    (SELECT COUNT(*) FROM notebooks nb WHERE nb.workspace_id = w.id) AS notebook_count,
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
    where = ["w.is_public = true"]
    args: list = []
    idx = 1

    if query:
        where.append(f"(w.name ILIKE ${idx} OR w.summary ILIKE ${idx} OR w.description ILIKE ${idx})")
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
        f"{_CATALOG_SELECT} WHERE w.is_public = true AND w.featured = true "
        "ORDER BY w.updated_at DESC LIMIT 12"
    )
    return [dict(r) for r in rows]


async def get_public_detail(workspace_id: UUID) -> dict | None:
    pool = get_pool()
    ws_row = await pool.fetchrow(
        f"{_CATALOG_SELECT} WHERE w.id = $1 AND w.is_public = true",
        workspace_id,
    )
    if not ws_row:
        return None

    notebooks = await pool.fetch(
        "SELECT nb.id, nb.name, nb.description, nb.updated_at, "
        "(SELECT COUNT(*) FROM notebook_pages p WHERE p.notebook_id = nb.id) AS page_count "
        "FROM notebooks nb WHERE nb.workspace_id = $1 ORDER BY nb.updated_at DESC",
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
        "notebooks": [dict(r) for r in notebooks],
        "tables": [dict(r) for r in tables],
        "files": [dict(r) for r in files],
    }


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
