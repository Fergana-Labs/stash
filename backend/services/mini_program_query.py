"""Reads, filters and bulk edits for mini program tables.

The generic tables API can page and sort, but an app view needs three things
it can't express: filtering on a multiselect cell (topics are a JSON array),
counting facets across the *whole* table rather than the loaded page, and the
derived filters a bookmark manager lives on — duplicates, untagged, broken.

Raindrop's model is the one worth copying here: those aren't separate screens,
they're filters over the same list with a count next to each. So none of them
gets its own storage. Duplicates and untagged are computed at query time;
broken is a value in the Status column, written by the link checker.

Everything is scoped by table id, and the router resolves that from the
caller's own slug, so a row id from another user's table is unreachable.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from ..database import get_pool

# Filters that don't come from a cell value.
FILTER_DUPLICATES = "duplicates"
FILTER_UNTAGGED = "untagged"
FILTER_BROKEN = "broken"

STATUS_BROKEN = "Broken"

# Query params that identify a campaign rather than a document. Raindrop
# normalises these away so the same article shared from two places counts once.
_TRACKING_PARAMS = re.compile(
    r"^(utm_[a-z]+|fbclid|gclid|mc_[a-z]+|ref|ref_src|source|igshid|si)$", re.I
)


def normalize_url(url: str) -> str:
    """Collapse the cosmetic differences between two URLs for the same page:
    scheme, a leading www., a trailing slash, tracking params, and case in the
    host. Deliberately conservative — it never drops a meaningful query param,
    because merging two genuinely different pages is worse than missing a dup.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    query = "&".join(
        sorted(
            piece
            for piece in parts.query.split("&")
            if piece and not _TRACKING_PARAMS.match(piece.split("=", 1)[0])
        )
    )
    return urlunsplit(("", host, path, query, ""))


async def _columns(table_id: UUID) -> list[dict]:
    return await get_pool().fetchval("SELECT columns FROM tables WHERE id = $1", table_id) or []


def _cell(row_data: dict, col_id: str | None) -> object:
    return row_data.get(col_id) if col_id else None


def _labels(row_data: dict, col_id: str | None) -> list[str]:
    value = _cell(row_data, col_id)
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


async def _all_rows(table_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, data, row_order FROM table_rows WHERE table_id = $1 ORDER BY row_order DESC",
        table_id,
    )
    return [dict(r) for r in rows]


def _duplicate_ids(rows: list[dict], link_col: str | None) -> set:
    """Row ids that share a normalized URL with an earlier row. The first save
    of a URL is not a duplicate — only the repeats are, so 'delete duplicates'
    leaves one copy behind."""
    if not link_col:
        return set()
    seen: dict[str, object] = {}
    dupes = set()
    # Oldest first, so the original is the keeper.
    for row in sorted(rows, key=lambda r: r["row_order"]):
        key = normalize_url(str(_cell(row["data"], link_col) or ""))
        if not key:
            continue
        if key in seen:
            dupes.add(row["id"])
        else:
            seen[key] = row["id"]
    return dupes


def _matches_query(row: dict, q: str) -> bool:
    if not q:
        return True
    haystack = " ".join(
        str(" ".join(map(str, v)) if isinstance(v, list) else v)
        for v in row["data"].values()
        if v is not None
    ).lower()
    return q in haystack


async def query_rows(
    table_id: UUID,
    slots: dict,
    *,
    q: str = "",
    topic: str | None = None,
    filter_: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict:
    """Filtered, paged rows plus the total the filter matches.

    Filtering happens over the whole table rather than a loaded page — that is
    the entire point of moving it server-side. A library of 10k bookmarks
    showed 100 of them when the client did this.
    """
    rows = await _all_rows(table_id)
    label_col, link_col, status_col = slots.get("labels"), slots.get("link"), slots.get("status")

    if filter_ == FILTER_DUPLICATES:
        dupes = _duplicate_ids(rows, link_col)
        rows = [r for r in rows if r["id"] in dupes]
    elif filter_ == FILTER_UNTAGGED:
        rows = [r for r in rows if not _labels(r["data"], label_col)]
    elif filter_ == FILTER_BROKEN:
        rows = [r for r in rows if _cell(r["data"], status_col) == STATUS_BROKEN]

    if topic:
        rows = [r for r in rows if topic in _labels(r["data"], label_col)]

    needle = q.strip().lower()
    if needle:
        rows = [r for r in rows if _matches_query(r, needle)]

    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "rows": [{"id": str(r["id"]), "data": r["data"]} for r in page],
        "total": total,
        "has_more": offset + len(page) < total,
    }


async def facets(table_id: UUID, slots: dict) -> dict:
    """Counts for every filter chip, over the whole table.

    Computed together in one pass because they all read the same rows, and
    because a chip whose count is stale is worse than no chip.
    """
    rows = await _all_rows(table_id)
    label_col, link_col, status_col = slots.get("labels"), slots.get("link"), slots.get("status")

    counts: dict[str, int] = {}
    untagged = 0
    for row in rows:
        labels = _labels(row["data"], label_col)
        if not labels:
            untagged += 1
        for label in labels:
            counts[label] = counts.get(label, 0) + 1

    return {
        "total": len(rows),
        "topics": [
            {"label": label, "count": count}
            for label, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "untagged": untagged,
        "duplicates": len(_duplicate_ids(rows, link_col)),
        "broken": sum(1 for r in rows if _cell(r["data"], status_col) == STATUS_BROKEN),
    }


# --- Mutations ---------------------------------------------------------------


async def set_topics(table_id: UUID, row_id: UUID, label_col: str, topics: list[str]) -> bool:
    """Replace a row's labels. Manual edits are authoritative: the enrichment
    hash is left alone so a later sweep won't overwrite what the user chose."""
    result = await get_pool().execute(
        "UPDATE table_rows SET data = jsonb_set(data, ARRAY[$1], $2::jsonb), "
        "  embed_stale = TRUE, updated_at = now() "
        "WHERE id = $3 AND table_id = $4",
        label_col,
        topics,
        row_id,
        table_id,
    )
    return result.endswith(" 1")


async def bulk_add_topics(table_id: UUID, row_ids: list[UUID], label_col: str, add: list[str]):
    """Union `add` into each row's labels. Union rather than replace so a bulk
    tag never silently discards labels the rows already carry."""
    rows = await get_pool().fetch(
        "SELECT id, data FROM table_rows WHERE table_id = $1 AND id = ANY($2)",
        table_id,
        row_ids,
    )
    updated = 0
    for row in rows:
        existing = _labels(row["data"], label_col)
        lowered = {label.lower() for label in existing}
        merged = existing + [label for label in add if label.lower() not in lowered]
        if merged != existing:
            await set_topics(table_id, row["id"], label_col, merged)
            updated += 1
    return updated


async def bulk_remove_topic(table_id: UUID, row_ids: list[UUID], label_col: str, remove: str):
    rows = await get_pool().fetch(
        "SELECT id, data FROM table_rows WHERE table_id = $1 AND id = ANY($2)",
        table_id,
        row_ids,
    )
    updated = 0
    for row in rows:
        existing = _labels(row["data"], label_col)
        kept = [label for label in existing if label.lower() != remove.lower()]
        if kept != existing:
            await set_topics(table_id, row["id"], label_col, kept)
            updated += 1
    return updated


async def bulk_delete(table_id: UUID, row_ids: list[UUID]) -> int:
    result = await get_pool().execute(
        "DELETE FROM table_rows WHERE table_id = $1 AND id = ANY($2)", table_id, row_ids
    )
    return int(result.rsplit(" ", 1)[-1])
