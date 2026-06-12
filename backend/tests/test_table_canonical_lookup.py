"""The canonical table endpoint resolves the workspace server-side so
table links carry only the table ID and can never go stale."""

import uuid

import pytest
from httpx import AsyncClient

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("canon"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


async def _table_in_new_workspace(client: AsyncClient, api_key: str) -> tuple[str, str]:
    headers = _auth(api_key)
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Canonical lookup"}, headers=headers
    )
    assert ws_resp.status_code == 201
    workspace_id = ws_resp.json()["id"]

    table_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/tables",
        json={
            "name": "Prospects",
            "columns": [{"id": "col_name", "name": "Name", "type": "text"}],
        },
        headers=headers,
    )
    assert table_resp.status_code == 201
    return workspace_id, table_resp.json()["id"]


@pytest.mark.asyncio
async def test_member_resolves_table_by_id_alone(client: AsyncClient):
    api_key = await _register(client)
    workspace_id, table_id = await _table_in_new_workspace(client, api_key)

    resp = await client.get(f"/api/v1/tables/{table_id}", headers=_auth(api_key))

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == table_id
    assert body["workspace_id"] == workspace_id
    assert body["columns"][0]["id"] == "col_name"


@pytest.mark.asyncio
async def test_column_width_updates_table_metadata(client: AsyncClient):
    api_key = await _register(client)
    workspace_id, table_id = await _table_in_new_workspace(client, api_key)

    resp = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/tables/{table_id}/columns/col_name",
        json={"width": 260},
        headers=_auth(api_key),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"][0]["width"] == 260


@pytest.mark.asyncio
async def test_non_member_gets_404_not_403(client: AsyncClient):
    owner_key = await _register(client)
    _, table_id = await _table_in_new_workspace(client, owner_key)
    outsider_key = await _register(client)

    resp = await client.get(f"/api/v1/tables/{table_id}", headers=_auth(outsider_key))

    # 404, not 403: an unscoped lookup must not confirm the table exists.
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unknown_table_gets_404(client: AsyncClient):
    api_key = await _register(client)

    resp = await client.get(f"/api/v1/tables/{uuid.uuid4()}", headers=_auth(api_key))

    assert resp.status_code == 404
