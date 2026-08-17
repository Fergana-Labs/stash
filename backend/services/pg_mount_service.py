"""External read-only Postgres mounts for stash sql.

A mount points at a database the scope's owner controls — for an integrator,
typically a read-only role on their own Postgres (Supabase, RDS, …). At query
time every table in the mount's remote schema that the role can SELECT is
materialized into the throwaway DuckDB under a schema named after the mount,
so `SELECT * FROM supabase.world_observations` works next to native tables.

The trust posture matches the rest of the scope contract: the customer's
role/view IS the access control. We additionally open every connection with
`default_transaction_read_only = on` so a mis-granted role still cannot be
written through, and a statement timeout so a wedged remote fails the query
instead of hanging the worker.

The user's SQL never sees the DSN and never gets a network path: rows are
fetched server-side here, and DuckDB keeps `enable_external_access` off.
"""

import json
import re
from urllib.parse import urlsplit
from uuid import UUID

import asyncpg

from ..database import get_pool
from ..integrations.crypto import integration_fernet

CONNECT_TIMEOUT_SECONDS = 5
# Applied server-side per session; covers each count and fetch statement.
REMOTE_STATEMENT_TIMEOUT_MS = 10_000

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
# Schemas stash sql already owns, plus DuckDB/Postgres system schemas.
_RESERVED_NAMES = {"main", "files", "memory", "temp", "system", "information_schema", "pg_catalog"}

_PG_TO_DUCKDB = {
    "smallint": "BIGINT",
    "integer": "BIGINT",
    "bigint": "BIGINT",
    "numeric": "DOUBLE",
    "real": "DOUBLE",
    "double precision": "DOUBLE",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "timestamp without time zone": "TIMESTAMP",
    "timestamp with time zone": "TIMESTAMP",
}


class PgMountError(Exception):
    """The mount cannot be created or read; message is user-facing."""


def validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise PgMountError("mount name must be a short lowercase identifier ([a-z][a-z0-9_]{0,31})")
    if name in _RESERVED_NAMES:
        raise PgMountError(f"mount name {name!r} is reserved")


def validate_dsn(dsn: str) -> None:
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise PgMountError("dsn must be a postgresql:// URL")


def _redacted(dsn: str) -> dict:
    """Host and database only — the DSN (with its password) never leaves the
    server after creation."""
    parsed = urlsplit(dsn)
    return {"host": parsed.hostname or "", "database": parsed.path.lstrip("/")}


async def create_mount(owner_user_id: UUID, name: str, dsn: str, remote_schema: str) -> dict:
    validate_name(name)
    validate_dsn(dsn)
    # Prove the DSN before storing it: connect, and enumerate the schema so a
    # typo'd password or empty schema fails the create, not tomorrow's query.
    tables = await _fetch_remote_tables(name, dsn, remote_schema, include_rows=False)
    row = await get_pool().fetchrow(
        """
        INSERT INTO pg_mounts (owner_user_id, name, dsn_encrypted, remote_schema)
        VALUES ($1, $2, $3, $4)
        RETURNING id, name, remote_schema, created_at
        """,
        owner_user_id,
        name,
        integration_fernet().encrypt(dsn.encode()),
        remote_schema,
    )
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "remote_schema": row["remote_schema"],
        "created_at": row["created_at"].isoformat(),
        "table_count": len(tables),
        **_redacted(dsn),
    }


async def list_mounts(owner_user_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, name, dsn_encrypted, remote_schema, created_at "
        "FROM pg_mounts WHERE owner_user_id = $1 ORDER BY name",
        owner_user_id,
    )
    result = []
    for row in rows:
        dsn = integration_fernet().decrypt(bytes(row["dsn_encrypted"])).decode()
        result.append(
            {
                "id": str(row["id"]),
                "name": row["name"],
                "remote_schema": row["remote_schema"],
                "created_at": row["created_at"].isoformat(),
                **_redacted(dsn),
            }
        )
    return result


