"""Tests for publishable (anon) keys + per-table policies on the data API."""

import uuid

import pytest
from httpx import AsyncClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _anon(key: str) -> dict[str, str]:
    # supabase-js sends the publishable key in the apikey header.
    return {"apikey": key}


async def _register(client: AsyncClient) -> str:
    name = f"user_{uuid.uuid4().hex[:10]}"
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "display_name": name, "password": "password123"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


async def _setup(client: AsyncClient):
    api_key = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Pub"}, headers=_auth(api_key))
    ).json()
    table = (
        await client.post(
            f"/api/v1/workspaces/{ws['id']}/tables",
            json={"name": "Leaderboard", "columns": [{"name": "Player", "type": "text"}]},
            headers=_auth(api_key),
        )
    ).json()
    hdr = {**_auth(api_key), "X-Stash-Workspace": ws["id"]}
    await client.post("/rest/v1/Leaderboard", json={"Player": "Ada"}, headers=hdr)
    return api_key, ws, table


async def _make_key(client: AsyncClient, api_key: str, ws_id: str) -> str:
    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/publishable-keys",
        json={"name": "site"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    key = resp.json()["key"]
    assert key.startswith("pk_")
    return key


@pytest.mark.asyncio
async def test_anon_key_grants_nothing_until_policy(client: AsyncClient):
    api_key, ws, _table = await _setup(client)
    pk = await _make_key(client, api_key, ws["id"])

    # No policy yet -> the anon key can't read the table.
    denied = await client.get("/rest/v1/Leaderboard", headers=_anon(pk))
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_read_policy_enables_read_not_write(client: AsyncClient):
    api_key, ws, table = await _setup(client)
    pk = await _make_key(client, api_key, ws["id"])
    keys = await client.get(
        f"/api/v1/workspaces/{ws['id']}/publishable-keys", headers=_auth(api_key)
    )
    key_id = keys.json()[0]["id"]

    # Grant read.
    policy = await client.put(
        f"/api/v1/workspaces/{ws['id']}/publishable-keys/{key_id}/policies",
        json={"table_id": table["id"], "permission": "read"},
        headers=_auth(api_key),
    )
    assert policy.status_code == 201

    read = await client.get("/rest/v1/Leaderboard", headers=_anon(pk))
    assert read.status_code == 200
    assert [r["Player"] for r in read.json()] == ["Ada"]

    # Read policy does not allow writes.
    write = await client.post("/rest/v1/Leaderboard", json={"Player": "Grace"}, headers=_anon(pk))
    assert write.status_code == 403


@pytest.mark.asyncio
async def test_write_policy_enables_anon_write(client: AsyncClient):
    api_key, ws, table = await _setup(client)
    pk = await _make_key(client, api_key, ws["id"])
    key_id = (
        await client.get(f"/api/v1/workspaces/{ws['id']}/publishable-keys", headers=_auth(api_key))
    ).json()[0]["id"]
    await client.put(
        f"/api/v1/workspaces/{ws['id']}/publishable-keys/{key_id}/policies",
        json={"table_id": table["id"], "permission": "write"},
        headers=_auth(api_key),
    )

    write = await client.post("/rest/v1/Leaderboard", json={"Player": "Grace"}, headers=_anon(pk))
    assert write.status_code == 201
    assert write.json()["Player"] == "Grace"


@pytest.mark.asyncio
async def test_only_owner_can_make_keys(client: AsyncClient):
    _owner_key, ws, _table = await _setup(client)
    outsider = await _register(client)
    resp = await client.post(
        f"/api/v1/workspaces/{ws['id']}/publishable-keys",
        json={"name": "x"},
        headers=_auth(outsider),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoked_key_is_rejected(client: AsyncClient):
    api_key, ws, table = await _setup(client)
    pk = await _make_key(client, api_key, ws["id"])
    key_id = (
        await client.get(f"/api/v1/workspaces/{ws['id']}/publishable-keys", headers=_auth(api_key))
    ).json()[0]["id"]
    await client.put(
        f"/api/v1/workspaces/{ws['id']}/publishable-keys/{key_id}/policies",
        json={"table_id": table["id"], "permission": "read"},
        headers=_auth(api_key),
    )
    assert (await client.get("/rest/v1/Leaderboard", headers=_anon(pk))).status_code == 200

    await client.delete(
        f"/api/v1/workspaces/{ws['id']}/publishable-keys/{key_id}", headers=_auth(api_key)
    )
    assert (await client.get("/rest/v1/Leaderboard", headers=_anon(pk))).status_code == 401
