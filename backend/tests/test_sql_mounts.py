"""External Postgres mounts for stash sql.

The mount contract: a customer-side database materializes into the same
DuckDB as native tables — addressable by mount name, joinable, visible in
information_schema — while the DSN never leaves the server and an unreachable
or oversized mount fails the query loudly instead of silently shrinking the
schema. The "remote" database in these tests is the test database itself,
scoped to a fixture schema, which exercises the full asyncpg fetch path
without a second server.
"""

import asyncpg
import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient

from backend.config import settings

from .conftest import unique_name

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture
async def remote_schema():
    """A scratch schema in the test database, standing in for a customer's
    Supabase: a parts lookup table and a world-observations ledger."""
    schema = unique_name("mount_fixture").replace("-", "_").lower()
    con = await asyncpg.connect(settings.DATABASE_URL)
    try:
        await con.execute(f'CREATE SCHEMA "{schema}"')
        await con.execute(
            f'CREATE TABLE "{schema}".reference_parts ('
            "  part_number text, tool_match text, price numeric)"
        )
        await con.execute(
            f'CREATE TABLE "{schema}".world_observations ('
            "  vin text, observation text, observed_at timestamptz, details jsonb)"
        )
        await con.execute(
            f'INSERT INTO "{schema}".reference_parts VALUES '
            "('BW-800110', 'Bendix AD-IP cartridge', 189.50), "
            "('MER-R955320', 'Meritor slack adjuster', 74.25)"
        )
        await con.execute(
            f'INSERT INTO "{schema}".world_observations VALUES '
            "('1XKAD49X5KJ211407', 'confirmed correct fit', now(), '{\"source\": \"shop\"}')"
        )
        yield schema
    finally:
        await con.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await con.close()


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("mounts"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['api_key']}"}


async def _mount(client: AsyncClient, headers: dict, schema: str, name: str = "supabase") -> dict:
    resp = await client.post(
        "/api/v1/me/sql/mounts",
        json={"name": name, "dsn": settings.DATABASE_URL, "remote_schema": schema},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _sql(client: AsyncClient, headers: dict, query: str) -> dict:
    resp = await client.post("/api/v1/me/sql", json={"query": query}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_create_reports_tables_and_redacts_dsn(client, remote_schema):
    headers = await _register(client)
    mount = await _mount(client, headers, remote_schema)
    assert mount["table_count"] == 2
    assert "dsn" not in mount

    listed = (await client.get("/api/v1/me/sql/mounts", headers=headers)).json()
    assert [m["name"] for m in listed] == ["supabase"]
    assert all("dsn" not in m for m in listed)


async def test_mounted_tables_are_queryable_by_mount_schema(client, remote_schema):
    headers = await _register(client)
    await _mount(client, headers, remote_schema)
    result = await _sql(
        client,
        headers,
        "SELECT tool_match FROM supabase.reference_parts WHERE part_number = 'BW-800110'",
    )
    assert result["rows"] == [["Bendix AD-IP cartridge"]]


async def test_bare_name_resolves_and_information_schema_tells_truth(client, remote_schema):
    headers = await _register(client)
    await _mount(client, headers, remote_schema)
    result = await _sql(client, headers, "SELECT vin FROM world_observations")
    assert result["rows"] == [["1XKAD49X5KJ211407"]]

    schemas = await _sql(
        client,
        headers,
        "SELECT DISTINCT table_schema FROM information_schema.tables "
        "WHERE table_schema = 'supabase'",
    )
    assert schemas["rows"] == [["supabase"]]


async def test_mounted_joins_native(client, remote_schema):
    headers = await _register(client)
    await _mount(client, headers, remote_schema)
    table = await client.post(
        "/api/v1/me/tables",
        json={"name": "notes", "columns": [{"name": "part_number", "type": "text"}]},
        headers=headers,
    )
    assert table.status_code == 201
    col_id = table.json()["columns"][0]["id"]
    created = await client.post(
        f"/api/v1/me/tables/{table.json()['id']}/rows",
        json={"data": {col_id: "BW-800110"}},
        headers=headers,
    )
    assert created.status_code == 201

    result = await _sql(
        client,
        headers,
        "SELECT p.tool_match FROM notes n "
        "JOIN supabase.reference_parts p ON p.part_number = n.part_number",
    )
    assert result["rows"] == [["Bendix AD-IP cartridge"]]


async def test_numeric_and_jsonb_columns_survive_the_crossing(client, remote_schema):
    headers = await _register(client)
    await _mount(client, headers, remote_schema)
    price = await _sql(client, headers, "SELECT price FROM supabase.reference_parts ORDER BY price")
    assert price["rows"] == [[74.25], [189.5]]
    details = await _sql(
        client,
        headers,
        "SELECT json_extract_string(details, '$.source') FROM supabase.world_observations",
    )
    assert details["rows"] == [["shop"]]


async def test_bad_dsn_fails_create_loudly(client):
    headers = await _register(client)
    resp = await client.post(
        "/api/v1/me/sql/mounts",
        json={"name": "supabase", "dsn": "postgresql://nope:nope@127.0.0.1:1/nope"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "unreachable" in resp.json()["detail"]


async def test_reserved_and_duplicate_names_rejected(client, remote_schema):
    headers = await _register(client)
    resp = await client.post(
        "/api/v1/me/sql/mounts",
        json={"name": "memory", "dsn": settings.DATABASE_URL, "remote_schema": remote_schema},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "reserved" in resp.json()["detail"]

    await _mount(client, headers, remote_schema)
    duplicate = await client.post(
        "/api/v1/me/sql/mounts",
        json={"name": "supabase", "dsn": settings.DATABASE_URL, "remote_schema": remote_schema},
        headers=headers,
    )
    assert duplicate.status_code == 409


async def test_oversized_mount_fails_the_query_not_the_worker(client, remote_schema, monkeypatch):
    from backend.services import sql_service

    headers = await _register(client)
    await _mount(client, headers, remote_schema)
    monkeypatch.setattr(sql_service, "MAX_MATERIALIZED_ROWS", 1)
    resp = await client.post("/api/v1/me/sql", json={"query": "SELECT 1"}, headers=headers)
    assert resp.status_code == 400
    assert "budget" in resp.json()["detail"]


async def test_removed_mount_is_gone_from_queries(client, remote_schema):
    headers = await _register(client)
    await _mount(client, headers, remote_schema)
    deleted = await client.delete("/api/v1/me/sql/mounts/supabase", headers=headers)
    assert deleted.status_code == 204
    resp = await client.post(
        "/api/v1/me/sql",
        json={"query": "SELECT * FROM supabase.reference_parts"},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_mount_writes_are_impossible(client, remote_schema):
    """The SELECT-only guard plus the read-only session mean no path writes
    through a mount; the guard rejects before any remote work happens."""
    headers = await _register(client)
    await _mount(client, headers, remote_schema)
    resp = await client.post(
        "/api/v1/me/sql",
        json={"query": "DELETE FROM supabase.reference_parts"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "read-only" in resp.json()["detail"]
