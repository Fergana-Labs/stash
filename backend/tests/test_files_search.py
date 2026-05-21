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


@pytest.mark.asyncio
async def test_search_pages_finds_html_page_text(client: AsyncClient) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    workspace = (
        await client.post("/api/v1/workspaces", json={"name": "Searchable HTML"}, headers=headers)
    ).json()

    created = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/pages/new",
        json={
            "name": "HTML Guide",
            "content_type": "html",
            "content_html": "<main><h1>Release checklist</h1><p>has a sentinelhtmlword</p></main>",
        },
        headers=headers,
    )
    assert created.status_code == 201

    resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/pages/search",
        params={"q": "sentinelhtmlword", "limit": 10},
        headers=headers,
    )

    assert resp.status_code == 200
    pages = resp.json()["pages"]
    assert [page["name"] for page in pages] == ["HTML Guide"]
    assert pages[0]["content_type"] == "html"


@pytest.mark.asyncio
async def test_search_files_finds_workspace_files(client: AsyncClient, pool) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    workspace = (
        await client.post("/api/v1/workspaces", json={"name": "Searchable files"}, headers=headers)
    ).json()
    user = (await client.get("/api/v1/users/me", headers=headers)).json()

    await pool.execute(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, "
        "extracted_text, extraction_status) "
        "VALUES ($1, 'pricing-matrix.txt', 'text/plain', 36, $2, $3, $4, 'completed')",
        workspace["id"],
        f"{workspace['id']}/pricing-matrix.txt",
        user["id"],
        "enterprise pricing tiers",
    )

    resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/files/search",
        params={"q": "pricing", "limit": 10},
        headers=headers,
    )

    assert resp.status_code == 200
    files = resp.json()["files"]
    assert [file["name"] for file in files] == ["pricing-matrix.txt"]
    assert files[0]["search_text"] == "enterprise pricing tiers"
