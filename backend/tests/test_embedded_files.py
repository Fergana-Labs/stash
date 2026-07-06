"""Embedded files (files.owner_page_id).

A file is *filed* (folder or root, a tree entry) or *embedded* (owned by the
page whose body links its download route, absent from tree views). Embedding
is derived: saving a page body claims referenced root files, trashes owned
files whose link left the body, and restores owned files whose link came
back. The ownership edge itself is never writable through the API.
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


async def _page(client: AsyncClient, api_key: str, name: str = "Doc", content: str = "") -> str:
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": name, "content": content},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _set_page_content(client: AsyncClient, api_key: str, page_id: str, content: str) -> None:
    resp = await client.patch(
        f"/api/v1/me/pages/{page_id}",
        json={"content": content},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200


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
) -> str:
    resp = await client.post(
        "/api/v1/me/files",
        files={"file": (name, b"\x89PNG fake", "image/png")},
        data=data or {},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _embed(file_id: str) -> str:
    return f"![shot](/api/v1/me/files/{file_id}/download)"


async def _owner_page_id(client: AsyncClient, api_key: str, file_id: str) -> str | None:
    resp = await client.get(f"/api/v1/me/files/{file_id}", headers=_auth(api_key))
    assert resp.status_code == 200
    return resp.json()["owner_page_id"]


@pytest.mark.asyncio
async def test_saving_a_body_with_the_link_embeds_the_file(client: AsyncClient, stub_storage):
    api_key, _ = await _register(client, "embed_save")
    file_id = await _upload_image(client, api_key)

    page_id = await _page(client, api_key, content=f"# Doc\n\n{_embed(file_id)}\n")

    assert await _owner_page_id(client, api_key, file_id) == page_id
    # Embedded files are internals of their page — the overview tree omits them.
    overview = await client.get("/api/v1/me/overview", headers=_auth(api_key))
    assert overview.status_code == 200
    assert overview.json()["files"]["files"] == []


@pytest.mark.asyncio
async def test_unembedding_trashes_and_reembedding_restores(client: AsyncClient, stub_storage):
    api_key, _ = await _register(client, "embed_sync")
    file_id = await _upload_image(client, api_key)
    body = f"intro\n\n{_embed(file_id)}\n"
    page_id = await _page(client, api_key, content=body)

    # The link leaves the body -> the file is part of the document no more.
    await _set_page_content(client, api_key, page_id, "intro only\n")
    trash = await client.get("/api/v1/me/trash", headers=_auth(api_key))
    assert [f["id"] for f in trash.json()["files"]] == [file_id]

    # Editor undo brings the link back -> the bytes must follow.
    await _set_page_content(client, api_key, page_id, body)
    trash = await client.get("/api/v1/me/trash", headers=_auth(api_key))
    assert trash.json()["files"] == []
    assert await _owner_page_id(client, api_key, file_id) == page_id


@pytest.mark.asyncio
async def test_filed_files_are_never_claimed(client: AsyncClient, stub_storage):
    api_key, _ = await _register(client, "embed_filed")
    folder_id = await _folder(client, api_key)
    file_id = await _upload_image(client, api_key, {"folder_id": folder_id})

    page_id = await _page(client, api_key, content=_embed(file_id))

    # Referencing a folder-organized file links it without taking ownership.
    assert await _owner_page_id(client, api_key, file_id) is None
    # And the page saving again must not trash it (it owns nothing).
    await _set_page_content(client, api_key, page_id, "no links\n")
    trash = await client.get("/api/v1/me/trash", headers=_auth(api_key))
    assert trash.json()["files"] == []


@pytest.mark.asyncio
async def test_moving_an_embedded_file_to_a_folder_files_it(client: AsyncClient, stub_storage):
    api_key, _ = await _register(client, "embed_move")
    file_id = await _upload_image(client, api_key)
    await _page(client, api_key, content=_embed(file_id))
    folder_id = await _folder(client, api_key)

    moved = await client.patch(
        f"/api/v1/me/files/{file_id}",
        json={"folder_id": folder_id},
        headers=_auth(api_key),
    )
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == folder_id
    assert moved.json()["owner_page_id"] is None


@pytest.mark.asyncio
async def test_restoring_a_trashed_file_files_it_at_root(client: AsyncClient, stub_storage):
    api_key, _ = await _register(client, "embed_restore")
    file_id = await _upload_image(client, api_key)
    page_id = await _page(client, api_key, content=_embed(file_id))

    # Unembed -> trash, then restore the file on its own.
    await _set_page_content(client, api_key, page_id, "no links\n")
    assert (
        await client.post(f"/api/v1/me/files/{file_id}/restore", headers=_auth(api_key))
    ).status_code == 204

    # Restored as an ordinary root file — visible, not secretly still owned.
    assert await _owner_page_id(client, api_key, file_id) is None
    overview = await client.get("/api/v1/me/overview", headers=_auth(api_key))
    assert [f["id"] for f in overview.json()["files"]["files"]] == [file_id]


@pytest.mark.asyncio
async def test_embedded_files_follow_page_through_trash_and_restore(
    client: AsyncClient, stub_storage, _db_pool
):
    api_key, _ = await _register(client, "embed_trash")
    riding = await _upload_image(client, api_key)
    solo = await _upload_image(client, api_key, name="solo.png")
    page_id = await _page(client, api_key, content=f"{_embed(riding)}\n{_embed(solo)}\n")

    # Trash one embedded file individually first; it must NOT ride the restore.
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

    # The riding file is hidden from trash (it restores with the page); the
    # individually-trashed one listed while its page was live — but the page
    # is now trashed too, so both hide. The page itself lists.
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
async def test_purge_page_destroys_embedded_files_and_blobs(
    client: AsyncClient, stub_storage, _db_pool, monkeypatch
):
    api_key, _ = await _register(client, "embed_purge")
    file_id = await _upload_image(client, api_key)
    page_id = await _page(client, api_key, content=_embed(file_id))

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
