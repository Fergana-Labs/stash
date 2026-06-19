"""Tests for scope (workspace) CRUD and owner enforcement.

The multi-tenant membership/invite model is gone: each user owns exactly one
scope (owner == workspaces.creator_id). Cross-user access is only via shares.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    """Register a user. Returns (api_key, response_body)."""
    name = name or unique_name()
    resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": name,
            "password": "securepassword1",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# --- Creation ---


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient):
    key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/workspaces",
        json={
            "name": "My Workspace",
            "description": "desc",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Workspace"
    assert body["invite_code"]
    assert body["member_count"] == 1


@pytest.mark.asyncio
async def test_create_workspace_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/workspaces", json={"name": "X"})
    assert resp.status_code == 401


# --- Listing ---


@pytest.mark.asyncio
async def test_list_my_workspaces(client: AsyncClient):
    key, _ = await _register(client)
    h = _auth(key)
    await client.post("/api/v1/workspaces", json={"name": "WS1"}, headers=h)
    await client.post("/api/v1/workspaces", json={"name": "WS2"}, headers=h)

    resp = await client.get("/api/v1/workspaces/mine", headers=h)
    assert resp.status_code == 200
    # Registration auto-provisions a default workspace, so WS1/WS2 come alongside it.
    names = {w["name"] for w in resp.json()["workspaces"]}
    assert {"WS1", "WS2"}.issubset(names)


@pytest.mark.asyncio
async def test_registration_auto_provisions_default_workspace(client: AsyncClient):
    key, body = await _register(client)
    resp = await client.get("/api/v1/workspaces/mine", headers=_auth(key))
    assert resp.status_code == 200
    workspaces = resp.json()["workspaces"]
    assert len(workspaces) == 1
    assert workspaces[0]["name"] == "Stash"
    assert workspaces[0]["member_count"] == 1


@pytest.mark.asyncio
async def test_non_owner_cannot_read_workspace(client: AsyncClient):
    owner_key, _ = await _register(client)
    stranger_key, _ = await _register(client)
    workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Private Team"},
            headers=_auth(owner_key),
        )
    ).json()

    response = await client.get(
        f"/api/v1/workspaces/{workspace['id']}",
        headers=_auth(stranger_key),
    )

    assert response.status_code == 404


# --- Update / Delete ---


@pytest.mark.asyncio
async def test_update_workspace(client: AsyncClient):
    key, _ = await _register(client)
    ws = (await client.post("/api/v1/workspaces", json={"name": "Old"}, headers=_auth(key))).json()

    resp = await client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        json={"name": "New"},
        headers=_auth(key),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


@pytest.mark.asyncio
async def test_non_owner_cannot_update_workspace(client: AsyncClient):
    owner_key, _ = await _register(client)
    stranger_key, _ = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()

    resp = await client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        json={"name": "Hacked"},
        headers=_auth(stranger_key),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_workspace(client: AsyncClient):
    key, _ = await _register(client)
    ws = (await client.post("/api/v1/workspaces", json={"name": "Temp"}, headers=_auth(key))).json()

    resp = await client.delete(f"/api/v1/workspaces/{ws['id']}", headers=_auth(key))
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/workspaces/{ws['id']}", headers=_auth(key))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_owner_cannot_delete_workspace(client: AsyncClient):
    owner_key, _ = await _register(client)
    stranger_key, _ = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()

    resp = await client.delete(f"/api/v1/workspaces/{ws['id']}", headers=_auth(stranger_key))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_workspace_deletes_stored_files_and_session_artifacts(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    key, user = await _register(client)
    ws = (await client.post("/api/v1/workspaces", json={"name": "Temp"}, headers=_auth(key))).json()
    workspace_id = UUID(ws["id"])
    user_id = UUID(user["id"])

    await pool.execute(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        workspace_id,
        "plans.pdf",
        "application/pdf",
        12,
        "file-key",
        user_id,
    )
    session_row_id = await pool.fetchval(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id",
        workspace_id,
        "sess-workspace-delete",
        "codex",
        user_id,
    )
    await pool.execute(
        "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, $2, $3, $4)",
        session_row_id,
        "artifact.txt",
        "artifact-key",
        42,
    )

    deleted_keys: list[str] = []

    async def fake_delete_file(storage_key: str) -> None:
        # Blobs are purged only after the DB delete commits — a failed delete
        # must never leave live rows pointing at destroyed storage objects.
        assert (
            await pool.fetchval("SELECT COUNT(*) FROM workspaces WHERE id = $1", workspace_id) == 0
        )
        deleted_keys.append(storage_key)

    monkeypatch.setattr("backend.routers.workspaces.storage_service.delete_file", fake_delete_file)

    resp = await client.delete(f"/api/v1/workspaces/{ws['id']}", headers=_auth(key))
    assert resp.status_code == 204
    assert deleted_keys == ["artifact-key", "file-key"]
    assert (
        await pool.fetchval("SELECT COUNT(*) FROM files WHERE workspace_id = $1", workspace_id) == 0
    )
    assert (
        await pool.fetchval("SELECT COUNT(*) FROM sessions WHERE workspace_id = $1", workspace_id)
        == 0
    )


@pytest.mark.asyncio
async def test_delete_workspace_keeps_storage_keys_referenced_by_other_workspaces(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    key, user = await _register(client)
    first = (
        await client.post("/api/v1/workspaces", json={"name": "First"}, headers=_auth(key))
    ).json()
    second = (
        await client.post("/api/v1/workspaces", json={"name": "Second"}, headers=_auth(key))
    ).json()
    first_workspace_id = UUID(first["id"])
    second_workspace_id = UUID(second["id"])
    user_id = UUID(user["id"])

    for workspace_id, name, storage_key in [
        (first_workspace_id, "first-plan.pdf", "shared-file-key"),
        (first_workspace_id, "first-private.pdf", "first-private-file-key"),
        (second_workspace_id, "second-plan.pdf", "shared-file-key"),
    ]:
        await pool.execute(
            "INSERT INTO files "
            "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            workspace_id,
            name,
            "application/pdf",
            12,
            storage_key,
            user_id,
        )

    first_session_id = await pool.fetchval(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id",
        first_workspace_id,
        "first-session",
        "codex",
        user_id,
    )
    second_session_id = await pool.fetchval(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id",
        second_workspace_id,
        "second-session",
        "codex",
        user_id,
    )
    for session_id, file_path, storage_key in [
        (first_session_id, "private.txt", "first-private-artifact-key"),
        (first_session_id, "shared.txt", "shared-artifact-key"),
        (second_session_id, "shared.txt", "shared-artifact-key"),
    ]:
        await pool.execute(
            "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
            "VALUES ($1, $2, $3, $4)",
            session_id,
            file_path,
            storage_key,
            42,
        )

    deleted_keys: list[str] = []

    async def fake_delete_file(storage_key: str) -> None:
        deleted_keys.append(storage_key)

    monkeypatch.setattr("backend.routers.workspaces.storage_service.delete_file", fake_delete_file)

    resp = await client.delete(f"/api/v1/workspaces/{first['id']}", headers=_auth(key))

    assert resp.status_code == 204
    assert deleted_keys == ["first-private-artifact-key", "first-private-file-key"]
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM files WHERE workspace_id = $1",
            first_workspace_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM files WHERE workspace_id = $1",
            second_workspace_id,
        )
        == 1
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
            second_session_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_new_page_button_never_collides(client: AsyncClient):
    """The 'New page' button always sends 'Untitled'. Clicking it repeatedly must
    keep working: each new page gets the next free name instead of a 409."""
    key, _ = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Pages"}, headers=_auth(key))
    ).json()

    names = []
    for _ in range(3):
        resp = await client.post(
            f"/api/v1/workspaces/{ws['id']}/pages/new",
            json={"name": "Untitled"},
            headers=_auth(key),
        )
        assert resp.status_code == 201
        names.append(resp.json()["name"])

    assert names == ["Untitled", "Untitled (2)", "Untitled (3)"]
