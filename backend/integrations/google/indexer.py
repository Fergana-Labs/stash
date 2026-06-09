"""Google Drive → drive_index indexer (index only; body fetched lazily).

A Drive source's `external_ref` is a folder id ("root" for My Drive). We walk
the folder tree and store an INDEX ROW per file — its Drive-relative path, name,
and the Drive file id (`external_ref`). We never store the body; `read_source`
calls `fetch_drive_content` at read time, exporting the Google Doc to markdown
with the owner's token. The agent still navigates it like a file system.

Listing a folder + federated `fullText` search use the `drive.readonly` scope,
so the crawl and search see the user's whole Drive (not just app-picked files).
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
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_GOOGLE_SLIDE = "application/vnd.google-apps.presentation"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_FOLDER_DEPTH = 8
# Native (non-Google) files can be massive (terabyte videos). Cap downloads so
# a stray click doesn't drag a huge file into the agent's response.
MAX_NATIVE_DOWNLOAD_BYTES = 25 * 1024 * 1024


def _parse_time(value: str | None) -> datetime | None:
    """Drive returns RFC3339 ('...Z'); the column is timestamptz."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _list_folder(client: httpx.AsyncClient, folder_id: str) -> list[dict]:
    """All non-trashed children of a Drive folder."""
    out: list[dict] = []
    page_token: str | None = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime)",
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


async def index_google_drive(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    root = source["external_ref"] or "root"

    token = await get_valid_token(owner_user_id, "google")
    headers = {"Authorization": f"Bearer {token}"}
    present: list[str] = []

    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:

        async def _walk(folder_id: str, prefix: str, depth: int) -> None:
            if depth > MAX_FOLDER_DEPTH:
                return
            for entry in await _list_folder(client, folder_id):
                name = entry["name"]
                path = f"{prefix}{name}"
                if entry["mimeType"] == MIME_FOLDER:
                    await _walk(entry["id"], f"{path}/", depth + 1)
                    continue
                await source_service.upsert_index_row(
                    table="drive_index",
                    source_id=source_id,
                    workspace_id=workspace_id,
                    path=path,
                    name=name,
                    kind="file",
                    external_ref=entry["id"],
                    external_updated_at=_parse_time(entry.get("modifiedTime")),
                )
                present.append(path)

        await _walk(root, "", 0)

    await source_service.soft_delete_missing("drive_index", source_id, present)
    logger.info("google drive source %s: indexed %d file(s)", root, len(present))
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
                "q": f"fullText contains '{_drive_q_escape(query)}' and trashed = false",
                "fields": "files(id, name)",
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
        hits.append({"ref": path, "name": name, "snippet": ""})
    return hits


async def fetch_drive_content(owner_user_id: UUID, file_id: str) -> str:
    """Lazy read: route by Drive MIME type.

    - Google Doc       → markdown export
    - Google Sheet     → CSV export, rendered as a markdown table (first sheet)
    - Google Slides    → text/plain export
    - PDF              → bytes + pypdf extraction
    - Office formats (docx/pptx/xlsx) and text/* → bytes + file_extraction
    - Anything else    → empty string

    The metadata lookup costs one extra round-trip per read but avoids storing
    mime types on every index row (and avoids drift if a file is converted).
    """
    token = await get_valid_token(owner_user_id, "google")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
        meta = await client.get(
            DRIVE_FILE_URL.format(file_id=file_id),
            params={"fields": "mimeType,name,size"},
        )
        if meta.status_code != 200:
            return ""
        info = meta.json()
        mime = info.get("mimeType") or ""

        if mime == MIME_GOOGLE_DOC:
            return await _export(client, file_id, "text/markdown")
        if mime == MIME_GOOGLE_SHEET:
            # XLSX export keeps every visible sheet (Drive's CSV export drops
            # everything except the first). file_extraction renders one TSV
            # block per sheet.
            xlsx = await _export_bytes(client, file_id, _XLSX_MIME)
            if not xlsx:
                return ""
            from ...services.file_extraction import extract_text

            return extract_text(xlsx, _XLSX_MIME) or ""
        if mime == MIME_GOOGLE_SLIDE:
            return await _export(client, file_id, "text/plain")

        # Native files: cap by size, download bytes, route by mime to a text
        # extractor.
        size = int(info.get("size") or 0)
        if size and size > MAX_NATIVE_DOWNLOAD_BYTES:
            return f"_(file too large to inline: {size // (1024 * 1024)} MB)_"

        media = await client.get(
            DRIVE_FILE_URL.format(file_id=file_id),
            params={"alt": "media"},
        )
        if media.status_code != 200:
            return ""
        content = media.content
        if len(content) > MAX_NATIVE_DOWNLOAD_BYTES:
            return f"_(file too large to inline: {len(content) // (1024 * 1024)} MB)_"

        # Defer to the file-extraction service so docx/pptx/xlsx/pdf/text/*
        # share the same handler set as the direct-upload extraction queue.
        from ...services.file_extraction import extract_text

        text = extract_text(content, mime)
        return text or ""


async def _export(client: httpx.AsyncClient, file_id: str, mime: str) -> str:
    resp = await client.get(
        DRIVE_EXPORT_URL.format(file_id=file_id), params={"mimeType": mime}
    )
    return resp.text if resp.status_code == 200 else ""


async def _export_bytes(client: httpx.AsyncClient, file_id: str, mime: str) -> bytes:
    resp = await client.get(
        DRIVE_EXPORT_URL.format(file_id=file_id), params={"mimeType": mime}
    )
    return resp.content if resp.status_code == 200 else b""