async def delete_mount(owner_user_id: UUID, name: str) -> bool:
    status = await get_pool().execute(
        "DELETE FROM pg_mounts WHERE owner_user_id = $1 AND name = $2",
        owner_user_id,
        name,
    )
    return status.endswith("1")


async def fetch_mounted_tables(owner_user_id: UUID, row_budget: int) -> list[dict]:
    """Every mounted table with columns and rows, ready to materialize.

    Returns [{schema, name, columns: [(name, duckdb_type)], rows: [tuple]}].
    A mount that cannot be reached fails the whole query — a silently absent
    table would make the agent conclude the data doesn't exist. `row_budget`
    is what remains of the scope's materialization cap after native tables;
    rows are counted before they are fetched, so an oversized remote table
    fails the budget check instead of exhausting worker memory.
    """
    rows = await get_pool().fetch(
        "SELECT name, dsn_encrypted, remote_schema FROM pg_mounts "
        "WHERE owner_user_id = $1 ORDER BY name",
        owner_user_id,
    )
    tables: list[dict] = []
    for row in rows:
        dsn = integration_fernet().decrypt(bytes(row["dsn_encrypted"])).decode()
        fetched = await _fetch_remote_tables(
            row["name"], dsn, row["remote_schema"], include_rows=True, row_budget=row_budget
        )
        row_budget -= sum(len(t["rows"]) for t in fetched)
        tables.extend(fetched)
    return tables


async def _fetch_remote_tables(
    mount_name: str,
    dsn: str,
    remote_schema: str,
    *,
    include_rows: bool,
    row_budget: int = 0,
) -> list[dict]:
    try:
        con = await asyncpg.connect(
            dsn,
            timeout=CONNECT_TIMEOUT_SECONDS,
            server_settings={
                "default_transaction_read_only": "on",
                "statement_timeout": str(REMOTE_STATEMENT_TIMEOUT_MS),
            },
        )
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        raise PgMountError(f"mount {mount_name!r} unreachable: {exc}") from None
    try:
        relations = await con.fetch(
            """
            SELECT c.relname AS name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = $1
              AND c.relkind IN ('r', 'p', 'v', 'm')
              AND has_table_privilege(c.oid, 'SELECT')
            ORDER BY c.relname
            """,
            remote_schema,
        )
        if not relations:
            raise PgMountError(
                f"mount {mount_name!r}: no readable tables in schema {remote_schema!r}"
            )
        tables = []
        remaining = row_budget
        for relation in relations:
            table_name = relation["name"]
            columns = await con.fetch(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = $2
                ORDER BY ordinal_position
                """,
                remote_schema,
                table_name,
            )
            column_defs = [
                (c["column_name"], _PG_TO_DUCKDB.get(c["data_type"], "VARCHAR")) for c in columns
            ]
            table = {"schema": mount_name, "name": table_name, "columns": column_defs}
            if include_rows:
                qualified = f'"{remote_schema}"."{table_name}"'
                count = await con.fetchval(f"SELECT count(*) FROM {qualified}")
                if count > remaining:
                    raise PgMountError(
                        f"mount {mount_name!r}: table {table_name!r} has {count} rows, "
                        f"above the remaining stash sql budget of {remaining}"
                    )
                remaining -= count
                records = await con.fetch(f"SELECT * FROM {qualified}")
                table["rows"] = [
                    tuple(_duckdb_value(record[name], duck_type) for name, duck_type in column_defs)
                    for record in records
                ]
            tables.append(table)
        return tables
    except asyncpg.PostgresError as exc:
        raise PgMountError(f"mount {mount_name!r}: {exc}") from None
    finally:
        await con.close()


def _duckdb_value(value, duck_type: str):
    if value is None:
        return None
    if duck_type == "TIMESTAMP" and getattr(value, "tzinfo", None) is not None:
        return value.replace(tzinfo=None) - value.utcoffset()
    if duck_type != "VARCHAR" or isinstance(value, str):
        return value
    # asyncpg returns json/jsonb as str already; what remains is uuids,
    # arrays, ranges, bytea — stringify so the VARCHAR column always loads.
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str)
    return str(value)
