"""PDFs reach the knowledge base via vision transcription grounded by the text layer.

pypdf alone has exact characters but scrambles multi-column tables; vision
alone has the layout but can misread a digit — and a misread digit in a part
number ships the wrong part. `transcribe_pdf` sends both in one request:
structure from the page images, characters from the embedded text layer. A
scanned PDF simply has no layer to attach and degrades to pure OCR.

These tests pin that contract: the layer rides along as grounding, pages past
the vision cap keep their raw text layer (the cap bounds API spend, it must not
discard free text), failures surface loudly, and the upload path never pays for
a vision call when plain extraction already worked.
"""

import io
import uuid
from types import SimpleNamespace

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
async def test_transcribe_pdf_fails_loud_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await pdf_ocr.transcribe_pdf(_blank_pdf(1))


@pytest.mark.asyncio
async def test_transcribe_pdf_chunks_pages_and_joins_transcriptions(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    async def fake_chunk(client, chunk):
        pages = len(pypdf.PdfReader(io.BytesIO(chunk)).pages)
        return f"pages={pages}"

    monkeypatch.setattr(pdf_ocr, "_transcribe_chunk", fake_chunk)

    result = await pdf_ocr.transcribe_pdf(_blank_pdf(25))

    assert result == "pages=10\n\npages=10\n\npages=5"


@pytest.mark.asyncio
async def test_the_text_layer_rides_along_as_grounding(monkeypatch):
    """The whole point of reconciliation: the request must carry the embedded
    text layer so the model takes characters from it, not from its own read
    of the page image."""
    captured = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="reconciled")],
                stop_reason="end_turn",
            )

    client = SimpleNamespace(messages=FakeMessages())
    monkeypatch.setattr(pdf_ocr, "extract_text", lambda content, ct: "288241R\tOR288241\t106113")

    result = await pdf_ocr._transcribe_chunk(client, _blank_pdf(1))

    assert result == "reconciled"
    prompt = "".join(
        block["text"] for block in captured["messages"][0]["content"] if block["type"] == "text"
    )
    assert "288241R\tOR288241\t106113" in prompt
    assert "<text_layer>" in prompt
    # A page can render a token cut off (page edge, cropped scan) while the
    # layer holds the whole string; the instruction to recover it must ride
    # along, or clipped part numbers come back as fragments.
    assert "complete string" in prompt


@pytest.mark.asyncio
async def test_a_scan_sends_no_grounding_block(monkeypatch):
    """A scan has no text layer. The prompt must not carry an empty
    <text_layer> block that invites the model to treat 'nothing' as truth."""
    captured = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="ocr")], stop_reason="end_turn"
            )

    client = SimpleNamespace(messages=FakeMessages())
    monkeypatch.setattr(pdf_ocr, "extract_text", lambda content, ct: None)

    await pdf_ocr._transcribe_chunk(client, _blank_pdf(1))

    prompt = "".join(
        block["text"] for block in captured["messages"][0]["content"] if block["type"] == "text"
    )
    assert "<text_layer>" not in prompt


@pytest.mark.asyncio
async def test_pages_past_the_vision_cap_keep_their_text_layer(monkeypatch):
    """The cap bounds vision spend on giant catalogs. It must not discard text
    pypdf reads for free — the tail is appended raw, under a marker that says
    exactly where reconciliation stopped."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(pdf_ocr, "MAX_VISION_PAGES", 4)
    monkeypatch.setattr(pdf_ocr, "PAGES_PER_REQUEST", 2)

    async def fake_chunk(client, chunk):
        return "chunk"

    monkeypatch.setattr(pdf_ocr, "_transcribe_chunk", fake_chunk)
    monkeypatch.setattr(pdf_ocr, "_text_layer_tail", lambda reader, start: "tail layer text")

    result = await pdf_ocr.transcribe_pdf(_blank_pdf(6))

    assert result.startswith("chunk\n\nchunk\n\n[vision transcription stopped at page 4 of 6")
    assert result.endswith("tail layer text")


@pytest.mark.asyncio
async def test_the_vision_cap_is_marked_not_silent(monkeypatch):
    """A scan past the cap has no text layer to fall back on. Bounding API
    spend is fine; pretending we read the whole document is not — the stored
    text must say where transcription stopped."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(pdf_ocr, "MAX_VISION_PAGES", 4)
    monkeypatch.setattr(pdf_ocr, "PAGES_PER_REQUEST", 2)

    async def fake_chunk(client, chunk):
        return "chunk"

    monkeypatch.setattr(pdf_ocr, "_transcribe_chunk", fake_chunk)
    monkeypatch.setattr(pdf_ocr, "_text_layer_tail", lambda reader, start: "")

    result = await pdf_ocr.transcribe_pdf(_blank_pdf(6))

    assert result == "chunk\n\nchunk\n\n[transcription stopped at page 4 of 6]"


