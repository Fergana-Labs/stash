"""Google Drive → drive_index indexer (index only; body fetched lazily).

A Drive source's `external_ref` is a folder id ("root" for My Drive). We walk
the folder tree and store an INDEX ROW per file — its Drive-relative path, name,
and the Drive file id (`external_ref`). We never store the body; `read_source`
calls `fetch_drive_content` at read time, exporting the Google Doc to markdown
with the owner's token. The agent still navigates it like a file system.

Listing a folder + federated `fullText` search use the `drive.readonly` scope,
so the crawl and search see the user's whole Drive (not just app-picked files).

A whole-Drive source ("root") also crawls everything else the user can see but
does not own: the "Shared with me" corpus (files/folders others shared directly)
and every Shared Drive they belong to. Drive parents these outside My Drive, so
without a dedicated pass they would be invisible even though the user sees them
in the Drive UI. Every list/read call sets the all-drives flags; otherwise the
API silently drops Shared Drive items.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_FILE_URL = "https://www.googleapis.com/drive/v3/files/{file_id}"
DRIVE_EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/export"
DRIVE_DRIVES_URL = "https://www.googleapis.com/drive/v3/drives"
# Required on every files call so items living in Shared Drives are returned;
# without them the API pretends Shared Drive content does not exist.
ALL_DRIVES = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_SHORTCUT = "application/vnd.google-apps.shortcut"
MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_GOOGLE_SLIDE = "application/vnd.google-apps.presentation"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_FOLDER_DEPTH = 8
# Native (non-Google) files can be massive (terabyte videos). A whole-Drive
# source reads bodies inline on the request path, so it caps downloads tightly.
# A folder source extracts in a memory-bounded child process at sync time and
# can afford real catalogs — a 180 MB parts catalog is a normal thing to own.
MAX_NATIVE_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_EXTRACTION_DOWNLOAD_BYTES = 256 * 1024 * 1024


class DriveFileUnsupported(Exception):
    """Drive returned bytes we cannot turn into text — a video, an archive, a
    CAD drawing. Not an error to retry; the document has no text to index."""


class DriveFileTooLarge(Exception):
    pass


def _parse_time(value: str | None) -> datetime | None:
    """Drive returns RFC3339 ('...Z'); the column is timestamptz."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _list(client: httpx.AsyncClient, q: str) -> list[dict]:
    """All non-trashed files matching a Drive query `q` (paged)."""
    out: list[dict] = []
    page_token: str | None = None
    while True:
        params = {
            **ALL_DRIVES,
            "q": q,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, shortcutDetails)",
            "pageSize": 200,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = await client.get(DRIVE_LIST_URL, params=params)
        resp.raise_for_status()
        body = resp.json()
        out.extend(body.get("files", []))
        page_token = body.get("nextPageToken")
        if not page_token:
            return out


async def _target_modified_time(client: httpx.AsyncClient, file_id: str) -> str | None:
    resp = await client.get(
        DRIVE_FILE_URL.format(file_id=file_id),
        params={**ALL_DRIVES, "fields": "modifiedTime"},
    )
    resp.raise_for_status()
    return resp.json().get("modifiedTime")


async def _resolve_shortcut(client: httpx.AsyncClient, entry: dict) -> dict:
    """A shortcut's target as a plain entry, under the shortcut's display name.

    Shortcuts are Drive's symlinks; the walks must index the target, never the
    shortcut itself — a shortcut has no body (downloading one is a guaranteed
    403) and a folder shortcut's contents live under the target id. The
    shortcut's own modifiedTime is when the *shortcut* last moved, so a file
    target's real modifiedTime costs one metadata fetch — without it, edits to
    the target would never re-extract.
    """
    target = entry["shortcutDetails"]
    if target["targetMimeType"] == MIME_FOLDER:
        return {"id": target["targetId"], "name": entry["name"], "mimeType": MIME_FOLDER}
    return {
        "id": target["targetId"],
        "name": entry["name"],
        "mimeType": target["targetMimeType"],
        "modifiedTime": await _target_modified_time(client, target["targetId"]),
    }


async def _shared_drives(client: httpx.AsyncClient) -> list[dict]:
    """Every Shared Drive the user belongs to."""
    out: list[dict] = []
    page_token: str | None = None
    while True:
        params = {"pageSize": 100, "fields": "nextPageToken, drives(id, name)"}
        if page_token:
            params["pageToken"] = page_token
        resp = await client.get(DRIVE_DRIVES_URL, params=params)
        resp.raise_for_status()
        body = resp.json()
        out.extend(body.get("drives", []))
        page_token = body.get("nextPageToken")
        if not page_token:
            return out


