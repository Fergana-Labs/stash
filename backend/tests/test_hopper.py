"""The hopper: drop anything, and the feed says whether an agent can read it.

The whole promise of the tab is that "legible" means legible. So the feed must
never claim it for something an agent cannot actually read — a file still in
extraction, a file that yielded no text, a link the site refused us — and must
flip to it, unprompted, the moment the underlying pipeline lands the content.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import files_tree_service, storage_service, url_import_service
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
    # Extraction runs in a Celery worker; these tests drive its outcome by hand.
    monkeypatch.setattr(extraction.extract_file_text, "delay", lambda *a, **k: None)


def _mock_import_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda *a, **k: None)


async def _feed(client: AsyncClient, headers: dict) -> list[dict]:
    resp = await client.get("/api/v1/me/hopper", headers=headers)
    assert resp.status_code == 200
    return resp.json()["items"]


@pytest.mark.asyncio
async def test_note_is_legible_the_moment_it_is_dropped(client: AsyncClient) -> None:
    headers, _ = await _register(client)

    resp = await client.post(
        "/api/v1/me/hopper/note",
        json={"text": "Pricing call notes\nThey want annual billing."},
        headers=headers,
    )
    assert resp.status_code == 201
    item = resp.json()
    # A note IS its text — there is no pipeline to wait on.
    assert item["status"] == "legible"
    assert item["target"]["kind"] == "page"
    assert item["label"].startswith("Pricing call notes")
    assert "annual billing" in item["preview"]


@pytest.mark.asyncio
async def test_file_reads_first_and_only_then_claims_legible(
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
    item = resp.json()
    # The bytes are stored, but nothing has read them yet.
    assert item["status"] == "reading"
    assert item["target"]["kind"] == "file"

    await pool.execute(
        "UPDATE files SET extraction_status = 'done', extracted_text = $2 WHERE id = $1",
        UUID(item["target"]["id"]),
        "Master services agreement, term of 24 months.",
    )
    (fresh,) = await _feed(client, headers)
    assert fresh["status"] == "legible"
    assert "24 months" in fresh["preview"]


@pytest.mark.asyncio
async def test_file_that_yielded_no_text_is_never_called_legible(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)

    resp = await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("logo.svg", b"<svg/>", "image/svg+xml")},
        headers=headers,
    )
    file_id = UUID(resp.json()["target"]["id"])
    # Extraction finished and found nothing an agent can read.
    await pool.execute(
        "UPDATE files SET extraction_status = 'done', extracted_text = NULL WHERE id = $1",
        file_id,
    )

    (item,) = await _feed(client, headers)
    assert item["status"] == "no_text"
    assert item["detail"]


@pytest.mark.asyncio
async def test_failed_extraction_surfaces_the_failure(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, _ = await _register(client)
    _mock_storage(monkeypatch)

    resp = await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("deck.pptx", b"junk", "application/octet-stream")},
        headers=headers,
    )
    await pool.execute(
        "UPDATE files SET extraction_status = 'failed', extraction_error = $2 WHERE id = $1",
        UUID(resp.json()["target"]["id"]),
        "ValueError",
    )

    (item,) = await _feed(client, headers)
    assert item["status"] == "failed"
    assert item["detail"] == "ValueError"


@pytest.mark.asyncio
async def test_link_waits_on_its_import_then_points_at_what_landed(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, owner_id = await _register(client)
    _mock_import_dispatch(monkeypatch)

    resp = await client.post(
        "/api/v1/me/hopper/link",
        json={"url": "https://example.com/post"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "reading"

    import_id = await pool.fetchval(
        "SELECT id FROM url_imports WHERE owner_user_id = $1", UUID(owner_id)
    )
    page = await files_tree_service.create_page(
        UUID(owner_id), "The post", UUID(owner_id), content="The body of the post."
    )
    await url_import_service.mark_done(import_id, page_id=page["id"])

    # The feed reads the import's own result — nothing wrote status twice.
    (item,) = await _feed(client, headers)
    assert item["status"] == "legible"
    assert item["target"]["name"] == "The post"
    assert "body of the post" in item["preview"]


@pytest.mark.asyncio
async def test_link_the_site_blocked_asks_for_the_extension(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, owner_id = await _register(client)
    _mock_import_dispatch(monkeypatch)

    await client.post(
        "/api/v1/me/hopper/link",
        json={"url": "https://paywalled.example/article"},
        headers=headers,
    )
    import_id = await pool.fetchval(
        "SELECT id FROM url_imports WHERE owner_user_id = $1", UUID(owner_id)
    )
    await url_import_service.mark_needs_client(import_id, "HTTP 403")

    (item,) = await _feed(client, headers)
    # Telling the user the browser extension can reach it is the only honest
    # next step; a spinner here would never resolve.
    assert item["status"] == "needs_extension"
    assert "extension" in item["detail"]


@pytest.mark.asyncio
async def test_every_drop_lands_in_the_one_hopper_folder(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, owner_id = await _register(client)
    _mock_storage(monkeypatch)

    await client.post("/api/v1/me/hopper/note", json={"text": "first"}, headers=headers)
    await client.post(
        "/api/v1/me/hopper/file",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=headers,
    )

    folders = await pool.fetch(
        "SELECT id FROM folders WHERE owner_user_id = $1 AND name = 'Hopper'", UUID(owner_id)
    )
    assert len(folders) == 1
    folder_id = folders[0]["id"]
    assert await pool.fetchval("SELECT count(*) FROM pages WHERE folder_id = $1", folder_id) == 1
    assert await pool.fetchval("SELECT count(*) FROM files WHERE folder_id = $1", folder_id) == 1
