"""stash sql: read-only SQL over the scope's tables.

Each request materializes the scope's tables into a throwaway in-memory
DuckDB, runs the user's query there, and discards the instance. The user's
SQL never executes against the application Postgres — the blast radius of a
pathological query is one capped, interrupted DuckDB connection.

Addressing mirrors the VFS: every table exists as `"<folder path>"."<name>"`
(schema "files" for the root, "files/Jobs" for a folder, "memory/…" under the
Memory wiki), plus a bare-name view in `main` when the name is unique across
the scope, so `SELECT * FROM jobs` just works. Because it is real DuckDB,
`information_schema` reflects all of this truthfully.

External Postgres mounts (pg_mount_service) join the same instance: each
mount's remote tables materialize under a schema named after the mount, so a
customer's own database is queryable — and joinable against native tables —
through the identical read-only surface. Rows are fetched server-side; the
user's SQL still runs with no network access.
"""

import base64
import datetime
import decimal
import json
import threading
import uuid
from uuid import UUID

import anyio.to_thread
import duckdb

from ..database import get_pool
from . import pg_mount_service, table_service

# One query materializes every table in the scope (that is what makes
# information_schema truthful and cross-table joins work), so the cap is on
# the scope's total row count.
MAX_MATERIALIZED_ROWS = 200_000
MAX_RESULT_ROWS = 10_000
QUERY_TIMEOUT_SECONDS = 15

_DUCKDB_TYPES = {
    "text": "VARCHAR",
    "url": "VARCHAR",
    "email": "VARCHAR",
    "select": "VARCHAR",
    "number": "DOUBLE",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "multiselect": "VARCHAR",
    "json": "VARCHAR",
}


class SqlError(Exception):
    """The query (or the scope's data) cannot be run; message is user-facing."""


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def run_query(owner_user_id: UUID, user_id: UUID, query: str) -> dict:
    tables = await table_service.list_tables(owner_user_id, user_id)

    pool = get_pool()
    table_ids = [t["id"] for t in tables]
    total_rows = 0
    if table_ids:
        total_rows = await pool.fetchval(
            "SELECT COUNT(*) FROM table_rows WHERE table_id = ANY($1::uuid[])", table_ids
        )
    if total_rows > MAX_MATERIALIZED_ROWS:
        raise SqlError(
            f"this scope has {total_rows} table rows, above the stash sql "
            f"limit of {MAX_MATERIALIZED_ROWS}"
        )

    rows_by_table: dict[UUID, list[dict]] = {tid: [] for tid in table_ids}
    if table_ids:
        for record in await pool.fetch(
            "SELECT table_id, id, data FROM table_rows "
            "WHERE table_id = ANY($1::uuid[]) ORDER BY table_id, row_order",
            table_ids,
        ):
            rows_by_table[record["table_id"]].append(record)

    schema_by_folder = await _folder_schema_names(owner_user_id)

    try:
        external_tables = await pg_mount_service.fetch_mounted_tables(
            owner_user_id, MAX_MATERIALIZED_ROWS - total_rows
        )
    except pg_mount_service.PgMountError as exc:
        raise SqlError(str(exc)) from None

    return await anyio.to_thread.run_sync(
        _run_in_duckdb, tables, rows_by_table, schema_by_folder, external_tables, query
    )


async def _folder_schema_names(owner_user_id: UUID) -> dict[UUID, str]:
    """Each folder's DuckDB schema name, mirroring its VFS path: the root is
    "files", a folder is "files/<name>/…", and the Memory wiki is "memory"."""
    pool = get_pool()
    folders = await pool.fetch(
        "SELECT id, name, parent_folder_id, is_memory FROM folders WHERE owner_user_id = $1",
        owner_user_id,
    )
    by_id = {f["id"]: f for f in folders}
    paths: dict[UUID, str] = {}

    def path(folder_id: UUID) -> str:
        if folder_id in paths:
            return paths[folder_id]
        folder = by_id[folder_id]
        if folder["is_memory"]:
            result = "memory"
        elif folder["parent_folder_id"] is None:
            result = f"files/{folder['name']}"
        else:
            result = f"{path(folder['parent_folder_id'])}/{folder['name']}"
        paths[folder_id] = result
        return result

    return {f["id"]: path(f["id"]) for f in folders}


