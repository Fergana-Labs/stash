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
DRIVE_EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/export"
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MAX_FOLDER_DEPTH = 8


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
    """Lazy read: export a Drive file to markdown with the owner's token.
    Non-Doc files have no markdown export and come back empty."""
    token = await get_valid_token(owner_user_id, "google")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
        export = await client.get(
            DRIVE_EXPORT_URL.format(file_id=file_id),
            params={"mimeType": "text/markdown"},
        )
        return export.text if export.status_code == 200 else ""
