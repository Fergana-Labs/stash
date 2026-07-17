"""URL imports: async fetch jobs behind the clip API.

The router must classify URLs in one place (YouTube → transcript, arXiv
abs → paper PDF, PDFs → file clips, HTML → article pages) and every
failure must land on the row as a loud per-item error — a dead link in a
bookmark import can never block the batch.
"""

from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient

from backend.services import clip_router, storage_service, url_import_service
from backend.services.youtube_transcript import TranscriptUnavailable, _parse_json3, _pick_track
from backend.tasks import clips as clips_tasks
from backend.tasks import extraction

from .conftest import unique_name
from .test_clips import ARTICLE_HTML


async def _register(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["id"]


# --- URL classification ---


def test_is_youtube_matches_watch_shorts_and_short_links() -> None:
    assert clip_router.is_youtube("https://www.youtube.com/watch?v=abc123")
    assert clip_router.is_youtube("https://youtube.com/shorts/abc123")
    assert clip_router.is_youtube("https://youtu.be/abc123")
    assert not clip_router.is_youtube("https://youtu.be/")
    assert not clip_router.is_youtube("https://www.youtube.com/@somechannel")
    assert not clip_router.is_youtube("https://example.com/watch?v=abc123")


def test_normalize_arxiv_rewrites_abs_to_pdf() -> None:
    assert (
        clip_router.normalize_arxiv("https://arxiv.org/abs/2401.00001")
        == "https://arxiv.org/pdf/2401.00001"
    )
    assert (
        clip_router.normalize_arxiv("https://www.arxiv.org/abs/2401.00001v2")
        == "https://arxiv.org/pdf/2401.00001v2"
    )
    assert clip_router.normalize_arxiv("https://example.com/abs/x") == "https://example.com/abs/x"


def test_is_async_url_covers_youtube_and_arxiv() -> None:
    assert clip_router.is_async_url("https://www.youtube.com/watch?v=abc")
    assert clip_router.is_async_url("https://arxiv.org/abs/2401.00001")
    assert not clip_router.is_async_url("https://example.com/post")


# --- YouTube caption parsing ---


def test_pick_track_prefers_manual_then_english() -> None:
    manual = {"de": [{"ext": "json3", "url": "manual-de"}]}
    auto = {"en": [{"ext": "json3", "url": "auto-en"}]}
    assert _pick_track(manual, auto, "de")[0]["url"] == "manual-de"
    assert _pick_track({}, auto, "de")[0]["url"] == "auto-en"
    assert _pick_track({}, {}, "de") is None


def test_parse_json3_flattens_events() -> None:
    payload = {
        "events": [
            {"segs": [{"utf8": "hello "}, {"utf8": "world"}]},
            {"segs": [{"utf8": "\n"}]},
            {"segs": [{"utf8": "again"}]},
        ]
    }
    assert _parse_json3(payload) == "hello world again"
    with pytest.raises(TranscriptUnavailable):
        _parse_json3({"events": []})


# --- Endpoint behaviour ---


@pytest.mark.asyncio
async def test_clip_page_defers_youtube_to_worker(client: AsyncClient, pool, monkeypatch) -> None:
    dispatched: list[list[str]] = []
    monkeypatch.setattr(
        clips_tasks.process_url_imports, "delay", lambda ids: dispatched.append(ids)
    )
    headers, _ = await _register(client)

    resp = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://www.youtube.com/watch?v=abc123", "html": "<html></html>"},
        headers=headers,
    )
    assert resp.status_code == 202
    import_id = resp.json()["import_id"]
    assert dispatched == [[import_id]]

    status = await client.get(f"/api/v1/me/clips/{import_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_clip_import_status_is_owner_scoped(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda ids: None)
    headers, _ = await _register(client)
    other_headers, _ = await _register(client)

    resp = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://youtu.be/abc123", "html": "<html></html>"},
        headers=headers,
    )
    import_id = resp.json()["import_id"]

    other = await client.get(f"/api/v1/me/clips/{import_id}", headers=other_headers)
    assert other.status_code == 404


# --- Worker processing ---


async def _make_import(owner_id: str, url: str, title: str | None = None) -> UUID:
    ids = await url_import_service.create_url_imports(
        owner_user_id=UUID(owner_id),
        created_by=UUID(owner_id),
        items=[{"url": url, "title": title}],
    )
    return ids[0]


@pytest.mark.asyncio
async def test_worker_turns_html_url_into_clip_page(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/post")

    async def fake_fetch(url: str):
        return ARTICLE_HTML.encode(), "text/html; charset=utf-8"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    page = await pool.fetchrow(
        "SELECT p.name, f.name AS folder_name FROM pages p "
        "JOIN folders f ON f.id = p.folder_id WHERE p.id = $1",
        row["result_page_id"],
    )
    assert page["name"] == "Why Simplicity Wins"
    assert page["folder_name"] == "raw"


@pytest.mark.asyncio
async def test_worker_turns_pdf_url_into_file_clip(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://arxiv.org/abs/2401.00001")

    fetched: list[str] = []

    async def fake_fetch(url: str):
        fetched.append(url)
        return b"%PDF-1.4 fake body", "application/pdf"

    async def _upload(*args, **kwargs):
        return "test/key"

    async def _url(key):
        return f"https://blob.example/{key}"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(extraction.extract_file_text, "delay", lambda *a, **k: None)

    await clips_tasks._process_batch([import_id])

    assert fetched == ["https://arxiv.org/pdf/2401.00001"]
    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    file_row = await pool.fetchrow(
        "SELECT name, source_url FROM files WHERE id = $1", row["result_file_id"]
    )
    assert file_row["source_url"] == "https://arxiv.org/abs/2401.00001"
    assert file_row["name"].endswith(".pdf")


@pytest.mark.asyncio
async def test_worker_turns_youtube_url_into_transcript_page(
    client: AsyncClient, pool, monkeypatch
) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://www.youtube.com/watch?v=abc123")

    monkeypatch.setattr(
        clip_router.youtube_transcript,
        "fetch_transcript",
        lambda url: {"title": "A Great Talk", "channel": "Chan", "transcript": "words words"},
    )
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "done"
    page = await pool.fetchrow(
        "SELECT p.name, p.content_markdown, f.name AS folder_name FROM pages p "
        "JOIN folders f ON f.id = p.folder_id WHERE p.id = $1",
        row["result_page_id"],
    )
    assert page["name"] == "A Great Talk"
    assert page["folder_name"] == "raw"
    assert "words words" in page["content_markdown"]


@pytest.mark.asyncio
async def test_worker_records_fetch_failure_on_row(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/dead-link")

    async def fake_fetch(url: str):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "failed"
    assert "ConnectError" in row["error"]
    assert row["attempts"] == 1


@pytest.mark.asyncio
async def test_done_rows_are_not_reclaimed(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/post")

    async def fake_fetch(url: str):
        return ARTICLE_HTML.encode(), "text/html"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])
    assert await url_import_service.claim(import_id) is None


@pytest.mark.asyncio
async def test_unsupported_content_type_fails_loud(client: AsyncClient, pool, monkeypatch) -> None:
    _, owner_id = await _register(client)
    import_id = await _make_import(owner_id, "https://example.com/video.mp4")

    async def fake_fetch(url: str):
        return b"\x00\x01binary", "video/mp4"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    await clips_tasks._process_batch([import_id])

    row = await pool.fetchrow("SELECT * FROM url_imports WHERE id = $1", import_id)
    assert row["status"] == "failed"
    assert "video/mp4" in row["error"]
