"""The canonical page/file/session endpoints resolve the workspace
server-side so item links carry only the item ID and can never go stale.
Same contract as the canonical table endpoint: membership-gated, and every
failure is a 404 so an unscoped probe can't confirm an item exists."""

import uuid

import pytest
from httpx import AsyncClient

from ..config import settings
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


async def _new_workspace(client: AsyncClient, api_key: str) -> str:
    resp = await client.post(
        "/api/v1/workspaces", json={"name": "Canonical items"}, headers=_auth(api_key)
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_page(client: AsyncClient, api_key: str, workspace_id: str) -> str:
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/pages/new",
        json={"name": "Notes", "content": "# hello"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# The test environment has no S3 (see test_copy.py), so file rows are
# inserted directly and only the resolve-and-gate behavior is pinned here —
# the success path's response building needs storage and stays uncovered,
# like every other file-success path in this suite's environment.
async def _insert_file_row(pool, workspace_id: str) -> str:
    uploader = await pool.fetchval(
        "SELECT creator_id FROM workspaces WHERE id = $1",
        uuid.UUID(workspace_id),
    )
    return str(
        await pool.fetchval(
            "INSERT INTO files (workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
            "VALUES ($1, 'report.pdf', 'application/pdf', 13, 'test/fake-key', $2) RETURNING id",
            uuid.UUID(workspace_id),
            uploader,
        )
    )


async def _create_session(client: AsyncClient, api_key: str, workspace_id: str) -> str:
    session_id = f"sess-{uuid.uuid4()}"
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sessions",
        json={"session_id": session_id, "agent_name": "claude"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return session_id


@pytest.mark.asyncio
async def test_member_resolves_page_by_id_alone(client: AsyncClient):
    api_key = await _register(client)
    workspace_id = await _new_workspace(client, api_key)
    page_id = await _create_page(client, api_key, workspace_id)

    resp = await client.get(f"/api/v1/pages/{page_id}", headers=_auth(api_key))

    assert resp.status_code == 200
    assert resp.json()["id"] == page_id
    assert resp.json()["workspace_id"] == workspace_id


@pytest.mark.asyncio
async def test_non_member_page_lookup_is_404_not_403(client: AsyncClient):
    owner_key = await _register(client)
    workspace_id = await _new_workspace(client, owner_key)
    page_id = await _create_page(client, owner_key, workspace_id)
    outsider_key = await _register(client)

    resp = await client.get(f"/api/v1/pages/{page_id}", headers=_auth(outsider_key))

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_member_file_lookup_is_404_not_403(client: AsyncClient, pool):
    owner_key = await _register(client)
    workspace_id = await _new_workspace(client, owner_key)
    file_id = await _insert_file_row(pool, workspace_id)
    outsider_key = await _register(client)

    resp = await client.get(f"/api/v1/files/{file_id}", headers=_auth(outsider_key))

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_member_resolves_session_by_external_id_alone(client: AsyncClient):
    api_key = await _register(client)
    workspace_id = await _new_workspace(client, api_key)
    session_id = await _create_session(client, api_key, workspace_id)

    resp = await client.get(f"/api/v1/sessions/{session_id}", headers=_auth(api_key))

    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id
    assert resp.json()["workspace_id"] == workspace_id
    # The record link must point at the web app (PUBLIC_URL), not the API host,
    # so the plugin can hand it back as a clickable session URL.
    assert resp.json()["app_url"] == f"{settings.PUBLIC_URL.rstrip('/')}/sessions/{session_id}"


@pytest.mark.asyncio
async def test_session_id_in_two_workspaces_resolves_to_readable_one(client: AsyncClient):
    """session_id is unique per workspace, not globally. When the same id
    exists in a workspace the caller can't read, the lookup must skip it
    rather than 404 or leak it."""
    owner_a = await _register(client)
    ws_a = await _new_workspace(client, owner_a)
    owner_b = await _register(client)
    ws_b = await _new_workspace(client, owner_b)

    session_id = f"sess-{uuid.uuid4()}"
    for key, ws in ((owner_a, ws_a), (owner_b, ws_b)):
        resp = await client.post(
            f"/api/v1/workspaces/{ws}/sessions",
            json={"session_id": session_id, "agent_name": "claude"},
            headers=_auth(key),
        )
        assert resp.status_code == 201

    resp = await client.get(f"/api/v1/sessions/{session_id}", headers=_auth(owner_a))

    assert resp.status_code == 200
    assert resp.json()["workspace_id"] == ws_a


@pytest.mark.asyncio
async def test_non_member_session_lookup_is_404(client: AsyncClient):
    owner_key = await _register(client)
    workspace_id = await _new_workspace(client, owner_key)
    session_id = await _create_session(client, owner_key, workspace_id)
    outsider_key = await _register(client)

    resp = await client.get(f"/api/v1/sessions/{session_id}", headers=_auth(outsider_key))

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unknown_ids_get_404(client: AsyncClient):
    api_key = await _register(client)

    for path in (f"/api/v1/pages/{uuid.uuid4()}", f"/api/v1/files/{uuid.uuid4()}"):
        resp = await client.get(path, headers=_auth(api_key))
        assert resp.status_code == 404

    resp = await client.get("/api/v1/sessions/never-existed", headers=_auth(api_key))
    assert resp.status_code == 404
