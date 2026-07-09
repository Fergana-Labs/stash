"""A picked Drive folder stores its documents' text.

The old index-only Drive source fetched each body from Google on every read, which
meant a scanned parts catalog returned the empty string (OCR only ran on uploads)
and anything over 25 MB returned the sentence "_(file too large to inline)_".
Both looked, to an agent, exactly like a blank document.

These tests pin the two properties that fix buys: a document with no body is an
error the caller can see, and a body that has been extracted is served from
Postgres without touching Google.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from backend.database import get_pool
from backend.services import source_service

from .conftest import unique_name

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("drive"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _folder_source(owner_id: UUID) -> dict:
    return await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive_folder",
        external_ref=f"folder-{uuid4().hex[:8]}",
        display_name="Heavi Knowledge Base",
    )


async def _row(source_id: UUID, owner_id: UUID, path: str, **fields) -> UUID:
    cols = {"content": None, "extraction_status": "pending", "extraction_error": None, **fields}
    row = await get_pool().fetchrow(
        "INSERT INTO drive_documents "
        "(source_id, owner_user_id, path, name, external_ref, content, "
        " extraction_status, extraction_error) "
        "VALUES ($1, $2, $3, $4, 'drive-file-id', $5, $6, $7) RETURNING id",
        source_id,
        owner_id,
        path,
        path.split("/")[-1],
        cols["content"],
        cols["extraction_status"],
        cols["extraction_error"],
    )
    return row["id"]


async def test_a_folder_source_stores_content(client: AsyncClient):
    """The whole point: reads come from Postgres, not from Google."""
    api_key, owner_id = await _register(client)
    src = await _folder_source(owner_id)
    await _row(
        UUID(src["id"]),
        owner_id,
        "Bendix Catalog.pdf",
        content="BW1114 core charge waived",
        extraction_status="done",
    )

    resp = await client.get(
        f"/api/v1/me/sources/{src['id']}/doc",
        params={"ref": "Bendix Catalog.pdf"},
        headers=_auth(api_key),
    )

    assert resp.status_code == 200
    assert resp.json()["content"] == "BW1114 core charge waived"


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        ("pending", 409),
        ("processing", 409),
        ("unsupported", 415),
        ("too_large", 413),
        ("failed", 422),
    ],
)
async def test_a_document_without_a_body_is_an_error_not_an_empty_document(
    client: AsyncClient, status: str, expected_code: int
):
    """This is the bug that started it. A scanned catalog used to read as "" with
    exit 0, so an agent concluded the catalog was blank. Every state that carries
    no text must reach the caller as a non-2xx it can report."""
    api_key, owner_id = await _register(client)
    src = await _folder_source(owner_id)
    await _row(
        UUID(src["id"]),
        owner_id,
        "Scanned.pdf",
        extraction_status=status,
        extraction_error="no text could be extracted",
    )

    resp = await client.get(
        f"/api/v1/me/sources/{src['id']}/doc",
        params={"ref": "Scanned.pdf"},
        headers=_auth(api_key),
    )

    assert resp.status_code == expected_code
    assert "no text" in resp.json()["detail"]


async def test_text_already_extracted_survives_a_pending_re_extraction(client: AsyncClient):
    """A file edited in Drive is re-extracted, which takes minutes for a scan.
    Serving the previous text meanwhile is one sync interval stale — the same
    contract every copied source has — and beats going dark."""
    api_key, owner_id = await _register(client)
    src = await _folder_source(owner_id)
    await _row(
        UUID(src["id"]),
        owner_id,
        "Catalog.pdf",
        content="older but real",
        extraction_status="pending",
    )

    resp = await client.get(
        f"/api/v1/me/sources/{src['id']}/doc",
        params={"ref": "Catalog.pdf"},
        headers=_auth(api_key),
    )

    assert resp.status_code == 200
    assert resp.json()["content"] == "older but real"


async def test_search_uses_local_fts_not_google(client: AsyncClient):
    """A folder's content lives in our table, so it is searchable without spending
    the owner's Drive quota. A whole-Drive source stays federated."""
    api_key, owner_id = await _register(client)
    src = await _folder_source(owner_id)
    await _row(
        UUID(src["id"]),
        owner_id,
        "Wheel Seals.pdf",
        content="STEMCO Scotseal interchange chart",
        extraction_status="done",
    )

    resp = await client.get(
        "/api/v1/me/sources/search",
        params={"q": "Scotseal", "source": src["id"]},
        headers=_auth(api_key),
    )

    assert resp.status_code == 200
    hits = resp.json()["results"]
    assert any("Wheel Seals.pdf" in (h.get("name") or "") for h in hits)


