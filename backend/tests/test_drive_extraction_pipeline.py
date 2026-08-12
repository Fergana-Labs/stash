"""The sync → enqueue → extract → store pipeline, end to end minus the two
external calls (Drive's API and Claude vision), which are stubbed.

Every other line runs for real: the folder walk, the row upsert, the staleness
check that decides what to re-extract, the Celery task's claim guard, and the
child process's status transitions. Without this the read-side tests only prove
that a correctly populated table reads correctly — never that anything fills it.
"""

import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from backend.database import get_pool
from backend.integrations.google import indexer
from backend.services import file_extraction, pdf_ocr, source_service
from backend.tasks import drive_extraction
from backend.workers import extract_drive_one

from .conftest import unique_name

pytestmark = pytest.mark.asyncio

MODIFIED = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


async def _folder_reads_fine(_client, _folder_id) -> None:
    """The health check the walk runs first; healthy in every test that is
    about the walk itself. Its own failure modes are covered separately."""
    return None


async def _owner(client: AsyncClient) -> UUID:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("pipe"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


async def _folder_source(owner_id: UUID) -> dict:
    return await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive_folder",
        external_ref=f"folder-{uuid4().hex[:8]}",
        display_name="Catalogs",
    )


def _stub_drive(monkeypatch, files: list[dict]) -> list[str]:
    """Drive returns `files`; record every row id handed to the extraction queue."""

    async def fake_token(*_a, **_k):
        return "token"

    async def fake_list(_client, q):
        return files if "in parents" in q else []

    enqueued: list[str] = []
    monkeypatch.setattr(indexer, "get_valid_token", fake_token)
    monkeypatch.setattr(indexer, "_list", fake_list)
    monkeypatch.setattr(indexer, "_require_readable_folder", _folder_reads_fine)
    monkeypatch.setattr(
        drive_extraction.extract_drive_document, "delay", lambda row_id: enqueued.append(row_id)
    )
    return enqueued


def _stub_drive_listings(monkeypatch, listings: dict[str, list[dict]]) -> list[str]:
    """Like `_stub_drive`, but keyed by parent folder id so a walk that descends
    into subfolders (or shortcut targets) sees each folder's own children.
    Shortcut targets report MODIFIED as their modifiedTime."""

    async def fake_token(*_a, **_k):
        return "token"

    async def fake_list(_client, q):
        if "in parents" not in q:
            return []
        return listings.get(q.split("'")[1], [])

    async def fake_target_time(_client, _file_id):
        return _iso(MODIFIED)

    enqueued: list[str] = []
    monkeypatch.setattr(indexer, "get_valid_token", fake_token)
    monkeypatch.setattr(indexer, "_list", fake_list)
    monkeypatch.setattr(indexer, "_target_modified_time", fake_target_time)
    monkeypatch.setattr(indexer, "_require_readable_folder", _folder_reads_fine)
    monkeypatch.setattr(
        drive_extraction.extract_drive_document, "delay", lambda row_id: enqueued.append(row_id)
    )
    return enqueued


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _entry(name: str, modified: datetime = MODIFIED) -> dict:
    return {
        "id": f"drive-{name}",
        "name": name,
        "mimeType": "application/pdf",
        "modifiedTime": _iso(modified),
    }


def _shortcut(name: str, target_id: str, target_mime: str) -> dict:
    # The shortcut's own modifiedTime is deliberately ancient: anything that
    # leaks it into a row would fail the freshness assertions.
    return {
        "id": f"shortcut-{name}",
        "name": name,
        "mimeType": "application/vnd.google-apps.shortcut",
        "modifiedTime": _iso(datetime(2020, 1, 1, tzinfo=UTC)),
        "shortcutDetails": {"targetId": target_id, "targetMimeType": target_mime},
    }


async def test_the_sync_walk_records_files_and_queues_each_for_extraction(
    client: AsyncClient, monkeypatch
):
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    enqueued = _stub_drive(monkeypatch, [_entry("Bendix.pdf"), _entry("Meritor.pdf")])

    await indexer.index_google_drive_folder(src)

    rows = await get_pool().fetch(
        "SELECT path, extraction_status, content FROM drive_documents "
        "WHERE source_id = $1 ORDER BY path",
        UUID(src["id"]),
    )
    assert [r["path"] for r in rows] == ["Bendix.pdf", "Meritor.pdf"]
    assert all(r["extraction_status"] == "pending" for r in rows)
    assert all(r["content"] is None for r in rows)
    assert len(enqueued) == 2


