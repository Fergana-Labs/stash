"""stash sql: real SQL over the scope's tables, without touching Postgres.

The endpoint materializes tables into a throwaway DuckDB per request. These
tests pin the contract that makes it feel like a relational database: bare
names resolve when unique, folder paths qualify when they don't,
information_schema tells the truth, and anything that isn't a read fails
loudly instead of pretending to write.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from .conftest import unique_name

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient) -> tuple[dict, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("sql"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, UUID(body["id"])


async def _make_folder(client: AsyncClient, headers: dict, name: str) -> str:
    resp = await client.post("/api/v1/me/folders", json={"name": name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _make_table(
    client: AsyncClient,
    headers: dict,
    name: str,
    columns: list[dict],
    rows: list[dict],
    folder_id: str | None = None,
) -> dict:
    resp = await client.post(
        "/api/v1/me/tables",
        json={"name": name, "columns": columns, "folder_id": folder_id},
        headers=headers,
    )
    assert resp.status_code == 201
    table = resp.json()
    by_name = {c["name"]: c["id"] for c in table["columns"]}
    for row in rows:
        created = await client.post(
            f"/api/v1/me/tables/{table['id']}/rows",
            json={"data": {by_name[k]: v for k, v in row.items()}},
            headers=headers,
        )
        assert created.status_code == 201
    return table


async def _sql(client: AsyncClient, headers: dict, query: str):
    return await client.post("/api/v1/me/sql", json={"query": query}, headers=headers)


JOBS_COLUMNS = [
    {"name": "Company", "type": "text"},
    {"name": "Salary", "type": "number"},
    {"name": "Applied", "type": "date"},
]

JOBS_ROWS = [
    {"Company": "Acme", "Salary": 90000, "Applied": "2026-01-05"},
    {"Company": "Globex", "Salary": 120000, "Applied": "2026-02-10"},
    {"Company": "Initech", "Salary": 80000, "Applied": "2026-03-01"},
]


async def test_select_with_aggregate_and_typed_columns(client: AsyncClient):
    headers, _ = await _register(client)
    await _make_table(client, headers, "Jobs", JOBS_COLUMNS, JOBS_ROWS)

    resp = await _sql(
        client,
        headers,
        'SELECT "Company", "Salary" FROM jobs WHERE "Applied" >= DATE \'2026-02-01\' '
        'ORDER BY "Salary" DESC',
    )

    assert resp.status_code == 200
    body = resp.json()
    assert [c["name"] for c in body["columns"]] == ["Company", "Salary"]
    assert body["rows"] == [["Globex", 120000.0], ["Initech", 80000.0]]
    assert body["truncated"] is False


async def test_tables_resolve_by_folder_path_schema(client: AsyncClient):
    headers, _ = await _register(client)
    folder_id = await _make_folder(client, headers, "Hiring")
    await _make_table(client, headers, "Jobs", JOBS_COLUMNS, JOBS_ROWS, folder_id=folder_id)

    bare = await _sql(client, headers, "SELECT COUNT(*) FROM jobs")
    qualified = await _sql(client, headers, 'SELECT COUNT(*) FROM "files/Hiring".jobs')

    assert bare.status_code == 200
    assert bare.json()["rows"] == [[3]]
    assert qualified.status_code == 200
    assert qualified.json()["rows"] == [[3]]


async def test_duplicate_names_require_the_folder_path(client: AsyncClient):
    """Two folders each hold a "Jobs" table. The bare name must not silently
    pick one — it doesn't exist; both folder-qualified names work."""
    headers, _ = await _register(client)
    for folder_name, company in [("A", "Acme"), ("B", "Globex")]:
        folder_id = await _make_folder(client, headers, folder_name)
        await _make_table(
            client,
            headers,
            "Jobs",
            [{"name": "Company", "type": "text"}],
            [{"Company": company}],
            folder_id=folder_id,
        )

    bare = await _sql(client, headers, "SELECT * FROM jobs")
    assert bare.status_code == 400
    assert "jobs" in bare.json()["detail"].lower()

    a = await _sql(client, headers, 'SELECT "Company" FROM "files/A".jobs')
    b = await _sql(client, headers, 'SELECT "Company" FROM "files/B".jobs')
    assert a.json()["rows"] == [["Acme"]]
    assert b.json()["rows"] == [["Globex"]]


