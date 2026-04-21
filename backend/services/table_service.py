"""Table service: structured data CRUD with typed columns, JSONB rows, and optional embeddings."""

import asyncio
import hashlib
import logging
import re
import secrets
from uuid import UUID

from ..database import get_pool
from .row_validation import RowValidationError, validate_row_data

logger = logging.getLogger(__name__)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# Dedup map for in-flight embed tasks, keyed by row_id.
_embed_tasks: dict[UUID, asyncio.Task] = {}


def _schedule_row_embed(row_id: UUID, text: str, text_hash: str) -> None:
    existing = _embed_tasks.get(row_id)
    if existing is not None and not existing.done():
        existing.cancel()
    task = asyncio.create_task(_embed_row(row_id, text, text_hash))
    _embed_tasks[row_id] = task
    task.add_done_callback(lambda t, rid=row_id: _embed_tasks.pop(rid, None) if _embed_tasks.get(rid) is t else None)


# --- Table CRUD ---


async def create_table(
    workspace_id: UUID | None,
    name: str,
    description: str,
    columns: list[dict],
    created_by: UUID,
) -> dict:
    pool = get_pool()
    # Assign server-generated IDs and order to columns
    for i, col in enumerate(columns):
        if not col.get("id"):
            col["id"] = f"col_{secrets.token_hex(6)}"
        col["order"] = i
    row = await pool.fetchrow(
        "INSERT INTO tables (workspace_id, name, description, columns, created_by, updated_by) "
        "VALUES ($1, $2, $3, $4, $5, $5) "
        "RETURNING id, workspace_id, name, description, columns, views, "
        "created_by, updated_by, created_at, updated_at",
        workspace_id,
        name,
        description,
        columns,
        created_by,
    )
    result = dict(row)
    result["row_count"] = 0
    return result


async def get_table(table_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT t.id, t.workspace_id, t.name, t.description, t.columns, t.views, "
        "t.created_by, t.updated_by, t.created_at, t.updated_at, "
        "(SELECT COUNT(*) FROM table_rows tr WHERE tr.table_id = t.id) AS row_count "
        "FROM tables t WHERE t.id = $1",
        table_id,
    )
    return dict(row) if row else None


async def update_table(
    table_id: UUID,
    updated_by: UUID,
    name: str | None = None,
    description: str | None = None,
) -> dict | None:
    pool = get_pool()
    sets = ["updated_at = now()", "updated_by = $1"]
    args: list = [updated_by]
    idx = 2

    if name is not None:
        sets.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if description is not None:
        sets.append(f"description = ${idx}")
        args.append(description)
        idx += 1

    args.append(table_id)
    row = await pool.fetchrow(
        f"UPDATE tables SET {', '.join(sets)} WHERE id = ${idx} "
        "RETURNING id, workspace_id, name, description, columns, views, "
        "created_by, updated_by, created_at, updated_at",
        *args,
    )
    if not row:
        return None
    result = dict(row)
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM table_rows WHERE table_id = $1",
        table_id,
    )
    result["row_count"] = count
    return result


