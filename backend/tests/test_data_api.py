"""Tests for the PostgREST/supabase-js-compatible data API (/rest/v1)."""

import uuid

import pytest
from httpx import AsyncClient

from backend import auth
from backend.config import settings

_SECRET = "test-dashboard-secret-which-is-long-enough"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient) -> tuple[str, dict]:
    name = f"user_{uuid.uuid4().hex[:10]}"
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "display_name": name, "password": "password123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


async def _setup(client: AsyncClient):
    """Register, make a workspace + a 'Sales' table with two columns, seed rows."""
    api_key, user = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Dash"}, headers=_auth(api_key))
    ).json()
    await client.post(
        f"/api/v1/workspaces/{ws['id']}/tables",
        json={
            "name": "Sales",
            "columns": [
                {"name": "Name", "type": "text"},
                {"name": "Revenue", "type": "number"},
            ],
        },
        headers=_auth(api_key),
    )
    hdr = {**_auth(api_key), "X-Stash-Workspace": ws["id"]}
    for name, rev in [("Acme", 5000), ("Globex", 200), ("Initech", 3000)]:
        r = await client.post("/rest/v1/Sales", json={"Name": name, "Revenue": rev}, headers=hdr)
        assert r.status_code == 201, r.text
    return api_key, user, ws, hdr


@pytest.mark.asyncio
async def test_filter_select_order_and_content_range(client: AsyncClient):
    _key, _user, _ws, hdr = await _setup(client)

    resp = await client.get(
        "/rest/v1/Sales?Revenue=gt.1000&select=Name,Revenue&order=Revenue.desc", headers=hdr
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    # Globex (200) filtered out; Acme(5000) before Initech(3000) by desc revenue.
    assert [r["Name"] for r in rows] == ["Acme", "Initech"]
    # select limited the projection to the two named columns.
    assert set(rows[0].keys()) == {"Name", "Revenue"}
    # Content-Range reflects 2 returned of 2 total matching.
    assert resp.headers["Content-Range"] == "0-1/2"


@pytest.mark.asyncio
async def test_insert_returns_row_with_id_then_patch_and_delete(client: AsyncClient):
    _key, _user, _ws, hdr = await _setup(client)

    created = (
        await client.post("/rest/v1/Sales", json={"Name": "Hooli", "Revenue": 10}, headers=hdr)
    ).json()
    row_id = created["id"]
    assert created["Name"] == "Hooli"

    patched = await client.patch(
        f"/rest/v1/Sales?id=eq.{row_id}", json={"Revenue": 99}, headers=hdr
    )
    assert patched.status_code == 200
    assert patched.json()["Revenue"] == 99

    deleted = await client.delete(f"/rest/v1/Sales?id=eq.{row_id}", headers=hdr)
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_numeric_order_is_numeric_not_lexicographic(client: AsyncClient):
    api_key, _user = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "N"}, headers=_auth(api_key))
    ).json()
    await client.post(
        f"/api/v1/workspaces/{ws['id']}/tables",
        json={"name": "T", "columns": [{"name": "V", "type": "number"}]},
        headers=_auth(api_key),
    )
    hdr = {**_auth(api_key), "X-Stash-Workspace": ws["id"]}
    for v in [900, 7400, 5000, 3200]:
        await client.post("/rest/v1/T", json={"V": v}, headers=hdr)
    rows = (await client.get("/rest/v1/T?order=V.desc", headers=hdr)).json()
    # Numeric order, not text order (which would put 900 first because '9' > '7').
    assert [r["V"] for r in rows] == [7400, 5000, 3200, 900]


@pytest.mark.asyncio
async def test_schema_introspection(client: AsyncClient):
    _key, _user, _ws, hdr = await _setup(client)
    resp = await client.get("/rest/v1", headers=hdr)
    assert resp.status_code == 200
    tables = resp.json()["tables"]
    sales = next(t for t in tables if t["name"] == "Sales")
    assert {c["name"] for c in sales["columns"]} == {"Name", "Revenue"}


@pytest.mark.asyncio
async def test_get_one_row_by_id(client: AsyncClient):
    # supabase .eq('id', x): fetch a single row by its id (id is the row id, not a cell).
    _key, _user, _ws, hdr = await _setup(client)
    created = (
        await client.post("/rest/v1/Sales", json={"Name": "Solo", "Revenue": 1}, headers=hdr)
    ).json()
    row_id = created["id"]

    resp = await client.get(f"/rest/v1/Sales?id=eq.{row_id}", headers=hdr)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1 and rows[0]["Name"] == "Solo"

    # A non-existent id returns an empty list, not an error.
    missing = await client.get(
        "/rest/v1/Sales?id=eq.00000000-0000-0000-0000-000000000000", headers=hdr
    )
    assert missing.status_code == 200 and missing.json() == []


@pytest.mark.asyncio
async def test_unsupported_and_bad_queries(client: AsyncClient):
    _key, _user, _ws, hdr = await _setup(client)

    # Embedded select (join) -> 501
    assert (await client.get("/rest/v1/Sales?select=Name,other(*)", headers=hdr)).status_code == 501
    # Multi-column order -> 501
    assert (
        await client.get("/rest/v1/Sales?order=Name.asc,Revenue.desc", headers=hdr)
    ).status_code == 501
    # Unknown column filter -> 400
    assert (await client.get("/rest/v1/Sales?Nope=eq.1", headers=hdr)).status_code == 400
    # PATCH without id=eq -> 400
    assert (
        await client.patch("/rest/v1/Sales?Name=eq.Acme", json={"Revenue": 1}, headers=hdr)
    ).status_code == 400


@pytest.mark.asyncio
async def test_missing_workspace_header(client: AsyncClient):
    api_key, _user = await _register(client)
    resp = await client.get("/rest/v1/Sales", headers=_auth(api_key))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_dashboard_token_reads_but_cannot_write(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "DASHBOARD_TOKEN_SECRET", _SECRET)
    _key, user, ws, _hdr = await _setup(client)

    dt, _exp = auth.mint_dashboard_token(user["id"], ws["id"])
    # Read works (workspace comes from the token binding, no header needed).
    read = await client.get("/rest/v1/Sales?order=Revenue.desc", headers=_auth(dt))
    assert read.status_code == 200
    assert len(read.json()) == 3
    # Write is refused — the token is read-only.
    write = await client.post("/rest/v1/Sales", json={"Name": "X", "Revenue": 1}, headers=_auth(dt))
    assert write.status_code == 403
