"""Table service: structured data CRUD with typed columns and JSONB rows."""

import re
import secrets
from uuid import UUID

from ..database import get_pool


# --- Table CRUD ---


async def create_table(
    workspace_id: UUID | None, name: str, description: str,
    columns: list[dict], created_by: UUID,
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
        "RETURNING id, workspace_id, name, description, columns, "
        "created_by, updated_by, created_at, updated_at",
        workspace_id, name, description, columns, created_by,
    )
    result = dict(row)
    result["row_count"] = 0
    return result


async def get_table(table_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT t.id, t.workspace_id, t.name, t.description, t.columns, "
        "t.created_by, t.updated_by, t.created_at, t.updated_at, "
        "(SELECT COUNT(*) FROM table_rows tr WHERE tr.table_id = t.id) AS row_count "
        "FROM tables t WHERE t.id = $1",
        table_id,
    )
    return dict(row) if row else None


async def update_table(
    table_id: UUID, updated_by: UUID,
    name: str | None = None, description: str | None = None,
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
        "RETURNING id, workspace_id, name, description, columns, "
        "created_by, updated_by, created_at, updated_at",
        *args,
    )
    if not row:
        return None
    result = dict(row)
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM table_rows WHERE table_id = $1", table_id,
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
        "SELECT t.id, t.workspace_id, t.name, t.description, t.columns, "
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
        "RETURNING id, workspace_id, name, description, columns, "
        "created_by, updated_by, created_at, updated_at",
        cols, updated_by, table_id,
    )
    result = dict(row)
    result["row_count"] = table["row_count"]
    return result


async def update_column(table_id: UUID, column_id: str, updates: dict, updated_by: UUID) -> dict | None:
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
        "RETURNING id, workspace_id, name, description, columns, "
        "created_by, updated_by, created_at, updated_at",
        cols, updated_by, table_id,
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
        "RETURNING id, workspace_id, name, description, columns, "
        "created_by, updated_by, created_at, updated_at",
        cols, updated_by, table_id,
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
        "RETURNING id, workspace_id, name, description, columns, "
        "created_by, updated_by, created_at, updated_at",
        reordered, updated_by, table_id,
    )
    result = dict(row)
    result["row_count"] = table["row_count"]
    return result


# --- Row CRUD ---


async def create_row(table_id: UUID, data: dict, created_by: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO table_rows (table_id, data, row_order, created_by, updated_by) "
        "VALUES ($1, $2, "
        "  COALESCE((SELECT MAX(row_order) FROM table_rows WHERE table_id = $1), -1) + 1, "
        "  $3, $3) "
        "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
        table_id, data, created_by,
    )
    return dict(row)


async def create_rows_batch(table_id: UUID, rows_data: list[dict], created_by: UUID) -> list[dict]:
    pool = get_pool()
    results = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock within transaction to prevent concurrent row_order conflicts
            max_order = await conn.fetchval(
                "SELECT COALESCE(MAX(row_order), -1) FROM table_rows WHERE table_id = $1 FOR UPDATE",
                table_id,
            )
            for i, data in enumerate(rows_data):
                row = await conn.fetchrow(
                    "INSERT INTO table_rows (table_id, data, row_order, created_by, updated_by) "
                    "VALUES ($1, $2, $3, $4, $4) "
                    "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
                    table_id, data, max_order + 1 + i, created_by,
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


async def update_row(row_id: UUID, data: dict, updated_by: UUID) -> dict | None:
    """Partial merge update — only specified keys are changed."""
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE table_rows SET data = data || $1, updated_by = $2, updated_at = now() "
        "WHERE id = $3 "
        "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
        data, updated_by, row_id,
    )
    return dict(row) if row else None


async def delete_row(row_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM table_rows WHERE id = $1", row_id)
    return result == "DELETE 1"


async def update_rows_batch(table_id: UUID, updates: list[dict], updated_by: UUID) -> list[dict]:
    """Batch partial merge update. Each item: {row_id: UUID, data: dict}."""
    if not updates:
        return []
    pool = get_pool()
    results = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for item in updates:
                row = await conn.fetchrow(
                    "UPDATE table_rows SET data = data || $1, updated_by = $2, updated_at = now() "
                    "WHERE id = $3 AND table_id = $4 "
                    "RETURNING id, table_id, data, row_order, created_by, updated_by, created_at, updated_at",
                    item["data"], updated_by, item["row_id"], table_id,
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
        table_id, row_ids,
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
        *args, limit, offset,
    )
    return [dict(r) for r in rows], total


async def count_rows(table_id: UUID, filters: list[dict] | None = None) -> int:
    """Count rows matching optional filters without fetching data."""
    if not filters:
        pool = get_pool()
        return await pool.fetchval(
            "SELECT COUNT(*) FROM table_rows WHERE table_id = $1", table_id,
        )
    # Reuse list_rows logic with limit=0 to get count
    _, total = await list_rows(table_id, filters=filters, limit=0, offset=0)
    return total


async def export_rows_all(table_id: UUID, filters: list[dict] | None = None,
                          sort_by: str | None = None, sort_order: str = "asc") -> list[dict]:
    """Fetch ALL rows for export (no limit). Use for CSV export."""
    rows, _ = await list_rows(
        table_id, filters=filters, sort_by=sort_by, sort_order=sort_order,
        limit=2_000_000, offset=0,
    )
    return rows