async def index_google_drive(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    root = source["external_ref"] or "root"

    token = await get_valid_token(owner_user_id, "google")
    headers = {"Authorization": f"Bearer {token}"}
    present: list[str] = []
    # A file shared at top level and also nested in a shared folder shows up
    # twice; dedup by id so it is indexed once and folder cycles can't loop.
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:

        async def _index(entry: dict, prefix: str) -> None:
            name = entry["name"]
            path = f"{prefix}{name}"
            await source_service.upsert_index_row(
                table="drive_index",
                source_id=source_id,
                owner_user_id=owner_user_id,
                path=path,
                name=name,
                kind="file",
                external_ref=entry["id"],
                external_updated_at=_parse_time(entry.get("modifiedTime")),
            )
            present.append(path)

        async def _walk(folder_id: str, prefix: str, depth: int) -> None:
            if depth > MAX_FOLDER_DEPTH:
                return
            for entry in await _list(client, f"'{folder_id}' in parents and trashed = false"):
                if entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                if entry["mimeType"] == MIME_SHORTCUT:
                    entry = await _resolve_shortcut(client, entry)
                    if entry["id"] in seen:
                        continue
                    seen.add(entry["id"])
                name = entry["name"]
                if entry["mimeType"] == MIME_FOLDER:
                    await _walk(entry["id"], f"{prefix}{name}/", depth + 1)
                    continue
                await _index(entry, prefix)

        await _walk(root, "", 0)

        # A whole-Drive source also covers what the user can see but doesn't own.
        if root == "root":
            for entry in await _list(client, "sharedWithMe = true and trashed = false"):
                if entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                if entry["mimeType"] == MIME_SHORTCUT:
                    entry = await _resolve_shortcut(client, entry)
                    if entry["id"] in seen:
                        continue
                    seen.add(entry["id"])
                if entry["mimeType"] == MIME_FOLDER:
                    await _walk(entry["id"], f"Shared with me/{entry['name']}/", 1)
                    continue
                await _index(entry, "Shared with me/")

            for drive in await _shared_drives(client):
                await _walk(drive["id"], f"Shared drives/{drive['name']}/", 1)

    await source_service.remove_missing_documents("drive_index", source_id, present)
    logger.info("google drive source %s: indexed %d file(s)", source_id, len(present))
    return None


async def index_google_drive_folder(source: dict) -> str | None:
    """Crawl one picked folder and extract every file's text.

    Unlike a whole-Drive source this copies bodies: the folder is bounded, and an
    agent grepping a shelf of scanned parts catalogs cannot afford a Google round
    trip and a pypdf pass per file per query. The walk only records rows; the
    bodies are extracted by `backend.workers.extract_drive_one`, one child process
    per file, because pypdf on a 180 MB catalog will OOM whatever it runs inside.
    """
    from ...tasks.drive_extraction import extract_drive_document

    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    folder_id = source["external_ref"]

    token = await get_valid_token(owner_user_id, "google")
    headers = {"Authorization": f"Bearer {token}"}
    present: list[str] = []
    stale: list[UUID] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:

        async def _walk(parent_id: str, prefix: str, depth: int) -> None:
            if depth > MAX_FOLDER_DEPTH:
                return
            for entry in await _list(client, f"'{parent_id}' in parents and trashed = false"):
                if entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                if entry["mimeType"] == MIME_SHORTCUT:
                    entry = await _resolve_shortcut(client, entry)
                    if entry["id"] in seen:
                        continue
                    seen.add(entry["id"])
                name = entry["name"]
                if entry["mimeType"] == MIME_FOLDER:
                    await _walk(entry["id"], f"{prefix}{name}/", depth + 1)
                    continue
                path = f"{prefix}{name}"
                present.append(path)
                row_id = await source_service.upsert_drive_document(
                    source_id=source_id,
                    owner_user_id=owner_user_id,
                    path=path,
                    name=name,
                    external_ref=entry["id"],
                    external_updated_at=_parse_time(entry.get("modifiedTime")),
                )
                if row_id is not None:
                    stale.append(row_id)

        await _walk(folder_id, "", 0)

    await source_service.remove_missing_documents("drive_documents", source_id, present)
    for row_id in stale:
        extract_drive_document.delay(str(row_id))
    logger.info(
        "google drive folder %s: indexed %d file(s), %d to extract",
        source_id,
        len(present),
        len(stale),
    )
    return None


def _drive_q_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


async def search_drive(source: dict, query: str, limit: int = 25) -> list[dict]:
    """Federated search via Drive's `fullText contains` — Google full-text-indexes
    file contents server-side, so we never copy them. Maps the matched file ids
    back to our index paths (so read_source resolves them) and only returns files
    we've indexed for this source."""
    owner_user_id = UUID(source["owner_user_id"])
    source_id = UUID(source["id"])
    token = await get_valid_token(owner_user_id, "google")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        resp = await client.get(
            DRIVE_LIST_URL,
            params={
                **ALL_DRIVES,
                "q": f"fullText contains '{_drive_q_escape(query)}' and trashed = false",
                "fields": "files(id, name, modifiedTime)",
                "pageSize": min(limit, 50),
            },
        )
        resp.raise_for_status()
        files = resp.json().get("files", [])

    file_ids = [f["id"] for f in files]
    paths = await source_service.index_paths_for_refs("drive_index", source_id, file_ids)
    hits = []
    for f in files:
        entry = paths.get(f["id"])
        if entry is None:
            continue  # outside the indexed scope of this source
        path, name = entry
        hits.append(
            {
                "ref": path,
                "name": name,
                "snippet": "",
                "date_modified": _parse_time(f.get("modifiedTime")),
            }
        )
    return hits


async def fetch_drive_content(owner_user_id: UUID, file_id: str) -> str:
    """Lazy read for a whole-Drive source, on the request path. Bounded by
    MAX_NATIVE_DOWNLOAD_BYTES and never calls Claude vision — see
    `extract_drive_text` for the folder-source path, which runs at sync time
    in a child process."""
    return await extract_drive_text(
        owner_user_id,
        file_id,
        max_bytes=MAX_NATIVE_DOWNLOAD_BYTES,
        transcribe_pdfs=False,
    )


async def extract_drive_text(
    owner_user_id: UUID,
    file_id: str,
    *,
    max_bytes: int,
    transcribe_pdfs: bool,
) -> str:
    """A Drive file as text. Routes by MIME type:

    - Google Doc       → markdown export
    - Google Sheet     → XLSX export, rendered as one TSV block per sheet
    - Google Slides    → text/plain export
    - PDF              → with `transcribe_pdfs`, Claude vision grounded by the
                         embedded text layer (structure from the page images,
                         characters from the layer; a scan just has no layer);
                         without it, the raw pypdf text layer
    - Office formats (docx/pptx/xlsx) and text/* → file_extraction
    - Anything else    → DriveFileUnsupported

    The metadata lookup costs one extra round-trip but avoids storing mime types
    on every index row (and avoids drift if a file is converted).

    Raises rather than returning a placeholder or an empty string: a caller that
    cannot read a document must know it, not mistake it for a blank one.
    """
    token = await get_valid_token(owner_user_id, "google")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
        meta = await client.get(
            DRIVE_FILE_URL.format(file_id=file_id),
            params={**ALL_DRIVES, "fields": "mimeType,name,size"},
        )
        meta.raise_for_status()
        info = meta.json()
        mime = info.get("mimeType") or ""

        from ...services.file_extraction import extract_text, is_pdf

        if mime == MIME_GOOGLE_DOC:
            text = await _export(client, file_id, "text/markdown")
        elif mime == MIME_GOOGLE_SHEET:
            # XLSX export keeps every visible sheet (Drive's CSV export drops
            # everything except the first).
            xlsx = await _export_bytes(client, file_id, _XLSX_MIME)
            text = extract_text(xlsx, _XLSX_MIME)
        elif mime == MIME_GOOGLE_SLIDE:
            text = await _export(client, file_id, "text/plain")
        else:
            size = int(info.get("size") or 0)
            if size > max_bytes:
                raise DriveFileTooLarge(
                    f"{size // (1024 * 1024)} MB exceeds the {max_bytes // (1024 * 1024)} MB limit"
                )

            media = await client.get(
                DRIVE_FILE_URL.format(file_id=file_id),
                params={**ALL_DRIVES, "alt": "media"},
            )
            media.raise_for_status()
            content = media.content
            if len(content) > max_bytes:
                raise DriveFileTooLarge(
                    f"{len(content) // (1024 * 1024)} MB exceeds the "
                    f"{max_bytes // (1024 * 1024)} MB limit"
                )

            if is_pdf(mime) and transcribe_pdfs:
                # One codepath for every PDF: vision reads the pages, the
                # embedded text layer (empty for a scan) grounds the characters.
                # pypdf alone scrambles multi-column tables, and a scrambled
                # parts table reads fine while crossing the wrong part numbers.
                from ...services.pdf_ocr import transcribe_pdf

                text = await transcribe_pdf(content)
            else:
                # Defer to the file-extraction service so docx/pptx/xlsx/pdf/
                # text/* share the same handler set as the direct-upload
                # extraction queue.
                text = extract_text(content, mime)

        # Every branch lands here, Google-native exports included — an export
        # that came back empty must not be stored as a blank 'done' document.
        if not text:
            raise DriveFileUnsupported(f"no text could be extracted from {mime or 'unknown type'}")
        return text


async def _export(client: httpx.AsyncClient, file_id: str, mime: str) -> str:
    url = DRIVE_EXPORT_URL.format(file_id=file_id)
    resp = await client.get(url, params={**ALL_DRIVES, "mimeType": mime})
    # A failed export must raise, not read as an empty document — the folder
    # extraction path would otherwise store "" as a successfully extracted body.
    resp.raise_for_status()
    return resp.text


async def _export_bytes(client: httpx.AsyncClient, file_id: str, mime: str) -> bytes:
    url = DRIVE_EXPORT_URL.format(file_id=file_id)
    resp = await client.get(url, params={**ALL_DRIVES, "mimeType": mime})
    resp.raise_for_status()
    return resp.content
