"""The hopper: an intake into the VFS, not a place things sit.

A drop must become an ordinary VFS item at the top of the user's stash,
indistinguishable from one created any other way. Nothing is parked in a
holding folder, and no ledger records the drop: the item itself is the record.

The hopper takes things that already exist — a file or a link. There is no
compose-a-note path; that is what pages are for.

A dropped directory keeps its shape: the user's own filing is the one
destination we never have to guess at, and re-dropping it must not double
what is already there.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import llm, storage_service
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


@pytest.mark.asyncio
async def test_a_dropped_folder_keeps_its_shape(client: AsyncClient, pool, monkeypatch) -> None:
    """Mirroring the directory is filing without guessing — it is the user's
    own structure, not a classifier's opinion."""
    headers, owner_id = await _register(client)
    _mock_storage(monkeypatch)

    resp = await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("brakes.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"path": "catalogs/meritor"},
        headers=headers,
    )
    assert resp.status_code == 201

    row = await pool.fetchrow(
        "SELECT f.name AS folder, p.name AS parent FROM files fi "
        "JOIN folders f ON f.id = fi.folder_id "
        "JOIN folders p ON p.id = f.parent_folder_id "
        "WHERE fi.id = $1",
        UUID(resp.json()["id"]),
    )
    assert row["folder"] == "meritor"
    assert row["parent"] == "catalogs"


@pytest.mark.asyncio
async def test_redropping_a_folder_skips_what_is_already_there(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """A backlog gets dropped twice — once to try it, once for real. The
    second pass must not leave two of everything."""
    headers, owner_id = await _register(client)
    _mock_storage(monkeypatch)

    async def drop():
        return await client.post(
            "/api/v1/me/hopper/file",
            files={"file": ("brakes.pdf", b"%PDF-1.4 x", "application/pdf")},
            data={"path": "catalogs"},
            headers=headers,
        )

    first = await drop()
    second = await drop()

    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"]
    count = await pool.fetchval(
        "SELECT count(*) FROM files WHERE owner_user_id = $1 AND deleted_at IS NULL",
        UUID(owner_id),
    )
    assert count == 1
    # One folder, not two: the mirror is idempotent too.
    folders = await pool.fetchval(
        "SELECT count(*) FROM folders WHERE owner_user_id = $1", UUID(owner_id)
    )
    assert folders == 1


@pytest.mark.asyncio
async def test_a_re_dropped_markdown_file_is_skipped_not_a_conflict(
    client: AsyncClient, monkeypatch
) -> None:
    """Pages are unique by name in a folder, so the second drop of the same
    note used to 409 and fail the whole batch."""
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)

    async def drop():
        return await client.post(
            "/api/v1/me/hopper/file",
            files={"file": ("readme.md", b"# hello", "text/markdown")},
            headers=headers,
        )

    assert (await drop()).json()["duplicate"] is False
    second = await drop()
    assert second.status_code == 201
    assert second.json()["duplicate"] is True


