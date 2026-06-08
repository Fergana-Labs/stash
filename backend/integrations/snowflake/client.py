"""Snowflake read-only query client.

Snowflake is a *queryable* source, not a document store: the agent runs SELECTs
against it live instead of crawling it into FTS. Everything here is read-only:
we allowlist a small set of statement keywords, reject multiple statements, and
cap returned rows. The driver is blocking, so every call runs in a thread.

`snowflake.connector` is imported lazily inside `_connect` so the integration
registers (and the rest of the app imports) even where the driver isn't
installed; only an actual connection needs it.
"""

from __future__ import annotations

import asyncio
import json
import re
from uuid import UUID

from ..storage import get_valid_token

# Statements we allow. Everything else (INSERT/UPDATE/DELETE/MERGE/CREATE/DROP/
# ALTER/GRANT/CALL/…) is rejected before it reaches Snowflake.
READ_ONLY_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")
ROW_CAP = 200
# A qualified table identifier: db.schema.table, optionally double-quoted parts.
_IDENTIFIER_RE = re.compile(r'^[A-Za-z0-9_$."]+$')


def _assert_read_only(sql: str) -> str:
    """Return a single read-only statement or raise ValueError."""
    stmt = sql.strip().rstrip(";").strip()
    if not stmt:
        raise ValueError("empty query")
    if ";" in stmt:
        raise ValueError("only a single statement is allowed")
    keyword = stmt.split(None, 1)[0].upper()
    if keyword not in READ_ONLY_PREFIXES:
        raise ValueError(
            f"only read-only statements are allowed (SELECT/SHOW/DESCRIBE/EXPLAIN); got {keyword}"
        )
    return stmt


def _validate_identifier(ref: str) -> str:
    if not ref or not _IDENTIFIER_RE.match(ref):
        raise ValueError(f"invalid table identifier: {ref!r}")
    return ref


def _cell(value):
    """Coerce a Snowflake cell to something JSON-serializable (Decimal, datetime,
    bytes, etc. become strings)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _connect(creds: dict):
    import snowflake.connector  # lazy: only needed for a live connection

    kwargs: dict = {"account": creds["account"], "user": creds["user"]}
    for key in ("role", "warehouse", "database", "schema"):
        if creds.get(key):
            kwargs[key] = creds[key]

    private_key = creds.get("private_key")
    if creds.get("token"):
        # A Programmatic Access Token authenticates in place of a password.
        kwargs["password"] = creds["token"]
    elif private_key:
        from cryptography.hazmat.primitives import serialization

        passphrase = creds.get("private_key_passphrase") or None
        key = serialization.load_pem_private_key(
            private_key.encode(),
            password=passphrase.encode() if passphrase else None,
        )
        kwargs["private_key"] = key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    elif creds.get("password"):
        kwargs["password"] = creds["password"]
    else:
        raise ValueError("Snowflake credentials need a token, private key, or password")

    return snowflake.connector.connect(**kwargs)


def _run_sync(creds: dict, sql: str, limit: int) -> dict:
    conn = _connect(creds)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        columns = [c[0] for c in cur.description] if cur.description else []
        rows = cur.fetchmany(limit)
        return {
            "columns": columns,
            "rows": [[_cell(v) for v in row] for row in rows],
            "row_count": len(rows),
            "truncated": len(rows) >= limit,
        }
    finally:
        conn.close()


async def _creds(owner_user_id: UUID) -> dict:
    return json.loads(await get_valid_token(owner_user_id, "snowflake"))


async def test_connection(creds: dict) -> str:
    """Validate credentials and return 'user @ account' for the integration card."""
    result = await asyncio.to_thread(
        _run_sync, creds, "SELECT CURRENT_USER(), CURRENT_ACCOUNT()", 1
    )
    if result["rows"]:
        user, account = result["rows"][0]
        return f"{user} @ {account}"
    return creds.get("user", "Snowflake")


async def run_query(source: dict, sql: str, limit: int = ROW_CAP) -> dict:
    """Run one read-only statement on behalf of the source's owner."""
    stmt = _assert_read_only(sql)
    creds = await _creds(UUID(source["owner_user_id"]))
    return await asyncio.to_thread(_run_sync, creds, stmt, min(limit, ROW_CAP))


async def list_tables(source: dict) -> list[dict]:
    """List tables as navigation entries: path = fully-qualified name."""
    creds = await _creds(UUID(source["owner_user_id"]))
    result = await asyncio.to_thread(_run_sync, creds, "SHOW TERSE TABLES IN ACCOUNT", 500)
    name_i = result["columns"].index("name") if "name" in result["columns"] else 1
    db_i = (
        result["columns"].index("database_name") if "database_name" in result["columns"] else None
    )
    schema_i = (
        result["columns"].index("schema_name") if "schema_name" in result["columns"] else None
    )
    entries = []
    for row in result["rows"]:
        name = row[name_i]
        parts = [
            row[db_i] if db_i is not None else None,
            row[schema_i] if schema_i is not None else None,
            name,
        ]
        full = ".".join(str(p) for p in parts if p)
        entries.append({"path": full, "name": name, "kind": "table"})
    return entries


async def describe_table(source: dict, ref: str) -> dict:
    """Return a table's columns (name + type) so the agent can write a query."""
    table = _validate_identifier(ref)
    creds = await _creds(UUID(source["owner_user_id"]))
    result = await asyncio.to_thread(_run_sync, creds, f"DESCRIBE TABLE {table}", ROW_CAP)
    name_i = result["columns"].index("name") if "name" in result["columns"] else 0
    type_i = result["columns"].index("type") if "type" in result["columns"] else 1
    cols = [f"{row[name_i]} {row[type_i]}" for row in result["rows"]]
    return {
        "path": ref,
        "name": ref,
        "kind": "table",
        "content": f"Table {ref}\nColumns:\n" + "\n".join(cols),
    }
