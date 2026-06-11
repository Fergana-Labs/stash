"""Writes into folders: member moves, and non-member writes via write shares."""

import pytest
from httpx import AsyncClient

from backend.services import storage_service

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, prefix: str) -> tuple[str, str, str]:
    """Returns (api_key, name, user_id)."""
    name = unique_name(prefix)
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1", "email": f"{name}@test.local"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], name, body["id"]


async def _workspace(client: AsyncClient, api_key: str) -> str:
    resp = await client.post(
        "/api/v1/workspaces", json={"name": "Folder Writes"}, headers=_auth(api_key)
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _folder(client: AsyncClient, api_key: str, workspace_id: str) -> str:
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/folders",
        json={"name": "Drop zone"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _share_folder(
    client: AsyncClient, owner_key: str, folder_id: str, email: str, permission: str
) -> None:
    resp = await client.post(
        "/api/v1/share",
        json={
            "object_type": "folder",
            "object_id": folder_id,
            "email": email,
            "permission": permission,
        },
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_member_can_move_file_into_folder(client: AsyncClient, _db_pool, monkeypatch):
    """Regression: this PATCH 500'd (check_access called with a bad kwarg)."""

    # The response serializer resolves a download URL; S3 isn't configured in CI.
    async def _fake_url(storage_key: str) -> str:
        return f"https://files.test/{storage_key}"

    monkeypatch.setattr(storage_service, "get_file_url", _fake_url)

    api_key, _, user_id = await _register(client, "fmove_owner")
    ws = await _workspace(client, api_key)
    folder_id = await _folder(client, api_key, ws)

    file_id = await _db_pool.fetchval(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, 'notes.txt', 'text/plain', 5, 'test/key', $2) RETURNING id",
        ws,
        user_id,
    )

    resp = await client.patch(
        f"/api/v1/workspaces/{ws}/files/{file_id}",
        json={"folder_id": folder_id},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["folder_id"] == folder_id


@pytest.mark.asyncio
async def test_write_share_allows_upload_and_move_into_shared_folder(client: AsyncClient):
    owner_key, _, _ = await _register(client, "fshare_owner")
    guest_key, guest_name, _ = await _register(client, "fshare_guest")
    ws = await _workspace(client, owner_key)
    folder_id = await _folder(client, owner_key, ws)

    # Before the share: a non-member can't upload at all.
    denied = await client.post(
        f"/api/v1/workspaces/{ws}/files",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
        data={"folder_id": folder_id},
        headers=_auth(guest_key),
    )
    assert denied.status_code == 403

    await _share_folder(client, owner_key, folder_id, f"{guest_name}@test.local", "write")

    # Markdown upload into the shared folder becomes a page in that folder.
    uploaded = await client.post(
        f"/api/v1/workspaces/{ws}/files",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
        data={"folder_id": folder_id},
        headers=_auth(guest_key),
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["kind"] == "page"
    assert uploaded.json()["folder_id"] == folder_id

    # Upload without a target folder stays forbidden for non-members.
    rootless = await client.post(
        f"/api/v1/workspaces/{ws}/files",
        files={"file": ("more.md", b"# hi", "text/markdown")},
        headers=_auth(guest_key),
    )
    assert rootless.status_code == 403

    # A page shared writable with the guest can be moved into the folder
    # (the share on the folder cascades to its contents).
    page = await client.post(
        f"/api/v1/workspaces/{ws}/pages/new",
        json={"name": "Loose doc"},
        headers=_auth(owner_key),
    )
    assert page.status_code == 201
    page_id = page.json()["id"]
    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": f"{guest_name}@test.local",
            "permission": "write",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    moved = await client.patch(
        f"/api/v1/workspaces/{ws}/pages/{page_id}",
        json={"folder_id": folder_id},
        headers=_auth(guest_key),
    )
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == folder_id


@pytest.mark.asyncio
async def test_read_share_does_not_allow_upload(client: AsyncClient):
    owner_key, _, _ = await _register(client, "fread_owner")
    guest_key, guest_name, _ = await _register(client, "fread_guest")
    ws = await _workspace(client, owner_key)
    folder_id = await _folder(client, owner_key, ws)
    await _share_folder(client, owner_key, folder_id, f"{guest_name}@test.local", "read")

    resp = await client.post(
        f"/api/v1/workspaces/{ws}/files",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
        data={"folder_id": folder_id},
        headers=_auth(guest_key),
    )
    assert resp.status_code == 403