async def test_join_across_tables(client: AsyncClient):
    headers, _ = await _register(client)
    await _make_table(client, headers, "Jobs", JOBS_COLUMNS, JOBS_ROWS)
    await _make_table(
        client,
        headers,
        "Notes",
        [{"name": "Company", "type": "text"}, {"name": "Note", "type": "text"}],
        [{"Company": "Globex", "Note": "great team"}],
    )

    resp = await _sql(
        client,
        headers,
        'SELECT j."Company", n."Note" FROM jobs j JOIN notes n ON j."Company" = n."Company"',
    )

    assert resp.status_code == 200
    assert resp.json()["rows"] == [["Globex", "great team"]]


async def test_information_schema_tells_the_truth(client: AsyncClient):
    headers, _ = await _register(client)
    folder_id = await _make_folder(client, headers, "Hiring")
    await _make_table(client, headers, "Jobs", JOBS_COLUMNS, [], folder_id=folder_id)

    resp = await _sql(
        client,
        headers,
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema = 'files/Hiring'",
    )

    assert resp.json()["rows"] == [["files/Hiring", "Jobs"]]

    columns = await _sql(
        client,
        headers,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'files/Hiring' AND table_name = 'Jobs' "
        "ORDER BY ordinal_position",
    )
    assert columns.json()["rows"] == [
        ["_row_id", "VARCHAR"],
        ["Company", "VARCHAR"],
        ["Salary", "DOUBLE"],
        ["Applied", "DATE"],
    ]


async def test_writes_are_rejected(client: AsyncClient):
    headers, _ = await _register(client)
    await _make_table(client, headers, "Jobs", JOBS_COLUMNS, JOBS_ROWS)

    for query in [
        "INSERT INTO jobs VALUES ('x', 'Evil', 1, DATE '2026-01-01')",
        "DELETE FROM jobs",
        "DROP TABLE jobs",
        "SELECT 1; SELECT 2",
        # EXPLAIN ANALYZE runs the statement it wraps while still parsing as an
        # EXPLAIN, so allowing EXPLAIN would let any write through the gate.
        "EXPLAIN ANALYZE DELETE FROM jobs",
        "EXPLAIN ANALYZE INSERT INTO jobs VALUES ('x', 'Evil', 1, DATE '2026-01-01')",
    ]:
        resp = await _sql(client, headers, query)
        assert resp.status_code == 400, query


async def test_read_only_introspection_still_works(client: AsyncClient):
    """Rejecting EXPLAIN must not cost the caller schema discovery: DESCRIBE,
    SHOW and SUMMARIZE all parse as SELECT and stay available."""
    headers, _ = await _register(client)
    await _make_table(client, headers, "Jobs", JOBS_COLUMNS, JOBS_ROWS)

    for query in ["DESCRIBE jobs", "SHOW TABLES", "SUMMARIZE jobs"]:
        resp = await _sql(client, headers, query)
        assert resp.status_code == 200, query


async def test_sql_errors_surface_as_400(client: AsyncClient):
    """A binder error and a syntax error are both the caller's mistake. They
    take different paths — the binder error comes from executing the query, the
    syntax error from parsing it before anything is materialized — and both
    have to reach the caller as a 400 they can act on."""
    headers, _ = await _register(client)

    resp = await _sql(client, headers, "SELECT * FROM nonexistent")
    assert resp.status_code == 400
    assert "nonexistent" in resp.json()["detail"]

    malformed = await _sql(client, headers, "SELEC * FROM jobs")
    assert malformed.status_code == 400
    assert "SELEC" in malformed.json()["detail"]


async def test_stale_column_type_names_the_offending_table(client: AsyncClient):
    """Changing a column's type does not rewrite rows already stored, so a text
    value can end up under a number column. Every query materializes every table
    in the scope, so this one table decides whether `stash sql` works at all —
    it must come back as a 400 naming the table, not an opaque 500."""
    headers, _ = await _register(client)
    table = await _make_table(
        client,
        headers,
        "Payroll",
        [{"name": "Salary", "type": "text"}],
        [{"Salary": "not a number"}],
    )
    column_id = table["columns"][0]["id"]
    patched = await client.patch(
        f"/api/v1/me/tables/{table['id']}/columns/{column_id}",
        json={"type": "number"},
        headers=headers,
    )
    assert patched.status_code == 200

    resp = await _sql(client, headers, "SELECT 1")

    assert resp.status_code == 400
    assert "Payroll" in resp.json()["detail"]
