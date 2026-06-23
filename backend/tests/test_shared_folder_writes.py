"""Writes into folders under the /me routing model.

A user only ever reaches their OWN scope through /api/v1/me/... Uploads and
moves therefore land in the caller's own scope; a folder_id always refers to a
folder the caller owns. Cross-user isolation: another user's folder is simply
not in your scope, so targeting it fails (400) — there is no membership/role
gate to trip anymore, and the upload endpoint has no canonical cross-scope
variant to write into someone else's folder.
"""

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


async def _folder(client: AsyncClient, api_key: str) -> str:
    resp = await client.post(
        "/api/v1/me/folders",
        json={"name": "Drop zone"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_owner_can_move_file_into_folder(client: AsyncClient, _db_pool, monkeypatch):
    """Regression: this PATCH 500'd (check_access called with a bad kwarg)."""

    # The response serializer resolves a download URL; S3 isn't configured in CI.
    async def _fake_url(storage_key: str) -> str:
        return f"https://files.test/{storage_key}"

    monkeypatch.setattr(storage_service, "get_file_url", _fake_url)

    api_key, _, user_id = await _register(client, "fmove_owner")
    folder_id = await _folder(client, api_key)

    file_id = await _db_pool.fetchval(
        "INSERT INTO files "
        "(owner_user_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, 'notes.txt', 'text/plain', 5, 'test/key', $1) RETURNING id",
        user_id,
    )

    resp = await client.patch(
        f"/api/v1/me/files/{file_id}",
        json={"folder_id": folder_id},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["folder_id"] == folder_id


@pytest.mark.asyncio
async def test_owner_can_upload_and_move_page_into_own_folder(client: AsyncClient):
    """Uploading markdown into a folder you own creates a page in that folder,
    and an existing page can be moved into it — all within the caller's scope."""
    owner_key, _, _ = await _register(client, "fown_owner")
    folder_id = await _folder(client, owner_key)

    # Markdown upload into the folder becomes a page in that folder.
    uploaded = await client.post(
        "/api/v1/me/files",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
        data={"folder_id": folder_id},
        headers=_auth(owner_key),
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["kind"] == "page"
    assert uploaded.json()["folder_id"] == folder_id

    # A loose page can be moved into the folder.
    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Loose doc"},
        headers=_auth(owner_key),
    )
    assert page.status_code == 201
    page_id = page.json()["id"]

    moved = await client.patch(
        f"/api/v1/me/pages/{page_id}",
        json={"folder_id": folder_id},
        headers=_auth(owner_key),
    )
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == folder_id


@pytest.mark.asyncio
async def test_stranger_cannot_upload_into_another_users_folder(client: AsyncClient):
    """Cross-user isolation: a folder owned by someone else is not in the
    caller's scope, so targeting it from /me/files fails. The stranger's own
    scope still accepts an unscoped upload."""
    owner_key, _, _ = await _register(client, "fiso_owner")
    stranger_key, _, _ = await _register(client, "fiso_stranger")
    folder_id = await _folder(client, owner_key)

    # The owner's folder_id does not belong to the stranger's scope.
    denied = await client.post(
        "/api/v1/me/files",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
        data={"folder_id": folder_id},
        headers=_auth(stranger_key),
    )
    assert denied.status_code == 400

    # An unscoped upload lands in the stranger's own root.
    rootless = await client.post(
        "/api/v1/me/files",
        files={"file": ("more.md", b"# hi", "text/markdown")},
        headers=_auth(stranger_key),
    )
    assert rootless.status_code == 201
    assert rootless.json()["kind"] == "page"
    assert rootless.json()["folder_id"] is None
