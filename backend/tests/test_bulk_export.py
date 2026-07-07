"""Bulk export (`GET /api/v1/me/export`).

The no-lock-in promise: the zip must contain every folder, page, and upload
the caller owns — as plain files mirroring the tree — and nothing owned by
anyone else.
"""

import io
import zipfile

import pytest
from httpx import AsyncClient

from backend.services import storage_service
from backend.tasks import extraction

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, prefix: str) -> str:
    name = unique_name(prefix)
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1", "email": f"{name}@test.local"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


@pytest.fixture
def stub_storage(monkeypatch):
    """Uploads and the export both hit S3; CI has none, so blobs live in a dict."""
    blobs: dict[str, bytes] = {}

    async def _upload(owner_user_id, filename, content, content_type):
        key = f"test/{owner_user_id}/{filename}"
        blobs[key] = content
        return key

    async def _url(storage_key, expires_in=3600):
        return f"https://files.test/{storage_key}"

    async def _download(storage_key):
        return blobs[storage_key]

    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(storage_service, "download_file", _download)
    monkeypatch.setattr(extraction.extract_file_text, "delay", lambda *a, **k: None)


async def _folder(client: AsyncClient, api_key: str, name: str, parent: str | None = None) -> str:
    body: dict = {"name": name}
    if parent:
        body["parent_folder_id"] = parent
    resp = await client.post("/api/v1/me/folders", json=body, headers=_auth(api_key))
    assert resp.status_code == 201
    return resp.json()["id"]


async def _page(
    client: AsyncClient, api_key: str, name: str, content: str, folder_id: str | None = None
) -> str:
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": name, "content": content, "folder_id": folder_id},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _upload_binary(
    client: AsyncClient, api_key: str, name: str, content: bytes, folder_id: str | None = None
) -> str:
    resp = await client.post(
        "/api/v1/me/files",
        files={"file": (name, content, "application/pdf")},
        data={"folder_id": folder_id} if folder_id else {},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _export(client: AsyncClient, api_key: str) -> zipfile.ZipFile:
    resp = await client.get("/api/v1/me/export", headers=_auth(api_key))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(resp.content))


@pytest.mark.asyncio
async def test_export_mirrors_the_whole_tree(client: AsyncClient, stub_storage):
    api_key = await _register(client, "export_tree")
    docs = await _folder(client, api_key, "Docs")
    brakes = await _folder(client, api_key, "Brakes", parent=docs)
    empty = await _folder(client, api_key, "Empty")
    await _page(client, api_key, "Guide", "# Brake pads\n", folder_id=brakes)
    await _page(client, api_key, "Notes", "root notes\n")
    await _page(client, api_key, "readme.md", "uploaded page\n")
    await _upload_binary(client, api_key, "manual.pdf", b"%PDF fake", folder_id=docs)
    assert empty

    archive = await _export(client, api_key)
    names = set(archive.namelist())

    assert "Docs/" in names
    assert "Empty/" in names
    assert "Docs/Brakes/Guide.md" in names
    assert "Notes.md" in names
    # A page name that already carries the extension must not double it.
    assert "readme.md" in names
    assert "Docs/manual.pdf" in names
    assert archive.read("Docs/Brakes/Guide.md") == b"# Brake pads\n"
    assert archive.read("Docs/manual.pdf") == b"%PDF fake"


@pytest.mark.asyncio
async def test_embedded_files_export_under_attachments(client: AsyncClient, stub_storage):
    api_key = await _register(client, "export_embed")
    file_id = await _upload_binary(client, api_key, "shot.png", b"\x89PNG fake")
    await _page(
        client,
        api_key,
        "Doc",
        f"![shot](/api/v1/me/files/{file_id}/download)\n",
    )

    archive = await _export(client, api_key)

    # Named by the file id the page body references, so links stay traceable.
    assert archive.read(f"attachments/{file_id}-shot.png") == b"\x89PNG fake"


@pytest.mark.asyncio
async def test_export_excludes_other_users_content(client: AsyncClient, stub_storage):
    owner_key = await _register(client, "export_owner")
    other_key = await _register(client, "export_other")
    await _page(client, other_key, "Secret", "not yours\n")
    await _page(client, owner_key, "Mine", "mine\n")

    archive = await _export(client, owner_key)
    names = set(archive.namelist())

    assert "Mine.md" in names
    assert "Secret.md" not in names


@pytest.mark.asyncio
async def test_export_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/me/export")
    assert resp.status_code == 401
