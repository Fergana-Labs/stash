import io

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, str]:
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert response.status_code == 201
    return response.json()["api_key"], response.json()["id"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_uploaded_items_exclude_memory_and_embedded_assets(client: AsyncClient, pool) -> None:
    api_key, user_id = await _register(client)
    headers = _auth(api_key)

    memory = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Agent memory", "content": "Created by an agent"},
        headers=headers,
    )
    assert memory.status_code == 201

    uploaded_page = await client.post(
        "/api/v1/me/files",
        files={"file": ("brief.md", io.BytesIO(b"# User context"), "text/markdown")},
        headers=headers,
    )
    assert uploaded_page.status_code == 201

    uploaded_file_id = await pool.fetchval(
        "INSERT INTO files "
        "(owner_user_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, 'evidence.pdf', 'application/pdf', 42, 'evidence-key', $1) "
        "RETURNING id",
        user_id,
    )
    await pool.execute(
        "INSERT INTO files "
        "(owner_user_id, owner_page_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, 'inline.png', 'image/png', 10, 'inline-key', $1)",
        user_id,
        uploaded_page.json()["id"],
    )

    response = await client.get("/api/v1/me/files/uploads", headers=headers)

    assert response.status_code == 200
    assert [(item["kind"], item["name"]) for item in response.json()["items"]] == [
        ("file", "evidence.pdf"),
        ("page", "brief.md"),
    ]
    assert response.json()["items"][0]["id"] == str(uploaded_file_id)

    page_metadata = await pool.fetchval(
        "SELECT metadata FROM pages WHERE id = $1",
        uploaded_page.json()["id"],
    )
    assert page_metadata == {"upload": {"filename": "brief.md", "size_bytes": 14}}