async def test_an_unchanged_file_is_not_re_extracted(client: AsyncClient, monkeypatch):
    """OCR of a scanned catalog is a Claude vision call. Re-running it every
    thirty minutes for a file nobody touched would be the whole cost of this
    feature, paid forever."""
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    _stub_drive(monkeypatch, [_entry("Bendix.pdf")])
    await indexer.index_google_drive_folder(src)

    await get_pool().execute(
        "UPDATE drive_documents SET extraction_status = 'done', content = 'text' "
        "WHERE source_id = $1",
        UUID(src["id"]),
    )

    enqueued = _stub_drive(monkeypatch, [_entry("Bendix.pdf")])
    await indexer.index_google_drive_folder(src)

    assert enqueued == []


async def test_a_file_edited_in_drive_is_re_extracted(client: AsyncClient, monkeypatch):
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    _stub_drive(monkeypatch, [_entry("Bendix.pdf")])
    await indexer.index_google_drive_folder(src)
    await get_pool().execute(
        "UPDATE drive_documents SET extraction_status = 'done', content = 'old' "
        "WHERE source_id = $1",
        UUID(src["id"]),
    )

    later = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)
    enqueued = _stub_drive(monkeypatch, [_entry("Bendix.pdf", later)])
    await indexer.index_google_drive_folder(src)

    assert len(enqueued) == 1
    row = await get_pool().fetchrow(
        "SELECT extraction_status, content FROM drive_documents WHERE source_id = $1",
        UUID(src["id"]),
    )
    assert row["extraction_status"] == "pending"
    # The old text stays readable while the new extraction runs.
    assert row["content"] == "old"


async def test_a_shortcut_to_a_folder_indexes_the_targets_files(client: AsyncClient, monkeypatch):
    """A Drive shortcut is how a customer symlinks a live folder into the synced
    one without copying it. The walk must descend into the target folder; the
    shortcut itself must get no row — it has no body, so its row could only ever
    be a permanently failed extraction."""
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    listings = {
        src["external_ref"]: [
            _shortcut("Transcripts", "tgt-folder", "application/vnd.google-apps.folder")
        ],
        "tgt-folder": [_entry("Bendix.pdf")],
    }
    enqueued = _stub_drive_listings(monkeypatch, listings)

    await indexer.index_google_drive_folder(src)

    rows = await get_pool().fetch(
        "SELECT path, external_ref FROM drive_documents WHERE source_id = $1 ORDER BY path",
        UUID(src["id"]),
    )
    assert [r["path"] for r in rows] == ["Transcripts/Bendix.pdf"]
    assert rows[0]["external_ref"] == "drive-Bendix.pdf"
    assert len(enqueued) == 1


async def test_a_shortcut_to_a_file_extracts_the_target(client: AsyncClient, monkeypatch):
    """The row must carry the target's id and the target's modifiedTime.
    Downloading the shortcut id is a guaranteed 403, and the shortcut's own
    modifiedTime only moves when the link moves — keyed on it, edits to the
    target would never re-extract."""
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    listings = {src["external_ref"]: [_shortcut("Catalog.pdf", "tgt-file", "application/pdf")]}
    enqueued = _stub_drive_listings(monkeypatch, listings)

    await indexer.index_google_drive_folder(src)

    row = await get_pool().fetchrow(
        "SELECT path, external_ref, external_updated_at FROM drive_documents WHERE source_id = $1",
        UUID(src["id"]),
    )
    assert row["path"] == "Catalog.pdf"
    assert row["external_ref"] == "tgt-file"
    assert row["external_updated_at"] == MODIFIED
    assert len(enqueued) == 1


