import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_search_pages_finds_workspace_pages(client: AsyncClient) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    workspace = (
        await client.post("/api/v1/workspaces", json={"name": "Searchable"}, headers=headers)
    ).json()

    alpha = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/pages/new",
        json={"name": "Alpha", "content": "alpha result lives here"},
        headers=headers,
    )
    assert alpha.status_code == 201
    beta = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/pages/new",
        json={"name": "Beta", "content": "nothing relevant"},
        headers=headers,
    )
    assert beta.status_code == 201

    resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/pages/search",
        params={"q": "alpha", "limit": 10},
        headers=headers,
    )

    assert resp.status_code == 200
    pages = resp.json()["pages"]
    assert [page["name"] for page in pages] == ["Alpha"]
