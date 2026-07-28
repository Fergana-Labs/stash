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
from . import table_service

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
    columns = await get_pool().fetchval("SELECT columns FROM tables WHERE id = $1", table_id)
    if columns is None:
        raise ValueError(f"Table {table_id} does not exist")
    return columns


def _cell(row_data: dict, col_id: str | None) -> object:
    return row_data.get(col_id) if col_id else None


def _labels(row_data: dict, col_id: str | None) -> list[str]:
    value = _cell(row_data, col_id)
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _url_key_sql(link_col: str | None) -> str:
    """Postgres equivalent of normalize_url for duplicate ranking.

    Column ids come from the table schema, not the request. Query values stay
    bound parameters.
    """
    if link_col is None:
        return "NULL::text"
    return f"""
        (
            SELECT
                lower(regexp_replace(parts.authority, '^www\\.', '', 'i'))
                || COALESCE(NULLIF(rtrim(parts.path, '/'), ''), '/')
                || CASE WHEN query.meaningful = '' THEN '' ELSE '?' || query.meaningful END
            FROM (
                SELECT
                    split_part(split_part(clean.without_scheme, '/', 1), '?', 1) AS authority,
                    CASE
                        WHEN strpos(clean.without_scheme, '/') = 0 THEN '/'
                        ELSE split_part(
                            substring(clean.without_scheme FROM strpos(clean.without_scheme, '/')),
                            '?',
                            1
                        )
                    END AS path,
                    split_part(clean.without_scheme, '?', 2) AS query_string
                FROM (
                    SELECT regexp_replace(
                        split_part(trim(data->>'{link_col}'), '#', 1),
                        '^[a-z][a-z0-9+.-]*://',
                        '',
                        'i'
                    ) AS without_scheme
                ) clean
            ) parts
            CROSS JOIN LATERAL (
                SELECT COALESCE(string_agg(piece, '&' ORDER BY piece), '') AS meaningful
                FROM regexp_split_to_table(parts.query_string, '&') piece
                WHERE piece != ''
                  AND split_part(piece, '=', 1)
                      !~* '^(utm_[a-z]+|fbclid|gclid|mc_[a-z]+|ref|ref_src|source|igshid|si)$'
            ) query
        )
    """


async def _query_parts(
    table_id: UUID,
    slots: dict,
    view: dict | None,
    *,
    include_url_key: bool,
) -> tuple[str, str, list]:
    columns = await _columns(table_id)
    valid_col_ids = {column["id"] for column in columns}
    for slot, col_id in slots.items():
        if col_id not in valid_col_ids:
            raise ValueError(f"Manifest slot {slot!r} points to a missing column")

    args: list = [table_id]
    clauses = ["table_id = $1"]
    if view:
        clauses.extend(
            table_service.row_filter_clauses(view.get("filters", []), valid_col_ids, args)
        )

    order = "row_order DESC"
    sort_by = view.get("sort_by") if view else None
    if sort_by in valid_col_ids:
        direction = "DESC" if view.get("sort_order") == "desc" else "ASC"
        order = f"data->>'{sort_by}' {direction}, row_order ASC"

    fields = "id, data, row_order"
    if include_url_key:
        fields += f", {_url_key_sql(slots.get('link'))} AS normalized_url"
    base_sql = f"SELECT {fields} FROM table_rows WHERE " + " AND ".join(clauses)
    return base_sql, order, args


