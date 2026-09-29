"""Read-only SQL over the caller's own reward-model rows, in an in-memory DuckDB.

Each query gets a fresh DuckDB holding only the caller's rows, so there is no
other user's data in reach to leak. The rows are loaded from temporary NDJSON
files (orders of magnitude faster than executemany); only after that is
external access (files, HTTP) disabled and the configuration locked, so the
caller's SELECT cannot read the host filesystem.
"""

import asyncio
import json
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from uuid import UUID

import duckdb

from ...database import get_pool

MAX_ROWS = 1000
QUERY_TIMEOUT_SECONDS = 10

SCHEMA = {
    "traces": [
        ("id", "VARCHAR"),
        ("external_id", "VARCHAR"),
        ("title", "VARCHAR"),
        ("source_format", "VARCHAR"),
        ("metadata", "JSON"),
        ("created_at", "TIMESTAMPTZ"),
    ],
    "steps": [
        ("id", "VARCHAR"),
        ("trace_id", "VARCHAR"),
        ("idx", "INTEGER"),
        ("role", "VARCHAR"),
        ("content", "VARCHAR"),
        ("tool_name", "VARCHAR"),
        ("tool_input", "JSON"),
        ("tool_call_id", "VARCHAR"),
        ("metadata", "JSON"),
    ],
    "annotations": [
        ("id", "VARCHAR"),
        ("trace_id", "VARCHAR"),
        ("step_id", "VARCHAR"),
        ("step_index", "INTEGER"),
        ("rating", "INTEGER"),
        ("comment", "VARCHAR"),
        ("quote", "JSON"),
        ("label_error", "BOOLEAN"),
        ("label_error_note", "VARCHAR"),
        ("created_at", "TIMESTAMPTZ"),
    ],
    "scores": [
        ("reward_model_id", "VARCHAR"),
        ("reward_model_name", "VARCHAR"),
        ("trace_id", "VARCHAR"),
        ("score", "DOUBLE"),
        ("created_at", "TIMESTAMPTZ"),
    ],
}

# Postgres side: one SELECT per DuckDB table, columns in SCHEMA order.
SOURCE_SQL = {
    "traces": """
        SELECT id::text, external_id, title, source_format, metadata, created_at
        FROM rm_traces WHERE owner_user_id = $1
    """,
    "steps": """
        SELECT s.id::text, s.trace_id::text, s.idx, s.role, s.content,
               s.tool_name, s.tool_input, s.tool_call_id, s.metadata
        FROM rm_trace_steps s JOIN rm_traces t ON t.id = s.trace_id
        WHERE t.owner_user_id = $1
    """,
    "annotations": """
        SELECT a.id::text, a.trace_id::text, a.step_id::text, s.idx, a.rating,
               a.comment, a.quote, a.label_error, a.label_error_note, a.created_at
        FROM rm_annotations a LEFT JOIN rm_trace_steps s ON s.id = a.step_id
        WHERE a.owner_user_id = $1
    """,
    "scores": """
        SELECT sc.reward_model_id::text, m.name, sc.trace_id::text, sc.score, sc.created_at
        FROM rm_trace_scores sc JOIN rm_reward_models m ON m.id = sc.reward_model_id
        WHERE m.owner_user_id = $1
    """,
}


class QueryRejected(ValueError):
    pass


def check_single_select(sql: str) -> None:
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.ParserException as exc:
        raise QueryRejected(str(exc)) from exc
    if len(statements) != 1:
        raise QueryRejected("Send exactly one SQL statement.")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise QueryRejected("Only SELECT (or WITH … SELECT) queries are allowed.")


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot load {type(value).__name__} into DuckDB")


def _load_tables(con: duckdb.DuckDBPyConnection, tables: dict[str, list], directory: Path) -> None:
    for name, columns in SCHEMA.items():
        column_names = [column for column, _ in columns]
        path = directory / f"{name}.jsonl"
        path.write_text(
            "".join(
                json.dumps(dict(zip(column_names, row, strict=True)), default=_json_value) + "\n"
                for row in tables[name]
            )
        )
        column_types = ", ".join(f"{column} {kind}" for column, kind in columns)
        con.execute(f"CREATE TABLE {name} ({column_types})")
        struct = ", ".join(f"'{column}': '{kind}'" for column, kind in columns)
        con.execute(
            f"INSERT INTO {name} SELECT * FROM read_json(?, format = 'newline_delimited', "
            f"columns = {{{struct}}})",
            [str(path)],
        )


def _run_in_duckdb(tables: dict[str, list], sql: str) -> dict:
    con = duckdb.connect(":memory:")
    try:
        with tempfile.TemporaryDirectory() as directory:
            _load_tables(con, tables, Path(directory))
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")

        timer = threading.Timer(QUERY_TIMEOUT_SECONDS, con.interrupt)
        timer.start()
        try:
            cursor = con.execute(sql)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchmany(MAX_ROWS + 1)
        except duckdb.InterruptException as exc:
            raise QueryRejected(f"query exceeded {QUERY_TIMEOUT_SECONDS}s") from exc
        except duckdb.Error as exc:
            raise QueryRejected(str(exc)) from exc
        finally:
            timer.cancel()
    finally:
        con.close()
    return {
        "columns": columns,
        "rows": [list(row) for row in rows[:MAX_ROWS]],
        "truncated": len(rows) > MAX_ROWS,
    }


async def run_query(owner_user_id: UUID, sql: str) -> dict:
    check_single_select(sql)
    pool = get_pool()
    tables = {}
    for name, source in SOURCE_SQL.items():
        tables[name] = [list(row) for row in await pool.fetch(source, owner_user_id)]
    return await asyncio.to_thread(_run_in_duckdb, tables, sql)