async def test_a_shortcut_to_an_already_walked_folder_is_skipped(client: AsyncClient, monkeypatch):
    """A folder and a shortcut to that same folder in one tree must index its
    files once, and a shortcut cycle must not recurse forever."""
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    listings = {
        src["external_ref"]: [
            {
                "id": "tgt-folder",
                "name": "Transcripts",
                "mimeType": "application/vnd.google-apps.folder",
            },
            _shortcut("Transcripts", "tgt-folder", "application/vnd.google-apps.folder"),
        ],
        "tgt-folder": [_entry("Bendix.pdf")],
    }
    enqueued = _stub_drive_listings(monkeypatch, listings)

    await indexer.index_google_drive_folder(src)

    rows = await get_pool().fetch(
        "SELECT path FROM drive_documents WHERE source_id = $1", UUID(src["id"])
    )
    assert [r["path"] for r in rows] == ["Transcripts/Bendix.pdf"]
    assert len(enqueued) == 1


async def _pending_row(client: AsyncClient, monkeypatch) -> tuple[UUID, UUID]:
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    _stub_drive(monkeypatch, [_entry("Scan.pdf")])
    await indexer.index_google_drive_folder(src)
    row = await get_pool().fetchrow(
        "SELECT id FROM drive_documents WHERE source_id = $1", UUID(src["id"])
    )
    return row["id"], UUID(src["id"])


def _stub_extract(monkeypatch, result):
    """`result` is the text to return, or an exception to raise."""

    async def fake(*_a, **_k):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(indexer, "extract_drive_text", fake)
    monkeypatch.setattr("backend.database.close_db", _noop)


async def _noop(*_a, **_k):
    """The child closes the pool on exit. In-process that would close the pool
    the rest of the test session shares."""


async def test_the_child_stores_extracted_text(client: AsyncClient, monkeypatch):
    row_id, _ = await _pending_row(client, monkeypatch)
    _stub_extract(monkeypatch, "STEMCO 2036 1036 382-8036")

    assert await extract_drive_one._run(row_id) == 0

    row = await get_pool().fetchrow(
        "SELECT content, extraction_status, extraction_error, embed_stale "
        "FROM drive_documents WHERE id = $1",
        row_id,
    )
    assert row["content"] == "STEMCO 2036 1036 382-8036"
    assert row["extraction_status"] == "done"
    assert row["extraction_error"] is None
    # The embeddings reconciler picks the row up from here.
    assert row["embed_stale"] is True


@pytest.mark.parametrize(
    ("raised", "status"),
    [
        (indexer.DriveFileUnsupported("no text could be extracted"), "unsupported"),
        (indexer.DriveFileTooLarge("300 MB exceeds the 256 MB limit"), "too_large"),
    ],
)
async def test_the_child_records_why_a_file_has_no_text(
    client: AsyncClient, monkeypatch, raised: Exception, status: str
):
    """Exit 0, because an unreadable document is a fact about the document, not a
    crash to retry. The reason is what a later read reports to the agent."""
    row_id, _ = await _pending_row(client, monkeypatch)
    _stub_extract(monkeypatch, raised)

    assert await extract_drive_one._run(row_id) == 0

    row = await get_pool().fetchrow(
        "SELECT content, extraction_status, extraction_error FROM drive_documents WHERE id = $1",
        row_id,
    )
    assert row["content"] is None
    assert row["extraction_status"] == status
    assert str(raised) in row["extraction_error"]


async def test_the_child_redacts_an_unexpected_failure_and_leaves_it_retryable(
    client: AsyncClient, monkeypatch
):
    """The persisted error names the exception class only — its message could
    carry document text or a provider response."""
    row_id, _ = await _pending_row(client, monkeypatch)
    _stub_extract(monkeypatch, RuntimeError("token abc123 leaked into the message"))

    assert await extract_drive_one._run(row_id) == 1

    row = await get_pool().fetchrow(
        "SELECT extraction_status, extraction_error FROM drive_documents WHERE id = $1",
        row_id,
    )
    assert row["extraction_status"] == "pending"  # attempts still under the cap
    assert row["extraction_error"] == "Extraction failed: RuntimeError"
    assert "abc123" not in row["extraction_error"]


async def test_a_row_is_claimed_once(client: AsyncClient, monkeypatch):
    """The sync walk enqueues, and so does the Beat sweep. Extracting twice would
    pay for the same OCR twice."""
    row_id, _ = await _pending_row(client, monkeypatch)
    monkeypatch.setattr(drive_extraction, "_run_child", _child_ok)

    assert await drive_extraction._extract(row_id) == "ok"
    assert await drive_extraction._extract(row_id) == "skipped"


async def _child_ok(_row_id):
    return 0, ""