async def query_rows(
    table_id: UUID,
    slots: dict,
    *,
    q: str = "",
    topic: str | None = None,
    filter_: str | None = None,
    view: dict | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict:
    """Filter, count, and page in Postgres without loading the table in Python."""
    needs_duplicate_rank = filter_ == FILTER_DUPLICATES
    base_sql, order, args = await _query_parts(
        table_id,
        slots,
        view,
        include_url_key=needs_duplicate_rank,
    )
    label_col, status_col = slots.get("labels"), slots.get("status")

    clauses = []
    if filter_ == FILTER_DUPLICATES:
        clauses.append("duplicate_rank > 1")
    elif filter_ == FILTER_UNTAGGED:
        clauses.append(f"COALESCE(jsonb_array_length(data->'{label_col}'), 0) = 0")
    elif filter_ == FILTER_BROKEN:
        args.append(STATUS_BROKEN)
        clauses.append(f"data->>'{status_col}' = ${len(args)}")

    if topic:
        args.append(topic)
        clauses.append(f"data->'{label_col}' ? ${len(args)}")

    needle = q.strip().lower()
    if needle:
        args.append(f"%{needle}%")
        clauses.append(
            "EXISTS (SELECT 1 FROM jsonb_each(data) cell "
            f"WHERE cell.value::text ILIKE ${len(args)})"
        )

    where = " AND ".join(clauses) if clauses else "TRUE"
    ctes = f"WITH base AS ({base_sql}), "
    source = "base"
    if needs_duplicate_rank:
        ctes += (
            "ranked AS ("
            "  SELECT *, CASE "
            "    WHEN normalized_url IS NULL OR normalized_url = '' THEN NULL "
            "    ELSE row_number() OVER (PARTITION BY normalized_url ORDER BY row_order ASC) "
            "  END AS duplicate_rank "
            "  FROM base"
            "), "
        )
        source = "ranked"
    ctes += f"filtered AS (SELECT * FROM {source} WHERE {where}) "
    total = await get_pool().fetchval(ctes + "SELECT count(*) FROM filtered", *args)
    args.extend([limit, offset])
    page = await get_pool().fetch(
        ctes + f"SELECT id, data FROM filtered ORDER BY {order} "
        f"LIMIT ${len(args) - 1} OFFSET ${len(args)}",
        *args,
    )
    return {
        "rows": [{"id": str(row["id"]), "data": row["data"]} for row in page],
        "total": total,
        "has_more": offset + len(page) < total,
    }


async def facets(table_id: UUID, slots: dict) -> dict:
    """Count all filter chips in Postgres without transferring every row."""
    base_sql, _, args = await _query_parts(
        table_id,
        slots,
        None,
        include_url_key=True,
    )
    label_col, status_col = slots.get("labels"), slots.get("status")
    args.append(STATUS_BROKEN)
    row = await get_pool().fetchrow(
        f"""
        WITH base AS ({base_sql}),
        ranked AS (
            SELECT *, CASE
                WHEN normalized_url IS NULL OR normalized_url = '' THEN NULL
                ELSE row_number() OVER (
                    PARTITION BY normalized_url ORDER BY row_order ASC
                )
            END AS duplicate_rank
            FROM base
        ),
        topic_counts AS (
            SELECT label, count(*) AS count
            FROM ranked
            CROSS JOIN LATERAL jsonb_array_elements_text(data->'{label_col}') label
            GROUP BY label
            ORDER BY count DESC, label ASC
        )
        SELECT
            (SELECT count(*) FROM ranked) AS total,
            (SELECT count(*) FROM ranked
             WHERE COALESCE(jsonb_array_length(data->'{label_col}'), 0) = 0) AS untagged,
            (SELECT count(*) FROM ranked WHERE duplicate_rank > 1) AS duplicates,
            (SELECT count(*) FROM ranked
             WHERE data->>'{status_col}' = ${len(args)}) AS broken,
            (SELECT COALESCE(
                jsonb_agg(jsonb_build_object('label', label, 'count', count)),
                '[]'::jsonb
             ) FROM topic_counts) AS topics
        """,
        *args,
    )
    return {
        "total": row["total"],
        "topics": row["topics"],
        "untagged": row["untagged"],
        "duplicates": row["duplicates"],
        "broken": row["broken"],
    }


# --- Mutations ---------------------------------------------------------------


async def set_topics(table_id: UUID, row_id: UUID, label_col: str, topics: list[str]) -> bool:
    """Replace a row's labels. Manual edits are authoritative: the enrichment
    hash is left alone so a later sweep won't overwrite what the user chose."""
    result = await get_pool().execute(
        "UPDATE table_rows SET data = jsonb_set(data, ARRAY[$1], $2::jsonb), "
        "  embed_stale = TRUE, enrich_stale = FALSE, updated_at = now() "
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
