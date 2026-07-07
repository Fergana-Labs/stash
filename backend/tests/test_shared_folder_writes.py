"""Writes into folders under the /me routing model.

An upload or page create lands in the scope that OWNS the target folder: your
own folders always accept, and another user's folder accepts if it (or an
ancestor) is shared with you with write permission — the content is owned by
the folder's owner and attributed to you via uploaded_by/created_by. Without a
write share, targeting someone else's folder fails 403. This is how multiple
people contribute to one company brain (e.g. two founders uploading docs into
a shared knowledge folder) without an org entity.
"""

from uuid import UUID

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


async def _share_folder(pool, folder_id: str, owner_id: str, user_id: str, permission: str):
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1, 'folder', $2, 'user', $3, $4, $1)",
        UUID(owner_id),
        UUID(folder_id),
        UUID(user_id),
        permission,
    )


@pytest.mark.asyncio
async def test_stranger_cannot_upload_into_another_users_folder(client: AsyncClient):
    """Without a write share, someone else's folder refuses the upload. The
    stranger's own scope still accepts an unscoped upload."""
    owner_key, _, _ = await _register(client, "fiso_owner")
    stranger_key, _, _ = await _register(client, "fiso_stranger")
    folder_id = await _folder(client, owner_key)

    denied = await client.post(
        "/api/v1/me/files",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
        data={"folder_id": folder_id},
        headers=_auth(stranger_key),
    )
    assert denied.status_code == 403

    # An unscoped upload lands in the stranger's own root.
    rootless = await client.post(
        "/api/v1/me/files",
        files={"file": ("more.md", b"# hi", "text/markdown")},
        headers=_auth(stranger_key),
    )
    assert rootless.status_code == 201
    assert rootless.json()["kind"] == "page"
    assert rootless.json()["folder_id"] is None


@pytest.mark.asyncio
async def test_write_share_allows_upload_into_owners_folder(client: AsyncClient, _db_pool):
    """A write share on a folder lets a non-owner upload into it: the content
    belongs to the folder's owner and is attributed to the uploader."""
    owner_key, _, owner_id = await _register(client, "fws_owner")
    writer_key, _, writer_id = await _register(client, "fws_writer")
    folder_id = await _folder(client, owner_key)
    await _share_folder(_db_pool, folder_id, owner_id, writer_id, "write")

    uploaded = await client.post(
        "/api/v1/me/files",
        files={"file": ("cheatsheet.md", b"# brake parts", "text/markdown")},
        data={"folder_id": folder_id},
        headers=_auth(writer_key),
    )
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["owner_user_id"] == owner_id
    assert body["created_by"] == writer_id
    assert body["folder_id"] == folder_id

    # The owner sees the contributed page in their folder.
    contents = await client.get(
        f"/api/v1/me/folders/{folder_id}/contents",
        headers=_auth(owner_key),
    )
    assert contents.status_code == 200
    assert any(p["name"] == "cheatsheet" for p in contents.json()["pages"])


@pytest.mark.asyncio
async def test_write_share_cascades_to_subfolders(client: AsyncClient, _db_pool):
    """Sharing a folder with write permission covers its subfolders too."""
    owner_key, _, owner_id = await _register(client, "fwc_owner")
    writer_key, _, writer_id = await _register(client, "fwc_writer")
    parent_id = await _folder(client, owner_key)
    sub = await client.post(
        "/api/v1/me/folders",
        json={"name": "Sub", "parent_folder_id": parent_id},
        headers=_auth(owner_key),
    )
    assert sub.status_code == 201
    await _share_folder(_db_pool, parent_id, owner_id, writer_id, "write")

    uploaded = await client.post(
        "/api/v1/me/files",
        files={"file": ("nested.md", b"# nested", "text/markdown")},
        data={"folder_id": sub.json()["id"]},
        headers=_auth(writer_key),
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["owner_user_id"] == owner_id


@pytest.mark.asyncio
async def test_read_share_does_not_allow_upload(client: AsyncClient, _db_pool):
    owner_key, _, owner_id = await _register(client, "frs_owner")
    reader_key, _, reader_id = await _register(client, "frs_reader")
    folder_id = await _folder(client, owner_key)
    await _share_folder(_db_pool, folder_id, owner_id, reader_id, "read")

    denied = await client.post(
        "/api/v1/me/files",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
        data={"folder_id": folder_id},
        headers=_auth(reader_key),
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_write_share_allows_page_create_in_owners_folder(client: AsyncClient, _db_pool):
    owner_key, _, owner_id = await _register(client, "fpc_owner")
    writer_key, _, writer_id = await _register(client, "fpc_writer")
    folder_id = await _folder(client, owner_key)
    await _share_folder(_db_pool, folder_id, owner_id, writer_id, "write")

    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Field notes", "folder_id": folder_id},
        headers=_auth(writer_key),
    )
    assert page.status_code == 201, page.text
    assert page.json()["owner_user_id"] == owner_id
    assert page.json()["created_by"] == writer_id
