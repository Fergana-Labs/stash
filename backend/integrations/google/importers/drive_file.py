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

import logging
from uuid import UUID

import asyncpg
import httpx

from ....celery_app import celery
from ....database import get_pool
from ....tasks._celery_helpers import run_async
from ...storage import get_valid_token

logger = logging.getLogger(__name__)

DRIVE_FILE_URL = "https://www.googleapis.com/drive/v3/files/{file_id}?fields=id,name,mimeType,parents"
DRIVE_EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/export"

MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


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
    markdown = resp.text
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
            return await _import_google_doc(
                client, workspace_id, folder_id, user_id, file_id, name
            )

        if mime == MIME_GOOGLE_SHEET:
            raise RuntimeError(
                "Sheets import is not yet implemented in this build"
            )

        if mime == MIME_PPTX:
            raise RuntimeError(
                "PPTX import is not yet implemented in this build"
            )

        raise RuntimeError(f"Unsupported Drive MIME type: {mime}")


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