async def test_only_the_folder_type_copies_content():
    """Whole-Drive stays index-only. `root` crawls My Drive plus Shared-with-me
    plus every Shared Drive — copying that, and auto-OCRing it, is unbounded."""
    assert source_service.SOURCE_TABLE["google_drive_folder"] == "drive_documents"
    assert "drive_documents" in source_service.CONTENT_TABLES

    assert source_service.SOURCE_TABLE["google_drive"] == "drive_index"
    assert "drive_index" not in source_service.CONTENT_TABLES
    assert "google_drive" in source_service.FEDERATED_SEARCH_TYPES
    assert "google_drive_folder" not in source_service.FEDERATED_SEARCH_TYPES


async def test_a_settled_unreadable_file_is_not_requeued_by_the_next_sync(client: AsyncClient):
    """'unsupported' is a fact about the bytes: the same version of the file will
    be unsupported next time too. If a sync treated it as work to redo, an
    unsupported 200 MB video would be re-downloaded every 30 minutes forever.
    Only a new Drive `modifiedTime` revives extraction."""
    _, owner_id = await _register(client)
    src = await _folder_source(owner_id)
    modified = datetime(2026, 7, 1, tzinfo=UTC)
    upsert = dict(
        source_id=UUID(src["id"]),
        owner_user_id=owner_id,
        path="training.mp4",
        name="training.mp4",
        external_ref="drive-file-id",
    )

    row_id = await source_service.upsert_drive_document(**upsert, external_updated_at=modified)
    assert row_id is not None  # first sight: extract it
    await get_pool().execute(
        "UPDATE drive_documents SET extraction_status = 'unsupported' WHERE id = $1", row_id
    )

    same_version = await source_service.upsert_drive_document(
        **upsert, external_updated_at=modified
    )
    assert same_version is None

    new_version = await source_service.upsert_drive_document(
        **upsert, external_updated_at=datetime(2026, 7, 2, tzinfo=UTC)
    )
    assert new_version is not None


async def test_a_stale_processing_lock_is_reclaimable(client: AsyncClient):
    """A worker that dies mid-extraction leaves 'processing' behind forever. The
    Beat sweep re-enqueues such rows, so the claim must accept them — while
    refusing a live lock, whose worker is still extracting."""
    from backend.tasks.drive_extraction import _claim

    _, owner_id = await _register(client)
    src = await _folder_source(owner_id)

    stuck = await _row(UUID(src["id"]), owner_id, "Stuck.pdf", extraction_status="processing")
    await get_pool().execute(
        "UPDATE drive_documents SET locked_at = now() - INTERVAL '31 minutes' WHERE id = $1",
        stuck,
    )
    assert await _claim(stuck) is True

    live = await _row(UUID(src["id"]), owner_id, "Live.pdf", extraction_status="processing")
    await get_pool().execute("UPDATE drive_documents SET locked_at = now() WHERE id = $1", live)
    assert await _claim(live) is False


async def test_the_recovery_sweep_is_scheduled():
    """The sweep is the only rescue for a dropped `.delay()` or a dead worker.
    A task that exists but is absent from `beat_schedule` never fires."""
    from backend.celery_app import celery

    scheduled = {entry["task"] for entry in celery.conf.beat_schedule.values()}
    assert "backend.tasks.drive_extraction.enqueue_pending" in scheduled
