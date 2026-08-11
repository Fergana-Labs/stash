"""The hopper: an intake into the VFS, not a place things sit.

A drop must become an ordinary VFS item at the top of the user's stash,
indistinguishable from one created any other way. Nothing is parked in a
holding folder, and no ledger records the drop: the item itself is the record.

The hopper takes things that already exist — a file or a link. There is no
compose-a-note path; that is what pages are for.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import storage_service
from backend.tasks import clips as clips_tasks
from backend.tasks import extraction

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["id"]


def _mock_storage(monkeypatch) -> None:
    async def _upload(*args, **kwargs):
        return "test/storage-key"

    async def _url(key):
        return f"https://blob.example/{key}"

    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(extraction.extract_file_text, "delay", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_file_lands_in_the_vfs_and_starts_extraction(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)

    resp = await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("contract.pdf", b"%PDF-1.4 fake body", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201
    drop = resp.json()
    assert drop["kind"] == "file"
    assert drop["name"] == "contract.pdf"

    row = await pool.fetchrow(
        "SELECT folder_id, extraction_status FROM files WHERE id = $1", UUID(drop["id"])
    )
    assert row["folder_id"] is None
    # Queued for text extraction the moment it lands — that is what makes it
    # readable by an agent.
    assert row["extraction_status"] == "pending"


@pytest.mark.asyncio
async def test_link_queues_an_import_that_files_itself(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, owner_id = await _register(client)
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda *a, **k: None)

    resp = await client.post(
        "/api/v1/me/hopper/link",
        json={"url": "https://example.com/post"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["kind"] == "link"

    row = await pool.fetchrow(
        "SELECT url, folder_id, status FROM url_imports WHERE owner_user_id = $1", UUID(owner_id)
    )
    assert row["url"] == "https://example.com/post"
    assert row["folder_id"] is None
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_hopper_creates_no_folder_of_its_own(client: AsyncClient, pool, monkeypatch) -> None:
    """The hopper sorts things INTO the VFS. A holding folder would defeat it."""
    headers, owner_id = await _register(client)
    _mock_storage(monkeypatch)

    await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=headers,
    )

    folders = await pool.fetch("SELECT name FROM folders WHERE owner_user_id = $1", UUID(owner_id))
    assert [f["name"] for f in folders] == []


@pytest.mark.asyncio
async def test_there_is_no_compose_a_note_endpoint(client: AsyncClient) -> None:
    """Typing prose into the hopper cheapens it: it is an intake for things
    that already exist, not a scratchpad."""
    headers, _ = await _register(client)
    resp = await client.post("/api/v1/me/hopper/note", json={"text": "a thought"}, headers=headers)
    assert resp.status_code == 404
