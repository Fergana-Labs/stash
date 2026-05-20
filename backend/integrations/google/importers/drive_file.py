"""Drive importer task: route by MIME type.

The API endpoint dispatches this task once per selected Drive file ID.
The task itself reads the file's MIME, then routes:

- application/vnd.google-apps.document     → markdown page (native MD export)
- application/vnd.google-apps.spreadsheet  → table (not implemented yet)
- application/vnd.openxmlformats-officedocument.presentationml.presentation
                                            → fixed-aspect slide page (not implemented yet)

Sheet + PPTX importers are stubbed for follow-up work — they fail loud
with a clear message rather than silently dropping content.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import secrets
from uuid import UUID

import asyncpg
import httpx

from ....celery_app import celery
from ....database import get_pool
from ....services import table_service
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


async def _import_google_sheet(
    client: httpx.AsyncClient,
    workspace_id: UUID,
    folder_id: UUID | None,
    user_id: UUID,
    file_id: str,
    name: str,
) -> dict:
    """First-tab-only Sheets import.

    Drive's CSV export already returns only the first sheet — that's
    the v1 limitation. Header row becomes the column names (text type
    for every column; the user can refine column types in the UI
    later). Empty cells stay empty; we don't try to coerce types.
    """
    resp = await _drive_get(
        client,
        DRIVE_EXPORT_URL.format(file_id=file_id) + "?mimeType=text/csv",
    )
    text = resp.text
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise RuntimeError("sheet is empty")

    header = rows[0]
    if not any(h.strip() for h in header):
        raise RuntimeError("sheet has no header row")

    columns = []
    seen_names: dict[str, int] = {}
    for raw_name in header:
        col_name = (raw_name or "").strip() or "column"
        # Disambiguate duplicate headers — Sheets allows them, our column
        # storage tolerates them, but the UI is friendlier when names differ.
        if col_name in seen_names:
            seen_names[col_name] += 1
            col_name = f"{col_name} ({seen_names[col_name]})"
        else:
            seen_names[col_name] = 1
        columns.append(
            {
                "id": f"col_{secrets.token_hex(6)}",
                "name": col_name,
                "type": "text",
            }
        )

    table = await table_service.create_table(
        workspace_id=workspace_id,
        name=name,
        description=f"Imported from Google Sheets ({file_id})",
        columns=columns,
        created_by=user_id,
    )

    data_rows: list[dict] = []
    for row in rows[1:]:
        record: dict = {}
        for i, col in enumerate(columns):
            value = row[i] if i < len(row) else ""
            record[col["id"]] = value
        data_rows.append(record)

    if data_rows:
        await table_service.create_rows_batch(
            table_id=table["id"],
            rows_data=data_rows,
            created_by=user_id,
        )

    return {
        "kind": "table",
        "table_id": str(table["id"]),
        "name": name,
        "row_count": len(data_rows),
        "column_count": len(columns),
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