async def _child_oom(_row_id):
    return 137, ""


async def test_a_child_killed_by_the_oom_killer_is_recorded(client: AsyncClient, monkeypatch):
    """A SIGKILL leaves the child no chance to write its own reason, so the parent
    writes one. Otherwise the row sits in 'processing' forever."""
    row_id, _ = await _pending_row(client, monkeypatch)
    monkeypatch.setattr(drive_extraction, "_run_child", _child_oom)

    assert await drive_extraction._extract(row_id) == "failed"

    row = await get_pool().fetchrow(
        "SELECT extraction_status, extraction_error FROM drive_documents WHERE id = $1",
        row_id,
    )
    assert row["extraction_status"] == "pending"  # retryable, attempts = 1
    assert "out of memory" in row["extraction_error"]


async def test_a_startup_crash_reaches_the_parents_log(monkeypatch):
    """A child that dies before it can write its own reason — an import
    failure, a refused DB connection — must not vanish into a bare 'exited 1'.
    The parent captures the stderr tail, which carries the failure."""
    monkeypatch.setattr(drive_extraction, "_CHILD_MODULE", "backend.no_such_module")

    code, tail = await drive_extraction._run_child(uuid4())

    assert code == 1
    assert "No module named" in tail


def test_a_child_crash_report_names_the_class_but_never_the_message(monkeypatch, capsys):
    """The stderr crash report follows the same redaction rule as the row's
    persisted error: frames locate the failure, the message stays out — it can
    embed document text or provider responses, and this reaches the logs."""
    monkeypatch.setattr(extract_drive_one, "_apply_memory_limit", lambda: None)

    async def _boom(_row_id):
        raise RuntimeError("token abc123 leaked into the message")

    monkeypatch.setattr(extract_drive_one, "_run", _boom)
    monkeypatch.setattr(sys, "argv", ["extract_drive_one", str(uuid4())])

    with pytest.raises(SystemExit) as exc:
        extract_drive_one.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "_boom" in err  # the frames locate the failure
    assert "abc123" not in err


async def test_a_file_removed_from_drive_stops_being_readable(client: AsyncClient, monkeypatch):
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    _stub_drive(monkeypatch, [_entry("Bendix.pdf"), _entry("Meritor.pdf")])
    await indexer.index_google_drive_folder(src)

    _stub_drive(monkeypatch, [_entry("Bendix.pdf")])
    await indexer.index_google_drive_folder(src)

    live = await get_pool().fetch(
        "SELECT path FROM drive_documents WHERE source_id = $1 AND deleted_at IS NULL",
        UUID(src["id"]),
    )
    assert [r["path"] for r in live] == ["Bendix.pdf"]


# --- PDF routing: which parser a Drive PDF gets --------------------------------
#
# A folder source's PDFs go through Claude vision grounded by the embedded text
# layer (structure from the images, characters from the layer). A whole-Drive
# source reads on the request path and must never pay for an API call.


class _FakeResponse:
    def __init__(self, *, json_body=None, content=b""):
        self._json = json_body
        self.content = content
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class _FakeDriveHttp:
    """Stands in for httpx.AsyncClient: a metadata lookup, then a media download."""

    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, _url, params=None):
        if "fields" in (params or {}):
            return _FakeResponse(json_body={"mimeType": "application/pdf", "size": "9"})
        return _FakeResponse(content=b"%PDF-fake")


def _stub_drive_http(monkeypatch):
    async def fake_token(*_a, **_k):
        return "token"

    monkeypatch.setattr(indexer, "get_valid_token", fake_token)
    monkeypatch.setattr(indexer, "httpx", SimpleNamespace(AsyncClient=_FakeDriveHttp))


async def test_a_folder_pdf_is_vision_reconciled_not_raw_pypdf(monkeypatch):
    """The behavior this feature adds: a text-layer PDF in a folder source does
    not stop at pypdf — it goes to vision with the layer as grounding, because
    pypdf alone flattens a three-column parts table into a stream that crosses
    part numbers between columns."""
    _stub_drive_http(monkeypatch)
    seen = {}

    async def fake_transcribe(content):
        seen["bytes"] = content
        return "288241R\tOR288241\t106113"

    monkeypatch.setattr(pdf_ocr, "transcribe_pdf", fake_transcribe)

    text = await indexer.extract_drive_text(
        uuid4(), "file-1", max_bytes=10_000, transcribe_pdfs=True
    )

    assert text == "288241R\tOR288241\t106113"
    assert seen["bytes"] == b"%PDF-fake"


