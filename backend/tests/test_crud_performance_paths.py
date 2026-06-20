"""Regression coverage for the high-volume CRUD paths."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("crud"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


async def _workspace(client: AsyncClient, api_key: str) -> dict:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "CRUD performance"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_batch_row_create_and_update_preserve_order(client: AsyncClient):
    api_key = await _register(client)
    headers = _auth(api_key)

    table_resp = await client.post(
        "/api/v1/me/tables",
        json={
            "name": "Bulk rows",
            "columns": [
                {"id": "col_name", "name": "Name", "type": "text"},
                {"id": "col_score", "name": "Score", "type": "number"},
            ],
        },
        headers=headers,
    )
    assert table_resp.status_code == 201
    table_id = table_resp.json()["id"]

    create_resp = await client.post(
        f"/api/v1/me/tables/{table_id}/rows/batch",
        json={"rows": [{"data": {"col_name": f"row-{i}", "col_score": i}} for i in range(250)]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["rows"]
    assert [row["row_order"] for row in created[:5]] == [0, 1, 2, 3, 4]
    assert created[-1]["row_order"] == 249

    selected = list(reversed(created[10:20]))
    update_resp = await client.post(
        f"/api/v1/me/tables/{table_id}/rows/update",
        json={
            "rows": [
                {"row_id": row["id"], "data": {"col_name": f"updated-{i}"}}
                for i, row in enumerate(selected)
            ]
        },
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["rows"]
    assert [row["id"] for row in updated] == [row["id"] for row in selected]
    assert [row["data"]["col_name"] for row in updated] == [
        f"updated-{i}" for i in range(len(selected))
    ]


@pytest.mark.asyncio
async def test_page_listing_ignores_trashed_pages(client: AsyncClient):
    api_key = await _register(client)
    headers = _auth(api_key)

    page_resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Draft", "content": "temporary"},
        headers=headers,
    )
    assert page_resp.status_code == 201
    page_id = page_resp.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/me/pages/{page_id}",
        headers=headers,
    )
    assert delete_resp.status_code == 204

    pages_resp = await client.get(
        "/api/v1/me/pages",
        headers=headers,
    )
    assert pages_resp.status_code == 200
    assert pages_resp.json()["pages"] == []
