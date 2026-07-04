"""Files attached to pages (files.parent_page_id).

An image pasted into a page uploads with parent_page_id, nests under the
page in tree views, and follows the page through trash/restore/purge. A
file has exactly one parent — folder OR page — enforced by the
files_single_parent CHECK constraint.
"""

import pytest
from httpx import AsyncClient

from backend.services import storage_service
from backend.tasks import extraction

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, prefix: str) -> tuple[str, str]:
    """Returns (api_key, user_id)."""
    name = unique_name(prefix)
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1", "email": f"{name}@test.local"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body["id"]


async def _page(client: AsyncClient, api_key: str, name: str = "Doc") -> str:
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": name},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _folder(client: AsyncClient, api_key: str) -> str:
    resp = await client.post(
        "/api/v1/me/folders",
        json={"name": "Drop zone"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def stub_storage(monkeypatch):
    """Binary uploads need storage + the extraction task; CI has neither."""

    async def _upload(owner_user_id, filename, content, content_type):
        return f"test/{owner_user_id}/{filename}"

    async def _url(storage_key):
        return f"https://files.test/{storage_key}"

    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(extraction.extract_file_text, "delay", lambda *a, **k: None)


async def _upload_image(
    client: AsyncClient, api_key: str, data: dict | None = None, name: str = "shot.png"
):
    return await client.post(
        "/api/v1/me/files",
        files={"file": (name, b"\x89PNG fake", "image/png")},
        data=data or {},
        headers=_auth(api_key),
    )


@pytest.mark.asyncio
async def test_upload_with_parent_page_attaches(client: AsyncClient, stub_storage):
    api_key, _ = await _register(client, "attach_up")
    page_id = await _page(client, api_key)

    resp = await _upload_image(client, api_key, {"parent_page_id": page_id})
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "file"
    assert body["parent_page_id"] == page_id
    assert body["folder_id"] is None

    # The overview tree carries the parent so clients can nest the file.
    overview = await client.get("/api/v1/me/overview", headers=_auth(api_key))
    assert overview.status_code == 200
    files = overview.json()["files"]["files"]
    assert [f["parent_page_id"] for f in files] == [page_id]


@pytest.mark.asyncio
async def test_upload_rejects_two_parents_and_foreign_pages(client: AsyncClient, stub_storage):
    api_key, _ = await _register(client, "attach_bad")
    stranger_key, _ = await _register(client, "attach_stranger")
    page_id = await _page(client, api_key)
    folder_id = await _folder(client, api_key)

    both = await _upload_image(client, api_key, {"parent_page_id": page_id, "folder_id": folder_id})
    assert both.status_code == 400

    foreign = await _upload_image(client, stranger_key, {"parent_page_id": page_id})
    assert foreign.status_code == 400

    # Markdown becomes a page — a page can't be another page's attachment.
    md = await client.post(
        "/api/v1/me/files",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
        data={"parent_page_id": page_id},
        headers=_auth(api_key),
    )
    assert md.status_code == 400


@pytest.mark.asyncio
async def test_patch_attach_and_detach_swap_parents(client: AsyncClient, stub_storage):
    api_key, _ = await _register(client, "attach_patch")
    page_id = await _page(client, api_key)
    folder_id = await _folder(client, api_key)

    file_id = (await _upload_image(client, api_key)).json()["id"]

    attached = await client.patch(
        f"/api/v1/me/files/{file_id}",
        json={"parent_page_id": page_id},
        headers=_auth(api_key),
    )
    assert attached.status_code == 200
    assert attached.json()["parent_page_id"] == page_id
    assert attached.json()["folder_id"] is None

    # Moving into a folder detaches — one parent at a time.
    moved = await client.patch(
        f"/api/v1/me/files/{file_id}",
        json={"folder_id": folder_id},
        headers=_auth(api_key),
    )
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == folder_id
    assert moved.json()["parent_page_id"] is None


@pytest.mark.asyncio
async def test_attachments_follow_page_through_trash_and_restore(
    client: AsyncClient, stub_storage, _db_pool
):
    api_key, _ = await _register(client, "attach_trash")
    page_id = await _page(client, api_key)

    riding = (await _upload_image(client, api_key, {"parent_page_id": page_id})).json()["id"]
    solo = (
        await _upload_image(client, api_key, {"parent_page_id": page_id}, name="solo.png")
    ).json()["id"]

    # Trash one attachment individually first; it must NOT ride the restore.
    assert (
        await client.delete(f"/api/v1/me/files/{solo}", headers=_auth(api_key))
    ).status_code == 204

    assert (
        await client.delete(f"/api/v1/me/pages/{page_id}", headers=_auth(api_key))
    ).status_code == 204
    deleted_at = await _db_pool.fetchval(
        "SELECT deleted_at FROM files WHERE id = CAST($1 AS uuid)", riding
    )
    assert deleted_at is not None

    # The riding attachment is hidden from trash (it restores with the page);
    # the individually-trashed one is listed while its page was live — but the
    # page is now trashed too, so both hide. The page itself lists.
    trash = await client.get("/api/v1/me/trash", headers=_auth(api_key))
    assert [p["id"] for p in trash.json()["pages"]] == [page_id]
    assert trash.json()["files"] == []

    assert (
        await client.post(f"/api/v1/me/pages/{page_id}/restore", headers=_auth(api_key))
    ).status_code == 204
    restored = await _db_pool.fetchrow(
        "SELECT "
        "  (SELECT deleted_at FROM files WHERE id = CAST($1 AS uuid)) AS riding, "
        "  (SELECT deleted_at FROM files WHERE id = CAST($2 AS uuid)) AS solo",
        riding,
        solo,
    )
    assert restored["riding"] is None
    assert restored["solo"] is not None


@pytest.mark.asyncio
async def test_purge_page_destroys_attachments_and_blobs(
    client: AsyncClient, stub_storage, _db_pool, monkeypatch
):
    api_key, _ = await _register(client, "attach_purge")
    page_id = await _page(client, api_key)
    file_id = (await _upload_image(client, api_key, {"parent_page_id": page_id})).json()["id"]

    deleted_blobs: list[str] = []

    async def _delete_blob(storage_key):
        deleted_blobs.append(storage_key)

    monkeypatch.setattr(storage_service, "delete_file", _delete_blob)

    assert (
        await client.delete(f"/api/v1/me/pages/{page_id}", headers=_auth(api_key))
    ).status_code == 204
    assert (
        await client.delete(f"/api/v1/me/pages/{page_id}/purge", headers=_auth(api_key))
    ).status_code == 204

    remaining = await _db_pool.fetchval(
        "SELECT COUNT(*) FROM files WHERE id = CAST($1 AS uuid)", file_id
    )
    assert remaining == 0
    assert len(deleted_blobs) == 1
