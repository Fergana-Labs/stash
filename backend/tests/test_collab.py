import asyncio
import uuid

import pytest
from httpx import AsyncClient

from backend.services import files_tree_service


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> tuple[str, dict]:
    name = f"user_{uuid.uuid4().hex[:10]}"
    response = await client.post(
        "/api/v1/users/register",
        json={"name": name, "display_name": name, "password": "password123"},
    )
    assert response.status_code == 201
    body = response.json()
    return body["api_key"], body


async def _scope_id(client: AsyncClient, api_key: str) -> str:
    response = await client.get("/api/v1/users/me", headers=_auth(api_key))
    assert response.status_code == 200
    return response.json()["id"]


@pytest.mark.asyncio
async def test_collab_authorizes_markdown_page_writer(client: AsyncClient):
    api_key, _user = await _register(client)
    scope_id = await _scope_id(client, api_key)
    page = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Plan", "content": "# Draft"},
            headers=_auth(api_key),
        )
    ).json()

    response = await client.post(
        "/api/v1/collab/authorize",
        json={"document_name": f"scope:{scope_id}:page:{page['id']}"},
        headers=_auth(api_key),
    )

    assert response.status_code == 200
    assert response.json()["can_write"] is True


@pytest.mark.asyncio
async def test_collab_authorizes_read_share_as_read_only(
    client: AsyncClient,
    pool,
):
    owner_key, _owner = await _register(client)
    viewer_key, viewer = await _register(client)
    owner_scope_id = await _scope_id(client, owner_key)
    page = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Plan", "content": "# Draft"},
            headers=_auth(owner_key),
        )
    ).json()
    await pool.execute(
        """
        INSERT INTO shares (owner_user_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by)
        VALUES ($1, 'page', $2, 'user', $3, 'read', $4)
        """,
        uuid.UUID(owner_scope_id),
        uuid.UUID(page["id"]),
        uuid.UUID(viewer["id"]),
        uuid.UUID(_owner["id"]),
    )

    response = await client.post(
        "/api/v1/collab/authorize",
        json={"document_name": f"scope:{owner_scope_id}:page:{page['id']}"},
        headers=_auth(viewer_key),
    )

    assert response.status_code == 200
    assert response.json()["can_write"] is False


@pytest.mark.asyncio
async def test_collab_authorizes_non_member_with_page_share(
    client: AsyncClient,
    pool,
):
    """A page shared directly with a non-member grants live-edit access:
    membership is not required, the share decides read/write."""
    owner_key, _owner = await _register(client)
    editor_key, editor = await _register(client)
    owner_scope_id = await _scope_id(client, owner_key)
    page = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Plan", "content": "# Draft"},
            headers=_auth(owner_key),
        )
    ).json()
    await pool.execute(
        """
        INSERT INTO shares (owner_user_id, object_type, object_id, principal_type,
                            principal_id, permission, created_by)
        VALUES ($1, 'page', $2, 'user', $3, 'write', $4)
        """,
        uuid.UUID(owner_scope_id),
        uuid.UUID(page["id"]),
        uuid.UUID(editor["id"]),
        uuid.UUID(_owner["id"]),
    )

    response = await client.post(
        "/api/v1/collab/authorize",
        json={"document_name": f"scope:{owner_scope_id}:page:{page['id']}"},
        headers=_auth(editor_key),
    )

    assert response.status_code == 200
    assert response.json()["can_write"] is True


@pytest.mark.asyncio
async def test_collab_rejects_user_without_access(
    client: AsyncClient,
):
    """A user who is neither a member nor a sharee is rejected outright."""
    owner_key, _owner = await _register(client)
    outsider_key, _outsider = await _register(client)
    owner_scope_id = await _scope_id(client, owner_key)
    page = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Plan", "content": "# Draft"},
            headers=_auth(owner_key),
        )
    ).json()

    response = await client.post(
        "/api/v1/collab/authorize",
        json={"document_name": f"scope:{owner_scope_id}:page:{page['id']}"},
        headers=_auth(outsider_key),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_collab_rejects_html_pages(client: AsyncClient):
    api_key, _user = await _register(client)
    scope_id = await _scope_id(client, api_key)
    page = (
        await client.post(
            "/api/v1/me/pages/new",
            json={
                "name": "Demo",
                "content_type": "html",
                "content_html": "<h1>Demo</h1>",
            },
            headers=_auth(api_key),
        )
    ).json()

    response = await client.post(
        "/api/v1/collab/authorize",
        json={"document_name": f"scope:{scope_id}:page:{page['id']}"},
        headers=_auth(api_key),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_collab_projection_save_disables_content_hash_guard(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    api_key, _user = await _register(client)
    page = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Plan", "content": "# Draft"},
            headers=_auth(api_key),
        )
    ).json()

    async def update_page_with_conflict(*args, **kwargs):
        assert kwargs["guard_content_hash"] is False
        return {**page, "content_markdown": kwargs["content"]}

    monkeypatch.setattr(files_tree_service, "update_page", update_page_with_conflict)

    response = await client.patch(
        f"/api/v1/me/pages/{page['id']}",
        json={"content": "CRDT projection", "collab_projection": True},
        headers=_auth(api_key),
    )

    assert response.status_code == 200
    assert response.json()["content_markdown"] == "CRDT projection"


@pytest.mark.asyncio
async def test_concurrent_collab_projection_saves_do_not_500(client: AsyncClient):
    api_key, _user = await _register(client)
    page = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Plan", "content": "# Draft"},
            headers=_auth(api_key),
        )
    ).json()

    async def save_projection(index: int):
        return await client.patch(
            f"/api/v1/me/pages/{page['id']}",
            json={"content": f"CRDT projection {index}", "collab_projection": True},
            headers=_auth(api_key),
        )

    responses = await asyncio.gather(*(save_projection(i) for i in range(12)))

    assert [response.status_code for response in responses] == [200] * 12