@pytest.mark.asyncio
async def test_absurd_nesting_is_refused(client: AsyncClient, monkeypatch) -> None:
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)

    resp = await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("deep.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"path": "/".join(f"level{i}" for i in range(12))},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_a_folder_named_memory_cannot_hijack_the_reserved_one(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """Memory is the product's space, not a folder name to be claimed. A drop
    that landed there would vanish: Files hides the Memory subtree."""
    headers, owner_id = await _register(client)
    _mock_storage(monkeypatch)

    # Touching the memory tree is what creates the reserved folder.
    assert (await client.get("/api/v1/me/memory-tree", headers=headers)).status_code == 200

    resp = await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("notes.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"path": "Memory"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "reserved" in resp.json()["detail"]

    landed = await pool.fetchval(
        "SELECT count(*) FROM files WHERE owner_user_id = $1 AND deleted_at IS NULL",
        UUID(owner_id),
    )
    assert landed == 0


# --- filing a loose file, after it has already landed --------------------


async def _drop(client: AsyncClient, headers: dict, name: str, body: bytes, ctype: str) -> dict:
    resp = await client.post(
        "/api/v1/me/hopper/file", files={"file": (name, body, ctype)}, headers=headers
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_upload_does_not_wait_on_the_classifier(client: AsyncClient, monkeypatch) -> None:
    """A model call has no business between dropping a file and being told it
    arrived."""
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)
    await client.post("/api/v1/me/folders", json={"name": "Invoices"}, headers=headers)

    async def never(**kwargs):
        raise AssertionError("the upload path must not call the model")

    monkeypatch.setattr(llm, "complete_json", never)

    landed = await _drop(client, headers, "acme-invoice.pdf", b"%PDF-1.4 x", "application/pdf")
    assert landed["classifiable"] is True


@pytest.mark.asyncio
async def test_classify_files_a_loose_item(client: AsyncClient, pool, monkeypatch) -> None:
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)
    await client.post("/api/v1/me/folders", json={"name": "Invoices"}, headers=headers)
    landed = await _drop(client, headers, "acme-invoice.pdf", b"%PDF-1.4 x", "application/pdf")

    async def fake_json(**kwargs):
        return {"folder": "Invoices"}

    monkeypatch.setattr(llm, "complete_json", fake_json)
    resp = await client.post(
        "/api/v1/me/hopper/classify",
        json={"kind": landed["kind"], "id": landed["id"]},
        headers=headers,
    )
    assert resp.json()["filed_in"] == "Invoices"
    folder = await pool.fetchval(
        "SELECT f.name FROM files fi JOIN folders f ON f.id = fi.folder_id WHERE fi.id = $1",
        UUID(landed["id"]),
    )
    assert folder == "Invoices"


@pytest.mark.asyncio
async def test_classify_never_invents_a_folder(client: AsyncClient, pool, monkeypatch) -> None:
    """Inventing a folder per file is how a stash ends up with forty folders
    holding one item each."""
    headers, owner_id = await _register(client)
    _mock_storage(monkeypatch)
    await client.post("/api/v1/me/folders", json={"name": "Invoices"}, headers=headers)
    landed = await _drop(client, headers, "receipt.pdf", b"%PDF-1.4 x", "application/pdf")

    async def fake_json(**kwargs):
        return {"folder": "Receipts/2026"}

    monkeypatch.setattr(llm, "complete_json", fake_json)
    resp = await client.post(
        "/api/v1/me/hopper/classify",
        json={"kind": "file", "id": landed["id"]},
        headers=headers,
    )
    assert resp.json()["filed_in"] is None
    assert (
        await pool.fetchval("SELECT count(*) FROM folders WHERE owner_user_id = $1", UUID(owner_id))
        == 1
    )


@pytest.mark.asyncio
async def test_classify_will_not_move_something_already_filed(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """A dropped folder is the user's own filing; re-deciding it would be the
    classifier overruling a person."""
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)
    resp = await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("brakes.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"path": "catalogs"},
        headers=headers,
    )
    landed = resp.json()
    assert landed["classifiable"] is False

    async def never(**kwargs):
        raise AssertionError("an already-filed item must not be classified")

    monkeypatch.setattr(llm, "complete_json", never)
    filed = await client.post(
        "/api/v1/me/hopper/classify",
        json={"kind": "file", "id": landed["id"]},
        headers=headers,
    )
    assert filed.json()["filed_in"] is None
    folder = await pool.fetchval(
        "SELECT f.name FROM files fi JOIN folders f ON f.id = fi.folder_id WHERE fi.id = $1",
        UUID(landed["id"]),
    )
    assert folder == "catalogs"


@pytest.mark.asyncio
async def test_an_unfilable_image_gets_a_home_rather_than_littering_the_root(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """IMG_0917.jpg has no semantic home, but it has an obvious kind. Leaving
    it loose turns the top level into the junk drawer a filesystem exists to
    prevent."""
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)
    landed = await _drop(client, headers, "IMG_0917.jpg", b"\xff\xd8\xff", "image/jpeg")

    async def declines(**kwargs):
        return {"folder": None}

    monkeypatch.setattr(llm, "complete_json", declines)
    resp = await client.post(
        "/api/v1/me/hopper/classify",
        json={"kind": "file", "id": landed["id"]},
        headers=headers,
    )
    assert resp.json()["filed_in"] == "Images"
    folder = await pool.fetchval(
        "SELECT f.name FROM files fi JOIN folders f ON f.id = fi.folder_id WHERE fi.id = $1",
        UUID(landed["id"]),
    )
    assert folder == "Images"


@pytest.mark.asyncio
async def test_a_named_image_still_goes_where_it_belongs(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """The Images folder is the last resort, not the destination for anything
    that happens to be an image."""
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)
    await client.post("/api/v1/me/folders", json={"name": "Diagrams"}, headers=headers)
    landed = await _drop(client, headers, "brake-assembly-diagram.png", b"\x89PNG", "image/png")

    async def picks(**kwargs):
        return {"folder": "Diagrams"}

    monkeypatch.setattr(llm, "complete_json", picks)
    resp = await client.post(
        "/api/v1/me/hopper/classify",
        json={"kind": "file", "id": landed["id"]},
        headers=headers,
    )
    assert resp.json()["filed_in"] == "Diagrams"


@pytest.mark.asyncio
async def test_an_unfilable_document_is_left_alone(client: AsyncClient, pool, monkeypatch) -> None:
    """Only images get a kind-based home; a document with no obvious folder
    stays where the person can see it."""
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)
    landed = await _drop(client, headers, "untitled.pdf", b"%PDF-1.4 x", "application/pdf")

    async def declines(**kwargs):
        return {"folder": None}

    monkeypatch.setattr(llm, "complete_json", declines)
    resp = await client.post(
        "/api/v1/me/hopper/classify",
        json={"kind": "file", "id": landed["id"]},
        headers=headers,
    )
    assert resp.json()["filed_in"] is None
    assert (
        await pool.fetchval("SELECT folder_id FROM files WHERE id = $1", UUID(landed["id"])) is None
    )