@pytest.mark.asyncio
async def test_ocr_holds_at_most_the_concurrency_limit_in_memory(monkeypatch):
    """A scanned catalog sliced into N chunks, all built and sent at once, is
    what used to blow the extraction child's 1GB RLIMIT_AS (Heavi's Timken and
    supplier catalogs: MemoryError after 3 attempts). Peak memory must be the
    document plus OCR_CONCURRENCY slices, so both slice construction and the
    API call have to sit behind the semaphore."""
    import asyncio

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(pdf_ocr, "MAX_VISION_PAGES", 12)
    monkeypatch.setattr(pdf_ocr, "PAGES_PER_REQUEST", 1)

    in_flight = 0
    peak = 0

    async def fake_chunk(client, chunk):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.005)
        in_flight -= 1
        return "chunk"

    slice_calls = []
    real_slice = pdf_ocr._slice_pdf

    def counting_slice(reader, start, end):
        # Slices must be created lazily (inside the semaphore), never
        # all up front — laziness IS the memory fix.
        slice_calls.append(in_flight)
        return real_slice(reader, start, end)

    monkeypatch.setattr(pdf_ocr, "_transcribe_chunk", fake_chunk)
    monkeypatch.setattr(pdf_ocr, "_slice_pdf", counting_slice)

    result = await pdf_ocr.transcribe_pdf(_blank_pdf(12))

    assert result == "\n\n".join(["chunk"] * 12)
    assert peak <= pdf_ocr.OCR_CONCURRENCY
    # If slices were pre-built, every _slice_pdf call would happen before any
    # request is in flight; lazy construction interleaves them.
    assert len(slice_calls) == 12
    assert any(n > 0 for n in slice_calls)


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
async def test_textless_pdf_is_transcribed_and_stored(monkeypatch):
    conn = _FakeConnection(uuid.uuid4(), "application/pdf")
    _wire_extract_one(monkeypatch, conn, _blank_pdf(2))

    async def fake_transcribe(content):
        return "transcribed scan"

    monkeypatch.setattr(pdf_ocr, "transcribe_pdf", fake_transcribe)

    assert await extract_one._run(conn.file_id) == 0
    assert conn.persisted_text == "transcribed scan"


@pytest.mark.asyncio
async def test_upload_with_text_layer_skips_vision(monkeypatch):
    """Vision costs an API call per chunk — an upload the embedded-text path
    already handled must never hit the API."""
    conn = _FakeConnection(uuid.uuid4(), "text/plain")
    _wire_extract_one(monkeypatch, conn, b"plain text body")

    async def fail_transcribe(content):
        raise AssertionError("transcribe_pdf must not be called")

    monkeypatch.setattr(pdf_ocr, "transcribe_pdf", fail_transcribe)

    assert await extract_one._run(conn.file_id) == 0
    assert conn.persisted_text == "plain text body"


@pytest.mark.asyncio
async def test_non_pdf_without_text_never_transcribes(monkeypatch):
    conn = _FakeConnection(uuid.uuid4(), "image/png")
    _wire_extract_one(monkeypatch, conn, b"\x89PNG....")

    async def fail_transcribe(content):
        raise AssertionError("transcribe_pdf must not be called")

    monkeypatch.setattr(pdf_ocr, "transcribe_pdf", fail_transcribe)

    assert await extract_one._run(conn.file_id) == 0
    assert conn.persisted_text is None


@pytest.mark.asyncio
async def test_transcription_failure_marks_row_for_retry(monkeypatch):
    """An API blowup must land in extraction_error via the redacted-error
    path, not resolve to a 'done' row with NULL text."""
    file_id = uuid.uuid4()
    persisted_errors = []

    class FailingConnection(_FakeConnection):
        async def execute(self, query, file_id, error):
            persisted_errors.append(error)

    conn = FailingConnection(file_id, "application/pdf")
    _wire_extract_one(monkeypatch, conn, _blank_pdf(1))

    async def fail_transcribe(content):
        raise RuntimeError("api exploded with document contents inside")

    monkeypatch.setattr(pdf_ocr, "transcribe_pdf", fail_transcribe)

    assert await extract_one._run(file_id) == 1
    assert persisted_errors == ["Extraction failed: RuntimeError"]
