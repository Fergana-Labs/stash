"""Drive importer task: route by MIME type.

The API endpoint dispatches this task once per selected Drive file ID.
The task itself reads the file's MIME, then routes:

- application/vnd.google-apps.document     → markdown page (native MD export)
- application/vnd.google-apps.spreadsheet  → one table per visible tab
                                              (via Drive's XLSX export +
                                              the shared xlsx_ingest service)
- application/vnd.openxmlformats-officedocument.presentationml.presentation
                                            → fixed-aspect slide page
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

import asyncpg
import httpx

from ....celery_app import celery
from ....database import get_pool
from ....services.xlsx_ingest import ingest_xlsx_bytes
from ....tasks._celery_helpers import run_async
from ...storage import get_valid_token

logger = logging.getLogger(__name__)

DRIVE_FILE_URL = (
    "https://www.googleapis.com/drive/v3/files/{file_id}?fields=id,name,mimeType,parents"
)
DRIVE_EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/export"

MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# Google's markdown export emits literal "- " / "* " / "1. " lines with no
# content. Tiptap's prosemirror schema rejects empty text nodes when loading
# the doc, which crashes the whole page render. Strip them at import time so
# the stored markdown is valid wherever it's later parsed.
_EMPTY_BULLET_RE = re.compile(r"^[ \t]*[-*+][ \t]*$\n?", re.MULTILINE)
_EMPTY_NUMBERED_RE = re.compile(r"^[ \t]*\d+\.[ \t]*$\n?", re.MULTILINE)


def _sanitize_drive_markdown(md: str) -> str:
    md = _EMPTY_BULLET_RE.sub("", md)
    md = _EMPTY_NUMBERED_RE.sub("", md)
    return md


async def _drive_get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    resp = await client.get(url)
    if resp.status_code == 404:
        raise RuntimeError("Drive file not found or not accessible to this account")
    resp.raise_for_status()
    return resp


async def _import_google_doc(
    client: httpx.AsyncClient,
    workspace_id: UUID,
    folder_id: UUID | None,
    user_id: UUID,
    file_id: str,
    name: str,
) -> dict:
    resp = await _drive_get(
        client,
        DRIVE_EXPORT_URL.format(file_id=file_id) + "?mimeType=text/markdown",
    )
    markdown = _sanitize_drive_markdown(resp.text)
    pool = get_pool()
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO pages (
                workspace_id, folder_id, name, content_markdown,
                content_type, html_layout, created_by
            ) VALUES ($1, $2, $3, $4, 'markdown', 'responsive', $5)
            RETURNING id
            """,
            workspace_id,
            folder_id,
            name,
            markdown,
            user_id,
        )
    except asyncpg.UniqueViolationError:
        row = await pool.fetchrow(
            """
            INSERT INTO pages (
                workspace_id, folder_id, name, content_markdown,
                content_type, html_layout, created_by
            ) VALUES ($1, $2, $3 || ' (imported)', $4, 'markdown', 'responsive', $5)
            RETURNING id
            """,
            workspace_id,
            folder_id,
            name,
            markdown,
            user_id,
        )
    return {"kind": "page", "page_id": str(row["id"]), "name": name}


async def _import(
    user_id: UUID,
    workspace_id: UUID,
    file_id: str,
    folder_id: UUID | None,
) -> dict:
    access_token = await get_valid_token(user_id, "google")
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
        meta_resp = await _drive_get(client, DRIVE_FILE_URL.format(file_id=file_id))
        meta = meta_resp.json()
        mime = meta.get("mimeType")
        name = meta.get("name") or "Imported file"

        if mime == MIME_GOOGLE_DOC:
            return await _import_google_doc(client, workspace_id, folder_id, user_id, file_id, name)

        if mime == MIME_GOOGLE_SHEET:
            return await _import_google_sheet(
                client, workspace_id, folder_id, user_id, file_id, name
            )

        if mime == MIME_PPTX:
            from .pptx import import_pptx_from_drive

            return await import_pptx_from_drive(
                client, workspace_id, folder_id, user_id, file_id, name
            )

        raise RuntimeError(f"Unsupported Drive MIME type: {mime}")


_XLSX_EXPORT_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _import_google_sheet(
    client: httpx.AsyncClient,
    workspace_id: UUID,
    folder_id: UUID | None,  # noqa: ARG001 — kept for signature parity with other importers
    user_id: UUID,
    file_id: str,
    name: str,
) -> dict:
    """Multi-tab Sheets import via Drive's XLSX export.

    Drive can export a Google Sheet as a real .xlsx workbook on a single
    HTTP call, so we don't need the Sheets API (or its extra OAuth
    scope) just to enumerate tabs. We hand the bytes to the same
    `ingest_xlsx_bytes` service the upload endpoint uses — one Stash
    table per visible sheet, types inferred per sheet.
    """
    resp = await _drive_get(
        client,
        DRIVE_EXPORT_URL.format(file_id=file_id) + f"?mimeType={_XLSX_EXPORT_MIME}",
    )
    created = await ingest_xlsx_bytes(
        workspace_id=workspace_id,
        user_id=user_id,
        content=resp.content,
        base_name=name,
        description_template=(f"Imported from Google Sheets ({file_id}) — sheet: {{sheet}}"),
    )
    if not created:
        raise RuntimeError("sheet had no visible tabs with data")

    first = created[0]
    return {
        "kind": "table",
        "table_id": str(first["id"]),
        "name": first["name"],
        "row_count": first.get("row_count"),
        "column_count": len(first.get("columns") or []),
        "sheet_count": len(created),
    }


@celery.task(name="backend.integrations.google.importers.drive_file.import_drive_file")
def import_drive_file(
    user_id: str,
    workspace_id: str,
    file_id: str,
    folder_id: str | None = None,
) -> dict:
    return run_async(
        _import(
            user_id=UUID(user_id),
            workspace_id=UUID(workspace_id),
            file_id=file_id,
            folder_id=UUID(folder_id) if folder_id else None,
        )
    )