def _run_in_duckdb(
    tables: list[dict],
    rows_by_table: dict[UUID, list[dict]],
    schema_by_folder: dict[UUID, str],
    external_tables: list[dict],
    query: str,
) -> dict:
    # Parsing is where a syntax error lands, and it is the user's mistake.
    try:
        statements = duckdb.extract_statements(query)
    except duckdb.Error as exc:
        raise SqlError(str(exc)) from None
    if len(statements) != 1:
        raise SqlError("stash sql runs exactly one statement per call")
    # EXPLAIN is not allowed: `EXPLAIN ANALYZE <write>` reports the EXPLAIN
    # statement type while actually running the write it wraps, and DuckDB
    # exposes no way to inspect the wrapped statement. DESCRIBE, SHOW and
    # SUMMARIZE all parse as SELECT, so introspection is unaffected.
    if statements[0].type != duckdb.StatementType.SELECT:
        raise SqlError(
            "stash sql is read-only: only SELECT is supported. "
            "Write through the tables API or `stash tables` commands."
        )

    con = duckdb.connect(
        ":memory:",
        config={"enable_external_access": False, "memory_limit": "512MB", "threads": 2},
    )
    # The timer covers materialization too: a scope near the row cap can spend
    # the whole budget on INSERTs before the user's query ever starts.
    timer = threading.Timer(QUERY_TIMEOUT_SECONDS, con.interrupt)
    timer.start()
    # Bare-name views span native and mounted tables alike, so a name is only
    # "unique" when nothing else in the scope claims it.
    name_counts: dict[str, int] = {}
    for table in [*tables, *external_tables]:
        key = table["name"].lower()
        name_counts[key] = name_counts.get(key, 0) + 1

    try:
        _materialize(con, tables, rows_by_table, schema_by_folder, name_counts)
        _materialize_external(con, external_tables, name_counts)
        cursor = con.execute(query)
        columns = [{"name": d[0], "type": str(d[1])} for d in (cursor.description or [])]
        fetched = cursor.fetchmany(MAX_RESULT_ROWS + 1)
    except duckdb.InterruptException:
        raise SqlError(f"query timed out after {QUERY_TIMEOUT_SECONDS}s") from None
    except duckdb.Error as exc:
        raise SqlError(str(exc)) from None
    finally:
        # cancel() does not wait out a timer that already fired, and
        # interrupting a closed connection is a use-after-free.
        timer.cancel()
        timer.join()
        con.close()

    truncated = len(fetched) > MAX_RESULT_ROWS
    rows = [[_jsonable(value) for value in row] for row in fetched[:MAX_RESULT_ROWS]]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


def _materialize(
    con: duckdb.DuckDBPyConnection,
    tables: list[dict],
    rows_by_table: dict[UUID, list[dict]],
    schema_by_folder: dict[UUID, str],
    name_counts: dict[str, int],
) -> None:
    seen_qualified: set[tuple[str, str]] = set()
    for table in tables:
        table_name = table["name"]
        folder_id = table.get("folder_id")
        schema = schema_by_folder[folder_id] if folder_id else "files"
        # DuckDB resolves identifiers case-insensitively, so "Jobs" and "jobs"
        # in one folder would collide even though Postgres kept them distinct.
        if (schema, table_name.lower()) in seen_qualified:
            table_name = f"{table_name}--{str(table['id'])[:8]}"
        seen_qualified.add((schema, table_name.lower()))

        columns = _column_defs(table["columns"])
        qualified = f"{_ident(schema)}.{_ident(table_name)}"
        column_sql = ", ".join(
            f"{_ident(name)} {_DUCKDB_TYPES[ctype]}" for name, ctype, _ in columns
        )
        records = rows_by_table.get(table["id"], [])
        try:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {_ident(schema)}")
            con.execute(f"CREATE TABLE {qualified} ({column_sql})")
            if records:
                placeholders = ", ".join("?" for _ in columns)
                con.executemany(
                    f"INSERT INTO {qualified} VALUES ({placeholders})",
                    [_row_values(record, columns) for record in records],
                )
            if name_counts[table["name"].lower()] == 1:
                con.execute(f"CREATE VIEW main.{_ident(table_name)} AS SELECT * FROM {qualified}")
        except duckdb.InterruptException:
            # A timeout stays a timeout; it is not this table's fault.
            raise
        except duckdb.Error as exc:
            # Every query materializes every table, so a table whose rows no
            # longer match its column types (the column type was changed after
            # the rows were written) would otherwise break `stash sql` for the
            # entire scope with an opaque 500.
            raise SqlError(f"table {table['name']!r} could not be loaded: {exc}") from None


def _materialize_external(
    con: duckdb.DuckDBPyConnection,
    external_tables: list[dict],
    name_counts: dict[str, int],
) -> None:
    for table in external_tables:
        qualified = f"{_ident(table['schema'])}.{_ident(table['name'])}"
        column_sql = ", ".join(
            f"{_ident(name)} {duck_type}" for name, duck_type in table["columns"]
        )
        try:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {_ident(table['schema'])}")
            con.execute(f"CREATE TABLE {qualified} ({column_sql})")
            if table["rows"]:
                placeholders = ", ".join("?" for _ in table["columns"])
                con.executemany(f"INSERT INTO {qualified} VALUES ({placeholders})", table["rows"])
            if name_counts[table["name"].lower()] == 1:
                con.execute(
                    f"CREATE VIEW main.{_ident(table['name'])} AS SELECT * FROM {qualified}"
                )
        except duckdb.InterruptException:
            raise
        except duckdb.Error as exc:
            raise SqlError(
                f"mounted table {table['schema']}.{table['name']} could not be loaded: {exc}"
            ) from None


def _column_defs(columns: list[dict]) -> list[tuple[str, str, str | None]]:
    """(duckdb column name, stash column type, stash column id). The row's
    UUID always leads as _row_id; duplicate display names get an id suffix so
    the CREATE TABLE never collides."""
    defs: list[tuple[str, str, str | None]] = [("_row_id", "text", None)]
    seen = {"_row_id"}
    for column in sorted(columns, key=lambda c: c.get("order", 0)):
        name = column["name"]
        if name.lower() in seen:
            name = f"{name}--{column['id']}"
        seen.add(name.lower())
        defs.append((name, column["type"], column["id"]))
    return defs


def _row_values(record: dict, columns: list[tuple[str, str, str | None]]) -> list:
    data = record["data"]
    values: list = [str(record["id"])]
    for _, ctype, column_id in columns[1:]:
        value = data.get(column_id)
        if value is not None and ctype in ("multiselect", "json") and not isinstance(value, str):
            value = json.dumps(value)
        values.append(value)
    return values


def _jsonable(value):
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode()
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value