async def test_a_whole_drive_pdf_never_pays_for_vision(monkeypatch):
    """Whole-Drive reads run per-request against an unbounded corpus; an API
    call per read is an unbounded bill. They get the raw text layer only."""
    _stub_drive_http(monkeypatch)

    async def fail_transcribe(content):
        raise AssertionError("a whole-Drive read must not call the vision API")

    monkeypatch.setattr(pdf_ocr, "transcribe_pdf", fail_transcribe)
    monkeypatch.setattr(file_extraction, "extract_text", lambda _c, _ct: "raw text layer")

    text = await indexer.extract_drive_text(
        uuid4(), "file-1", max_bytes=10_000, transcribe_pdfs=False
    )

    assert text == "raw text layer"


class _FakeDriveResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError("the guard must classify error statuses before this")


class _FakeDriveClient:
    def __init__(self, response: _FakeDriveResponse):
        self._response = response

    async def get(self, *_args, **_kwargs) -> _FakeDriveResponse:
        return self._response


HEALTHY = _FakeDriveResponse(200, {"trashed": False, "capabilities": {"canListChildren": True}})
TRASHED = _FakeDriveResponse(200, {"trashed": True, "capabilities": {"canListChildren": True}})
UNLISTABLE = _FakeDriveResponse(200, {"trashed": False, "capabilities": {"canListChildren": False}})
GONE = _FakeDriveResponse(404, {"error": {"message": "File not found"}})


@pytest.mark.parametrize(
    "response,label",
    [(GONE, "gone or access revoked"), (TRASHED, "trashed"), (UNLISTABLE, "not listable")],
)
async def test_an_unreadable_folder_stops_the_sync_instead_of_reading_as_empty(response, label):
    """Drive reports a folder you cannot see as a folder with no files in it.
    Believed, that empties the shelf — so each unreadable shape has to be
    caught here, where the sync can still be stopped."""
    with pytest.raises(source_service.SourceSyncUserError) as caught:
        await indexer._require_readable_folder(_FakeDriveClient(response), "folder-1")
    assert "Nothing was deleted" in str(caught.value), label


async def test_a_healthy_folder_passes_the_check():
    """The guard must not stand between a working folder and its sync."""
    assert await indexer._require_readable_folder(_FakeDriveClient(HEALTHY), "folder-1") is None


async def test_an_unreadable_folder_leaves_its_documents_in_place(client: AsyncClient, monkeypatch):
    """The point of the guard: the delete-to-mirror sweep never runs, so a
    revoked folder costs you nothing. These bodies were expensive — a scanned
    catalog is an OCR pass — and drive_documents deletes physically."""
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    _stub_drive(monkeypatch, [_entry("Bendix.pdf")])
    await indexer.index_google_drive_folder(src)

    async def folder_is_gone(_client, _folder_id):
        raise source_service.SourceSyncUserError("gone")

    monkeypatch.setattr(indexer, "_require_readable_folder", folder_is_gone)

    with pytest.raises(source_service.SourceSyncUserError):
        await indexer.index_google_drive_folder(src)

    surviving = await get_pool().fetchval(
        "SELECT count(*) FROM drive_documents WHERE source_id = $1 AND deleted_at IS NULL",
        UUID(src["id"]),
    )
    assert surviving == 1


async def test_a_folder_that_really_was_emptied_still_mirrors(client: AsyncClient, monkeypatch):
    """The guard must not turn into a refusal to ever delete. A readable folder
    reporting no files means the documents are genuinely gone."""
    owner_id = await _owner(client)
    src = await _folder_source(owner_id)
    _stub_drive(monkeypatch, [_entry("Bendix.pdf")])
    await indexer.index_google_drive_folder(src)

    _stub_drive(monkeypatch, [])
    await indexer.index_google_drive_folder(src)

    surviving = await get_pool().fetchval(
        "SELECT count(*) FROM drive_documents WHERE source_id = $1 AND deleted_at IS NULL",
        UUID(src["id"]),
    )
    assert surviving == 0
