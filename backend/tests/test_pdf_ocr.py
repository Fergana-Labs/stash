"""Scanned PDFs must reach the knowledge base via OCR.

A scanned PDF has no embedded text layer, so pypdf extraction yields
nothing — before OCR existed those files sat invisible to the agent.
These tests pin the contract: textless PDFs go through `ocr_pdf`,
OCR failures surface loudly (never a silent empty row), and OCR is
never triggered when the cheap embedded-text path already worked.
"""

import io
import uuid

import asyncpg
import pypdf
import pytest

from backend.config import settings
from backend.services import pdf_ocr, storage_service
from backend.workers import extract_one

PAGE_SIZE = (612, 792)


def _blank_pdf(pages: int) -> bytes:
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(*PAGE_SIZE)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_ocr_pdf_fails_loud_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await pdf_ocr.ocr_pdf(_blank_pdf(1))


@pytest.mark.asyncio
async def test_ocr_pdf_chunks_pages_and_joins_transcriptions(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    async def fake_ocr_chunk(client, chunk):
        pages = len(pypdf.PdfReader(io.BytesIO(chunk)).pages)
        return f"pages={pages}"

    monkeypatch.setattr(pdf_ocr, "_ocr_chunk", fake_ocr_chunk)

    result = await pdf_ocr.ocr_pdf(_blank_pdf(25))

    assert result == "pages=10\n\npages=10\n\npages=5"


@pytest.mark.asyncio
async def test_ocr_pdf_page_cap_is_marked_not_silent(monkeypatch):
    """Bounding API spend is fine; pretending we read the whole document
    is not — the stored text must say where OCR stopped."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(pdf_ocr, "MAX_OCR_PAGES", 4)
    monkeypatch.setattr(pdf_ocr, "PAGES_PER_REQUEST", 2)

    async def fake_ocr_chunk(client, chunk):
        return "chunk"

    monkeypatch.setattr(pdf_ocr, "_ocr_chunk", fake_ocr_chunk)

    result = await pdf_ocr.ocr_pdf(_blank_pdf(6))

    assert result == "chunk\n\nchunk\n\n[OCR stopped at page 4 of 6]"


class _FakeConnection:
    def __init__(self, file_id, content_type):
        self.file_id = file_id
        self.content_type = content_type
        self.persisted_text = "unset"

    async def fetchrow(self, query, file_id):
        return {
            "id": file_id,
            "storage_key": "key",
            "content_type": self.content_type,
            "extraction_attempts": 0,
        }

    async def execute(self, query, file_id, text, embed_stale=None):
        self.persisted_text = text

    async def close(self):
        pass


def _wire_extract_one(monkeypatch, conn, content):
    async def connect(database_url):
        return conn

    async def download_file(storage_key):
        return content

    async def close_storage():
        pass

    monkeypatch.setattr(asyncpg, "connect", connect)
    monkeypatch.setattr(storage_service, "download_file", download_file)
    monkeypatch.setattr(storage_service, "close", close_storage)


@pytest.mark.asyncio
async def test_textless_pdf_is_ocred_and_stored(monkeypatch):
    conn = _FakeConnection(uuid.uuid4(), "application/pdf")
    _wire_extract_one(monkeypatch, conn, _blank_pdf(2))

    async def fake_ocr(content):
        return "transcribed scan"

    monkeypatch.setattr(pdf_ocr, "ocr_pdf", fake_ocr)

    assert await extract_one._run(conn.file_id) == 0
    assert conn.persisted_text == "transcribed scan"


@pytest.mark.asyncio
async def test_pdf_with_text_layer_skips_ocr(monkeypatch):
    """OCR costs an API call per chunk — a PDF the embedded-text path
    already handled must never hit the API."""
    conn = _FakeConnection(uuid.uuid4(), "text/plain")
    _wire_extract_one(monkeypatch, conn, b"plain text body")

    async def fail_ocr(content):
        raise AssertionError("ocr_pdf must not be called")

    monkeypatch.setattr(pdf_ocr, "ocr_pdf", fail_ocr)

    assert await extract_one._run(conn.file_id) == 0
    assert conn.persisted_text == "plain text body"


@pytest.mark.asyncio
async def test_non_pdf_without_text_never_ocrs(monkeypatch):
    conn = _FakeConnection(uuid.uuid4(), "image/png")
    _wire_extract_one(monkeypatch, conn, b"\x89PNG....")

    async def fail_ocr(content):
        raise AssertionError("ocr_pdf must not be called")

    monkeypatch.setattr(pdf_ocr, "ocr_pdf", fail_ocr)

    assert await extract_one._run(conn.file_id) == 0
    assert conn.persisted_text is None


@pytest.mark.asyncio
async def test_ocr_failure_marks_row_for_retry(monkeypatch):
    """An API blowup must land in extraction_error via the redacted-error
    path, not resolve to a 'done' row with NULL text."""
    file_id = uuid.uuid4()
    persisted_errors = []

    class FailingConnection(_FakeConnection):
        async def execute(self, query, file_id, error):
            persisted_errors.append(error)

    conn = FailingConnection(file_id, "application/pdf")
    _wire_extract_one(monkeypatch, conn, _blank_pdf(1))

    async def fail_ocr(content):
        raise RuntimeError("api exploded with document contents inside")

    monkeypatch.setattr(pdf_ocr, "ocr_pdf", fail_ocr)

    assert await extract_one._run(file_id) == 1
    assert persisted_errors == ["Extraction failed: RuntimeError"]
