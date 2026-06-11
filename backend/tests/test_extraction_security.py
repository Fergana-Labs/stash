import subprocess
import uuid

import asyncpg
import pytest
import pytest_asyncio

from backend.services import file_extraction, storage_service
from backend.tasks import extraction
from backend.workers import extract_one


@pytest.mark.asyncio
async def test_extraction_child_output_is_discarded(monkeypatch):
    captured_kwargs = {}

    class FakeProcess:
        returncode = 1

        async def communicate(self):
            return b"token=secret-token and customer transcript", None

    async def create_process(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(extraction.asyncio, "create_subprocess_exec", create_process)

    code = await extraction._run_child(uuid.uuid4())

    assert code == 1
    assert captured_kwargs["stdout"] == subprocess.DEVNULL
    assert captured_kwargs["stderr"] == subprocess.DEVNULL


@pytest.mark.asyncio
async def test_extraction_parent_persists_only_failure_reason(monkeypatch):
    file_id = uuid.uuid4()
    persisted_errors: list[str] = []
    captured_logs: list[tuple[str, tuple]] = []

    async def claim_for_processing(received_file_id):
        assert received_file_id == file_id
        return True

    async def run_child(received_file_id):
        assert received_file_id == file_id
        return 1

    async def mark_failed(received_file_id, error):
        assert received_file_id == file_id
        persisted_errors.append(error)

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(extraction, "_claim_for_processing", claim_for_processing)
    monkeypatch.setattr(extraction, "_run_child", run_child)
    monkeypatch.setattr(extraction, "_mark_failed_externally", mark_failed)
    monkeypatch.setattr(extraction.logger, "warning", capture_warning)

    result = await extraction._extract(file_id)

    assert result == "failed"
    assert persisted_errors == ["exit_1"]
    assert captured_logs == [("extraction child failed file=%s reason=%s", (file_id, "exit_1"))]


@pytest.mark.asyncio
async def test_extraction_child_persists_redacted_error_with_exception_type(
    monkeypatch,
):
    """The dispatcher discards the child's stdout/stderr, so the files row is
    the only diagnostic channel: it must carry the exception class for triage
    but never the message, which can embed document text."""
    file_id = uuid.uuid4()
    persisted_errors: list[str] = []

    class FakeConnection:
        async def fetchrow(self, query, received_file_id):
            assert received_file_id == file_id
            return {
                "id": file_id,
                "storage_key": "customer/webflow/private-file.txt",
                "content_type": "text/plain",
                "extraction_attempts": 3,
            }

        async def execute(self, query, received_file_id, error):
            assert received_file_id == file_id
            persisted_errors.append(error)

        async def close(self):
            pass

    async def connect(database_url):
        return FakeConnection()

    async def download_file(storage_key):
        assert storage_key == "customer/webflow/private-file.txt"
        return b"customer transcript"

    async def close_storage():
        pass

    def extract_text(content, content_type):
        raise RuntimeError("token=secret-token and customer transcript")

    monkeypatch.setattr(asyncpg, "connect", connect)
    monkeypatch.setattr(storage_service, "download_file", download_file)
    monkeypatch.setattr(storage_service, "close", close_storage)
    monkeypatch.setattr(file_extraction, "extract_text", extract_text)

    result = await extract_one._run(file_id)

    assert result == 1
    assert persisted_errors == ["Extraction failed: RuntimeError"]
    assert "secret-token" not in str(persisted_errors)
    assert "customer transcript" not in str(persisted_errors)
    assert "private-file.txt" not in str(persisted_errors)


@pytest_asyncio.fixture
async def extraction_file(_db_pool):
    user_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    file_id = uuid.uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    await _db_pool.execute(
        "INSERT INTO workspaces (id, name, creator_id, invite_code) VALUES ($1, $2, $3, $4)",
        ws_id,
        f"ws_{ws_id.hex[:6]}",
        user_id,
        ws_id.hex[:12],
    )
    await _db_pool.execute(
        "INSERT INTO files (id, workspace_id, name, content_type, size_bytes, storage_key, "
        "uploaded_by) VALUES ($1, $2, 'doc.txt', 'text/plain', 1, $3, $4)",
        file_id,
        ws_id,
        f"key_{file_id.hex[:6]}",
        user_id,
    )
    return file_id


@pytest.mark.asyncio
async def test_parent_preserves_child_persisted_error(monkeypatch, extraction_file, _db_pool):
    """When the child persists its redacted error, the parent's external
    failure marking must not overwrite it with a bare exit-code marker —
    otherwise extraction failures are undiagnosable beyond 'exit_1'."""

    async def download_file(storage_key):
        return b"customer transcript"

    async def close_storage():
        pass

    def extract_text(content, content_type):
        raise RuntimeError("token=secret-token and customer transcript")

    async def run_child(file_id):
        return await extract_one._run(file_id)

    monkeypatch.setattr(storage_service, "download_file", download_file)
    monkeypatch.setattr(storage_service, "close", close_storage)
    monkeypatch.setattr(file_extraction, "extract_text", extract_text)
    monkeypatch.setattr(extraction, "_run_child", run_child)

    result = await extraction._extract(extraction_file)

    assert result == "failed"
    row = await _db_pool.fetchrow(
        "SELECT extraction_status, extraction_error FROM files WHERE id = $1",
        extraction_file,
    )
    assert row["extraction_error"] == "Extraction failed: RuntimeError"
    assert row["extraction_status"] == "pending"  # first attempt, still retryable


@pytest.mark.asyncio
async def test_parent_records_oom_when_child_dies_silently(monkeypatch, extraction_file, _db_pool):
    """A child killed before it could persist anything leaves the row in
    'processing'; only then does the parent record its own marker."""

    async def run_child(file_id):
        return -9

    monkeypatch.setattr(extraction, "_run_child", run_child)

    result = await extraction._extract(extraction_file)

    assert result == "failed"
    row = await _db_pool.fetchrow(
        "SELECT extraction_status, extraction_error FROM files WHERE id = $1",
        extraction_file,
    )
    assert row["extraction_error"] == "oom_or_kill"
    assert row["extraction_status"] == "pending"


def test_extract_text_logs_only_failure_metadata(monkeypatch):
    captured_logs: list[tuple[str, tuple]] = []

    def fail_pdf(content):
        raise RuntimeError("token=secret-token and customer transcript")

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(file_extraction, "_extract_pdf_embedded", fail_pdf)
    monkeypatch.setattr(file_extraction.logger, "warning", capture_warning)

    result = file_extraction.extract_text(b"%PDF", "application/pdf")

    assert result is None
    assert captured_logs == [
        (
            "file_extraction: extract_text failed content_type=%s exception_type=%s",
            ("application/pdf", "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