async def delete_table(table_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM tables WHERE id = $1", table_id)
    return result == "DELETE 1"


async def list_tables(workspace_id: UUID | None, user_id: UUID | None = None) -> list[dict]:
    pool = get_pool()
    if workspace_id is not None:
        rows = await pool.fetch(
            "SELECT t.id, t.workspace_id, t.name, t.description, t.columns, "
            "t.created_by, t.updated_by, t.created_at, t.updated_at, "
            "(SELECT COUNT(*) FROM table_rows tr WHERE tr.table_id = t.id) AS row_count "
            "FROM tables t WHERE t.workspace_id = $1 ORDER BY t.updated_at DESC",
            workspace_id,
        )
    else:
        rows = await pool.fetch(
            "SELECT t.id, t.workspace_id, t.name, t.description, t.columns, "
            "t.created_by, t.updated_by, t.created_at, t.updated_at, "
            "(SELECT COUNT(*) FROM table_rows tr WHERE tr.table_id = t.id) AS row_count "
            "FROM tables t WHERE t.workspace_id IS NULL AND t.created_by = $1 "
            "ORDER BY t.updated_at DESC",
            user_id,
        )
    return [dict(r) for r in rows]


async def list_all_user_tables(user_id: UUID) -> list[dict]:
    """All tables from workspaces user is member of + personal."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT t.id, t.workspace_id, t.name, t.description, t.columns, t.views, "
        "t.created_by, t.updated_by, t.created_at, t.updated_at, "
        "w.name AS workspace_name, "
        "(SELECT COUNT(*) FROM table_rows tr WHERE tr.table_id = t.id) AS row_count "
        "FROM tables t "
        "LEFT JOIN workspaces w ON w.id = t.workspace_id "
        "WHERE t.workspace_id IN ("
        "  SELECT workspace_id FROM workspace_members WHERE user_id = $1"
        ") OR (t.workspace_id IS NULL AND t.created_by = $1) "
        "ORDER BY t.updated_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


# --- Column Management ---


async def add_column(table_id: UUID, column: dict, updated_by: UUID) -> dict:
    pool = get_pool()
    table = await get_table(table_id)
    if not table:
        return None
    cols = table["columns"]
    col_id = f"col_{secrets.token_hex(6)}"
    new_col = {
        "id": col_id,
        "name": column["name"],
        "type": column["type"],
        "order": len(cols),
        "required": column.get("required", False),
        "default": column.get("default"),
        "options": column.get("options"),
    }
    cols.append(new_col)
    row = await pool.fetchrow(
        "UPDATE tables SET columns = $1, updated_by = $2, updated_at = now() "
        "WHERE id = $3 "
        "RETURNING id, workspace_id, name, description, columns, views, "
        "created_by, updated_by, created_at, updated_at",
        cols,
        updated_by,
        table_id,
    )
    result = dict(row)
    result["row_count"] = table["row_count"]
    return result


async def update_column(
    table_id: UUID, column_id: str, updates: dict, updated_by: UUID
) -> dict | None:
    pool = get_pool()
    table = await get_table(table_id)
    if not table:
        return None
    cols = table["columns"]
    found = False
    for col in cols:
        if col["id"] == column_id:
            for key in ("name", "type", "required", "default", "options"):
                if key in updates and updates[key] is not None:
                    col[key] = updates[key]
            found = True
            break
    if not found:
        return None
    row = await pool.fetchrow(
        "UPDATE tables SET columns = $1, updated_by = $2, updated_at = now() "
        "WHERE id = $3 "
        "RETURNING id, workspace_id, name, description, columns, views, "
        "created_by, updated_by, created_at, updated_at",
        cols,
        updated_by,
        table_id,
    )
    result = dict(row)
    result["row_count"] = table["row_count"]
    return result


async def delete_column(table_id: UUID, column_id: str, updated_by: UUID) -> dict | None:
    pool = get_pool()
    table = await get_table(table_id)
    if not table:
        return None
    cols = [c for c in table["columns"] if c["id"] != column_id]
    # Re-order
    for i, col in enumerate(cols):
        col["order"] = i
    row = await pool.fetchrow(
        "UPDATE tables SET columns = $1, updated_by = $2, updated_at = now() "
        "WHERE id = $3 "
        "RETURNING id, workspace_id, name, description, columns, views, "
        "created_by, updated_by, created_at, updated_at",
        cols,
        updated_by,
        table_id,
    )
    result = dict(row)
    result["row_count"] = table["row_count"]
    return result


async def reorder_columns(table_id: UUID, column_ids: list[str], updated_by: UUID) -> dict | None:
    pool = get_pool()
    table = await get_table(table_id)
    if not table:
        return None
    cols_by_id = {c["id"]: c for c in table["columns"]}
    reordered = []
    for i, cid in enumerate(column_ids):
        if cid not in cols_by_id:
            return None
        col = cols_by_id[cid]
        col["order"] = i
        reordered.append(col)
    row = await pool.fetchrow(
        "UPDATE tables SET columns = $1, updated_by = $2, updated_at = now() "
        "WHERE id = $3 "
        "RETURNING id, workspace_id, name, description, columns, views, "
        "created_by, updated_by, created_at, updated_at",
        reordered,
        updated_by,
        table_id,
    )
    result = dict(row)
    result["row_count"] = table["row_count"]
    return result


# --- Row CRUD ---


async def _get_columns(table_id: UUID) -> list[dict]:
    pool = get_pool()
    columns = await pool.fetchval("SELECT columns FROM tables WHERE id = $1", table_id)
    if columns is None:
        raise ValueError(f"table {table_id} not found")
    return columns


async def _get_row_table_id(row_id: UUID) -> UUID | None:
    pool = get_pool()
    return await pool.fetchval("SELECT table_id FROM table_rows WHERE id = $1", row_id)


def _validate_batch(columns: list[dict], rows: list[dict], *, partial: bool) -> list[dict]:
    """Validate every row before we write any. Collects errors per-row."""
    errors: list[str] = []
    validated: list[dict] = []
    for i, row in enumerate(rows):
        try:
            validated.append(validate_row_data(columns, row, partial=partial))
        except RowValidationError as exc:
            for err in exc.errors:
                errors.append(f"row {i}: {err}")
    if errors:
        raise RowValidationError(errors)
    return validated


async def create_row(table_id: UUID, data: dict, created_by: UUID) -> dict:
    pool = get_pool()
    columns = await _get_columns(table_id)
    validated = validate_row_data(columns, data)
    row = await pool.fetchrow(
        "INSERT INTO table_rows (table_id, data, row_order, created_by, updated_by) "
        "VALUES ($1, $2, "
        "  COALESCE((SELECT MAX(row_order) FROM table_rows WHERE table_id = $1), -1) + 1, "
        "  $3, $3) "
        "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
        table_id,
        validated,
        created_by,
    )
    result = dict(row)
    asyncio.create_task(maybe_embed_row(table_id, result["id"], validated))
    return result


async def create_rows_batch(table_id: UUID, rows_data: list[dict], created_by: UUID) -> list[dict]:
    columns = await _get_columns(table_id)
    validated_rows = _validate_batch(columns, rows_data, partial=False)
    pool = get_pool()
    results = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock the parent table row to prevent concurrent row_order conflicts
            await conn.fetchval(
                "SELECT id FROM tables WHERE id = $1 FOR UPDATE",
                table_id,
            )
            max_order = await conn.fetchval(
                "SELECT COALESCE(MAX(row_order), -1) FROM table_rows WHERE table_id = $1",
                table_id,
            )
            for i, data in enumerate(validated_rows):
                row = await conn.fetchrow(
                    "INSERT INTO table_rows (table_id, data, row_order, created_by, updated_by) "
                    "VALUES ($1, $2, $3, $4, $4) "
                    "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
                    table_id,
                    data,
                    max_order + 1 + i,
                    created_by,
                )
                results.append(dict(row))
    return results


async def get_row(row_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, table_id, data, row_order, created_by, updated_by, created_at, updated_at "
        "FROM table_rows WHERE id = $1",
        row_id,
    )
    return dict(row) if row else None


async def update_row(
    row_id: UUID, data: dict, updated_by: UUID, table_id: UUID | None = None
) -> dict | None:
    """Partial merge update — only specified keys are changed."""
    pool = get_pool()
    effective_table_id = table_id or await _get_row_table_id(row_id)
    if effective_table_id is None:
        return None
    columns = await _get_columns(effective_table_id)
    validated = validate_row_data(columns, data, partial=True)
    if table_id is not None:
        row = await pool.fetchrow(
            "UPDATE table_rows SET data = data || $1, updated_by = $2, updated_at = now() "
            "WHERE id = $3 AND table_id = $4 "
            "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
            validated,
            updated_by,
            row_id,
            table_id,
        )
    else:
        row = await pool.fetchrow(
            "UPDATE table_rows SET data = data || $1, updated_by = $2, updated_at = now() "
            "WHERE id = $3 "
            "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
            validated,
            updated_by,
            row_id,
        )
    if not row:
        return None
    result = dict(row)
    asyncio.create_task(maybe_embed_row(result["table_id"], result["id"], result["data"]))
    return result


async def delete_row(row_id: UUID, table_id: UUID | None = None) -> bool:
    pool = get_pool()
    if table_id is not None:
        result = await pool.execute(
            "DELETE FROM table_rows WHERE id = $1 AND table_id = $2",
            row_id,
            table_id,
        )
    else:
        result = await pool.execute("DELETE FROM table_rows WHERE id = $1", row_id)
    return result == "DELETE 1"


async def update_rows_batch(table_id: UUID, updates: list[dict], updated_by: UUID) -> list[dict]:
    """Batch partial merge update. Each item: {row_id: UUID, data: dict}."""
    if not updates:
        return []
    columns = await _get_columns(table_id)
    validated_payloads = _validate_batch(columns, [u["data"] for u in updates], partial=True)
    pool = get_pool()
    results = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for item, validated in zip(updates, validated_payloads):
                row = await conn.fetchrow(
                    "UPDATE table_rows SET data = data || $1, updated_by = $2, updated_at = now() "
                    "WHERE id = $3 AND table_id = $4 "
                    "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
                    validated,
                    updated_by,
                    item["row_id"],
                    table_id,
                )
                if row:
                    results.append(dict(row))
    return results


async def delete_rows_batch(table_id: UUID, row_ids: list[UUID]) -> int:
    if not row_ids:
        return 0
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM table_rows WHERE table_id = $1 AND id = ANY($2)",
        table_id,
        row_ids,
    )
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


# --- Row Querying ---


_FILTER_OPS = {
    "eq": "=",
    "neq": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


_COL_ID_RE = re.compile(r"^col_[a-f0-9]{12}$")


async def list_rows(
    table_id: UUID,
    filters: list[dict] | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List rows with optional filtering and sorting. Returns (rows, total_count)."""
    pool = get_pool()

    # Fetch table schema to validate column IDs against injection
    table = await get_table(table_id)
    if not table:
        return [], 0
    valid_col_ids = {c["id"] for c in table["columns"]}

    where_clauses = ["table_id = $1"]
    args: list = [table_id]
    idx = 2

    if filters:
        for f in filters:
            col_id = f.get("column_id", "")
            op = f.get("op", "eq")
            value = f.get("value")

            # Validate column ID against schema to prevent injection
            if col_id not in valid_col_ids:
                continue

            if op == "is_empty":
                where_clauses.append(f"(data->>'{col_id}' IS NULL OR data->>'{col_id}' = '')")
                continue
            if op == "is_not_empty":
                where_clauses.append(f"(data->>'{col_id}' IS NOT NULL AND data->>'{col_id}' != '')")
                continue
            if op == "contains":
                where_clauses.append(f"data->>'{col_id}' ILIKE ${idx}")
                args.append(f"%{value}%")
                idx += 1
                continue

            sql_op = _FILTER_OPS.get(op)
            if not sql_op:
                continue

            # Numeric comparison for number values
            if isinstance(value, (int, float)):
                where_clauses.append(f"(data->>'{col_id}')::numeric {sql_op} ${idx}")
            else:
                where_clauses.append(f"data->>'{col_id}' {sql_op} ${idx}")
            args.append(str(value) if not isinstance(value, str) else value)
            idx += 1

    where = " AND ".join(where_clauses)

    # Count
    total = await pool.fetchval(f"SELECT COUNT(*) FROM table_rows WHERE {where}", *args)

    # Sort — validate sort_by against schema
    order = "row_order ASC"
    if sort_by and sort_by in valid_col_ids:
        direction = "DESC" if sort_order == "desc" else "ASC"
        order = f"data->>'{sort_by}' {direction}, row_order ASC"

    # Fetch
    rows = await pool.fetch(
        f"SELECT id, table_id, data, row_order, created_by, updated_by, created_at, updated_at "
        f"FROM table_rows WHERE {where} ORDER BY {order} LIMIT ${idx} OFFSET ${idx + 1}",
        *args,
        limit,
        offset,
    )
    return [dict(r) for r in rows], total


# --- View Management ---


async def save_view(table_id: UUID, view: dict, updated_by: UUID) -> dict | None:
    """Add or update a saved view. view: {id?, name, filters, sort_by, sort_order, visible_columns}."""
    pool = get_pool()
    table = await get_table(table_id)
    if not table:
        return None
    views = table.get("views", [])
    view_id = view.get("id") or f"view_{secrets.token_hex(4)}"
    view["id"] = view_id
    # Replace existing or append
    views = [v for v in views if v.get("id") != view_id]
    views.append(view)
    row = await pool.fetchrow(
        "UPDATE tables SET views = $1, updated_by = $2, updated_at = now() "
        "WHERE id = $3 "
        "RETURNING id, workspace_id, name, description, columns, views, "
        "created_by, updated_by, created_at, updated_at",
        views,
        updated_by,
        table_id,
    )
    result = dict(row)
    result["row_count"] = table["row_count"]
    return result


async def delete_view(table_id: UUID, view_id: str, updated_by: UUID) -> dict | None:
    pool = get_pool()
    table = await get_table(table_id)
    if not table:
        return None
    views = [v for v in table.get("views", []) if v.get("id") != view_id]
    row = await pool.fetchrow(
        "UPDATE tables SET views = $1, updated_by = $2, updated_at = now() "
        "WHERE id = $3 "
        "RETURNING id, workspace_id, name, description, columns, views, "
        "created_by, updated_by, created_at, updated_at",
        views,
        updated_by,
        table_id,
    )
    result = dict(row)
    result["row_count"] = table["row_count"]
    return result


async def count_rows(table_id: UUID, filters: list[dict] | None = None) -> int:
    """Count rows matching optional filters without fetching data."""
    if not filters:
        pool = get_pool()
        return await pool.fetchval(
            "SELECT COUNT(*) FROM table_rows WHERE table_id = $1",
            table_id,
        )
    # Reuse list_rows logic with limit=0 to get count
    _, total = await list_rows(table_id, filters=filters, limit=0, offset=0)
    return total


async def export_rows_all(
    table_id: UUID,
    filters: list[dict] | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> list[dict]:
    """Fetch ALL rows for export (no limit). Use for CSV export."""
    rows, _ = await list_rows(
        table_id,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=2_000_000,
        offset=0,
    )
    return rows


async def search_rows(
    table_id: UUID,
    query: str,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Search across all text/email/url columns using ILIKE."""
    pool = get_pool()
    table = await get_table(table_id)
    if not table:
        return [], 0
    # Build OR clauses for all text-like columns
    text_cols = [c for c in table["columns"] if c["type"] in ("text", "email", "url", "select")]
    if not text_cols:
        return [], 0
    or_clauses = " OR ".join(f"data->>'{c['id']}' ILIKE $2" for c in text_cols)
    where = f"table_id = $1 AND ({or_clauses})"
    like_val = f"%{query}%"
    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM table_rows WHERE {where}", table_id, like_val
    )
    rows = await pool.fetch(
        f"SELECT id, table_id, data, row_order, created_by, updated_by, created_at, updated_at "
        f"FROM table_rows WHERE {where} ORDER BY row_order ASC LIMIT $3 OFFSET $4",
        table_id,
        like_val,
        limit,
        offset,
    )
    return [dict(r) for r in rows], total


async def summarize_rows(
    table_id: UUID,
    filters: list[dict] | None = None,
) -> dict:
    """Compute aggregates per column: count, sum, avg, min, max for numbers; count for all."""
    pool = get_pool()
    table = await get_table(table_id)
    if not table:
        return {}
    # Get total count (reuse existing logic)
    total = await count_rows(table_id, filters=filters)
    summaries: dict = {"total_rows": total, "columns": {}}
    # For each number column, compute aggregates
    num_cols = [c for c in table["columns"] if c["type"] == "number"]
    if num_cols and total > 0:
        # Build a single query that computes all aggregates
        agg_parts = []
        for c in num_cols:
            cid = c["id"]
            agg_parts.append(
                f"COUNT(CASE WHEN data->>'{cid}' IS NOT NULL AND data->>'{cid}' != '' THEN 1 END) AS \"{cid}_count\", "
                f"SUM((data->>'{cid}')::numeric) AS \"{cid}_sum\", "
                f"AVG((data->>'{cid}')::numeric) AS \"{cid}_avg\", "
                f"MIN((data->>'{cid}')::numeric) AS \"{cid}_min\", "
                f"MAX((data->>'{cid}')::numeric) AS \"{cid}_max\""
            )
        select_clause = ", ".join(agg_parts)
        # Build WHERE from filters
        where_clauses = ["table_id = $1"]
        args: list = [table_id]
        idx = 2
        valid_col_ids = {c["id"] for c in table["columns"]}
        if filters:
            for f in filters:
                col_id = f.get("column_id", "")
                op = f.get("op", "eq")
                value = f.get("value")
                if col_id not in valid_col_ids:
                    continue
                if op == "contains":
                    where_clauses.append(f"data->>'{col_id}' ILIKE ${idx}")
                    args.append(f"%{value}%")
                    idx += 1
                elif op in _FILTER_OPS:
                    sql_op = _FILTER_OPS[op]
                    if isinstance(value, (int, float)):
                        where_clauses.append(f"(data->>'{col_id}')::numeric {sql_op} ${idx}")
                    else:
                        where_clauses.append(f"data->>'{col_id}' {sql_op} ${idx}")
                    args.append(str(value) if not isinstance(value, str) else value)
                    idx += 1
        where = " AND ".join(where_clauses)
        row = await pool.fetchrow(f"SELECT {select_clause} FROM table_rows WHERE {where}", *args)
        if row:
            for c in num_cols:
                cid = c["id"]
                summaries["columns"][cid] = {
                    "name": c["name"],
                    "filled": row[f"{cid}_count"],
                    "sum": float(row[f"{cid}_sum"]) if row[f"{cid}_sum"] is not None else None,
                    "avg": (
                        round(float(row[f"{cid}_avg"]), 2)
                        if row[f"{cid}_avg"] is not None
                        else None
                    ),
                    "min": float(row[f"{cid}_min"]) if row[f"{cid}_min"] is not None else None,
                    "max": float(row[f"{cid}_max"]) if row[f"{cid}_max"] is not None else None,
                }
    # For non-number columns, just count non-empty values
    for c in table["columns"]:
        if c["id"] not in summaries["columns"]:
            cid = c["id"]
            filled = await pool.fetchval(
                f"SELECT COUNT(*) FROM table_rows WHERE table_id = $1 AND data->>'{cid}' IS NOT NULL AND data->>'{cid}' != ''",
                table_id,
            )
            summaries["columns"][cid] = {"name": c["name"], "filled": filled}
    return summaries


async def duplicate_row(row_id: UUID, table_id: UUID, created_by: UUID) -> dict | None:
    """Duplicate a row — copy data with new ID and row_order."""
    source = await get_row(row_id)
    if not source or source.get("table_id") != table_id:
        return None
    return await create_row(table_id, source["data"], created_by)


# --- Row Embeddings ---


async def get_embedding_config(table_id: UUID) -> dict | None:
    """Get embedding config for a table. Returns None if not configured."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT embedding_config FROM tables WHERE id = $1",
        table_id,
    )
    return row["embedding_config"] if row and row["embedding_config"] else None


async def set_embedding_config(table_id: UUID, config: dict, updated_by: UUID) -> dict:
    """Set embedding configuration for a table.

    Config: {"enabled": true, "columns": ["col_id1", "col_id2"]}
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE tables SET embedding_config = $1, updated_by = $2, updated_at = now() "
        "WHERE id = $3 "
        "RETURNING id, workspace_id, name, description, columns, views, embedding_config, "
        "created_by, updated_by, created_at, updated_at",
        config,
        updated_by,
        table_id,
    )
    return dict(row) if row else None


def _build_embedding_text(row_data: dict, config: dict, columns: list[dict]) -> str:
    """Build text to embed from row data based on embedding config."""
    col_ids = config.get("columns", [])
    col_map = {c["id"]: c["name"] for c in columns}

    parts = []
    for cid in col_ids:
        val = row_data.get(cid, "")
        if val:
            col_name = col_map.get(cid, cid)
            parts.append(f"{col_name}: {val}")

    return "\n".join(parts) if parts else str(row_data)


async def _embed_row(row_id: UUID, text: str, text_hash: str) -> None:
    """Fire-and-forget: embed row text and store in database.

    On failure, flips `embed_stale=true` so the reconciler retries later.
    """
    from . import embeddings as embedding_service

    if not embedding_service.is_configured():
        return
    embedding = await embedding_service.embed_text(text)
    pool = get_pool()
    if embedding is None:
        await pool.execute(
            "UPDATE table_rows SET content_hash = $1, embed_stale = TRUE WHERE id = $2",
            text_hash,
            row_id,
        )
        return
    await pool.execute(
        "UPDATE table_rows SET embedding = $1, content_hash = $2, embed_stale = FALSE WHERE id = $3",
        embedding,
        text_hash,
        row_id,
    )


async def _embed_rows_batch(row_ids: list[UUID], texts: list[str]) -> None:
    """Fire-and-forget: batch embed rows."""
    from . import embeddings as embedding_service

    if not embedding_service.is_configured() or not texts:
        return
    embeddings = await embedding_service.embed_batch(texts)
    pool = get_pool()
    if not embeddings:
        # Mark all stale so the reconciler will retry.
        hashes = [_text_hash(t) for t in texts]
        await pool.executemany(
            "UPDATE table_rows SET content_hash = $1, embed_stale = TRUE WHERE id = $2",
            list(zip(hashes, row_ids)),
        )
        return
    hashes = [_text_hash(t) for t in texts]
    await pool.executemany(
        "UPDATE table_rows SET embedding = $1, content_hash = $2, embed_stale = FALSE WHERE id = $3",
        [(emb, h, rid) for rid, emb, h in zip(row_ids, embeddings, hashes)],
    )


async def maybe_embed_row(table_id: UUID, row_id: UUID, row_data: dict) -> None:
    """Check if table has embedding config and embed the row if content changed."""
    config = await get_embedding_config(table_id)
    if not config or not config.get("enabled"):
        return
    pool = get_pool()
    tbl = await pool.fetchrow("SELECT columns FROM tables WHERE id = $1", table_id)
    if not tbl:
        return
    text = _build_embedding_text(row_data, config, tbl["columns"])
    new_hash = _text_hash(text)
    stored_hash = await pool.fetchval(
        "SELECT content_hash FROM table_rows WHERE id = $1",
        row_id,
    )
    if stored_hash == new_hash:
        return
    _schedule_row_embed(row_id, text, new_hash)


async def search_rows_vector(table_id: UUID, query_embedding, limit: int = 20) -> list[dict]:
    """Semantic search on table rows using pgvector."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, table_id, data, row_order, "
        "1 - (embedding <=> $2) AS similarity "
        "FROM table_rows WHERE table_id = $1 AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2 LIMIT $3",
        table_id,
        query_embedding,
        limit,
    )
    return [dict(r) for r in rows]


async def backfill_embeddings(table_id: UUID) -> dict:
    """Re-embed all rows in a table. Returns {embedded, total}."""
    config = await get_embedding_config(table_id)
    if not config or not config.get("enabled"):
        return {"embedded": 0, "total": 0, "error": "embedding not configured"}

    pool = get_pool()
    tbl = await pool.fetchrow("SELECT columns FROM tables WHERE id = $1", table_id)
    if not tbl:
        return {"embedded": 0, "total": 0, "error": "table not found"}

    rows = await pool.fetch(
        "SELECT id, data FROM table_rows WHERE table_id = $1",
        table_id,
    )

    texts = []
    ids = []
    for r in rows:
        text = _build_embedding_text(r["data"], config, tbl["columns"])
        texts.append(text)
        ids.append(r["id"])

    if texts:
        asyncio.create_task(_embed_rows_batch(ids, texts))

    return {"embedded": len(texts), "total": len(rows)}
