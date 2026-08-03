"""PDFs reach the knowledge base via vision transcription grounded by the text layer.

pypdf alone has exact characters but scrambles multi-column tables; vision
alone has the layout but can misread a digit — and a misread digit in a part
number ships the wrong part. `transcribe_pdf` sends both in one request:
structure from the page images, characters from the embedded text layer. A
scanned PDF simply has no layer to attach and degrades to pure OCR.

These tests pin that contract: the layer rides along as grounding, the prompt
demands markdown tables and figure descriptions (diagram content must survive
into text), pages past the vision cap keep their raw text layer (the cap
bounds API spend, it must not discard free text), failures surface loudly,
and every PDF — digital or scanned — takes the vision path, because the
pypdf-only path stores scrambled tables that read fine while crossing the
wrong part numbers.
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


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeGeminiClient:
    def __init__(self, payload):
        self._payload = payload
        self.captured = {}

    async def post(self, url, json):
        self.captured["url"] = url
        self.captured["json"] = json
        return _FakeResponse(self._payload)


def _payload(text: str, finish_reason: str = "STOP") -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish_reason}]}


def _prompt_of(client: _FakeGeminiClient) -> str:
    parts = client.captured["json"]["contents"][0]["parts"]
    return "".join(p.get("text", "") for p in parts if "text" in p)


@pytest.mark.asyncio
async def test_transcribe_pdf_fails_loud_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await pdf_ocr.transcribe_pdf(_blank_pdf(1))


@pytest.mark.asyncio
async def test_transcribe_pdf_chunks_pages_and_joins_transcriptions(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

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
    client = _FakeGeminiClient(_payload("reconciled"))
    monkeypatch.setattr(pdf_ocr, "extract_text", lambda content, ct: "288241R\tOR288241\t106113")

    result = await pdf_ocr._transcribe_chunk(client, _blank_pdf(1))

    assert result == "reconciled"
    prompt = _prompt_of(client)
    assert "288241R\tOR288241\t106113" in prompt
    assert "<text_layer>" in prompt
    # A page can render a token cut off (page edge, cropped scan) while the
    # layer holds the whole string; the instruction to recover it must ride
    # along, or clipped part numbers come back as fragments.
    assert "complete string" in prompt


@pytest.mark.asyncio
async def test_the_prompt_demands_markdown_tables_and_figure_descriptions(monkeypatch):
    """The two output requirements the knowledge base depends on: tables must
    come back as markdown tables (a flattened parts table crosses the wrong
    part numbers), and figures must be described in place (a diagram's
    identifying details — the only way to tell a 4515 shoe from a 4707 —
    otherwise never enter the searchable text)."""
    client = _FakeGeminiClient(_payload("out"))
    monkeypatch.setattr(pdf_ocr, "extract_text", lambda content, ct: None)

    await pdf_ocr._transcribe_chunk(client, _blank_pdf(1))

    prompt = _prompt_of(client)
    assert "markdown table" in prompt
    assert "[Figure:" in prompt


@pytest.mark.asyncio
async def test_a_scan_sends_no_grounding_block(monkeypatch):
    """A scan has no text layer. The prompt must not carry an empty
    <text_layer> block that invites the model to treat 'nothing' as truth."""
    client = _FakeGeminiClient(_payload("ocr"))
    monkeypatch.setattr(pdf_ocr, "extract_text", lambda content, ct: None)

    await pdf_ocr._transcribe_chunk(client, _blank_pdf(1))

    assert "<text_layer>" not in _prompt_of(client)


@pytest.mark.asyncio
async def test_a_truncated_transcription_is_marked_not_silent(monkeypatch):
    client = _FakeGeminiClient(_payload("partial", finish_reason="MAX_TOKENS"))
    monkeypatch.setattr(pdf_ocr, "extract_text", lambda content, ct: None)

    result = await pdf_ocr._transcribe_chunk(client, _blank_pdf(1))

    assert result == "partial\n\n[transcription truncated]"


@pytest.mark.asyncio
async def test_an_empty_candidate_list_raises(monkeypatch):
    """No candidates means the API refused or filtered the request. That must
    surface as a retryable failure, never be stored as a blank document."""
    client = _FakeGeminiClient({"candidates": []})
    monkeypatch.setattr(pdf_ocr, "extract_text", lambda content, ct: None)

    with pytest.raises(RuntimeError, match="no candidates"):
        await pdf_ocr._transcribe_chunk(client, _blank_pdf(1))


@pytest.mark.asyncio
async def test_pages_past_the_vision_cap_keep_their_text_layer(monkeypatch):
    """The cap bounds vision spend on giant catalogs. It must not discard text
    pypdf reads for free — the tail is appended raw, under a marker that says
    exactly where reconciliation stopped."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
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
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
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

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
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
async def test_every_uploaded_pdf_is_transcribed_and_stored(monkeypatch):
    """Digital PDFs included: the pypdf-only path stores a scrambled table
    that reads fine while crossing the wrong part numbers, so a text layer
    must not divert a PDF away from vision — it rides along as grounding."""
    conn = _FakeConnection(uuid.uuid4(), "application/pdf")
    _wire_extract_one(monkeypatch, conn, _blank_pdf(2))

    async def fake_transcribe(content):
        return "vision transcription"

    monkeypatch.setattr(pdf_ocr, "transcribe_pdf", fake_transcribe)

    assert await extract_one._run(conn.file_id) == 0
    assert conn.persisted_text == "vision transcription"


@pytest.mark.asyncio
async def test_non_pdf_upload_never_transcribes(monkeypatch):
    """Vision costs an API call per chunk — only PDFs take that path."""
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


@pytest.mark.asyncio
async def test_a_rate_limit_hands_the_attempt_back(monkeypatch):
    """HTTP 429 means "later", not "broken". Counting it against the attempt
    budget let one quota blip march 20 real customer documents to permanent
    failure in seconds — the row must go back to pending with its attempt
    returned, so the next dispatch retries it as if this one never happened."""
    import httpx

    file_id = uuid.uuid4()
    executed_queries = []

    class RateLimitedConnection(_FakeConnection):
        async def execute(self, query, *args):
            executed_queries.append(query)

    conn = RateLimitedConnection(file_id, "application/pdf")
    _wire_extract_one(monkeypatch, conn, _blank_pdf(1))

    async def rate_limited_transcribe(content):
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
        raise httpx.HTTPStatusError(
            "429", request=request, response=httpx.Response(429, request=request)
        )

    monkeypatch.setattr(pdf_ocr, "transcribe_pdf", rate_limited_transcribe)

    assert await extract_one._run(file_id) == 1
    (query,) = executed_queries
    assert "extraction_status = 'pending'" in query
    assert "extraction_attempts = greatest(extraction_attempts - 1, 0)" in query
    assert "failed" not in query
