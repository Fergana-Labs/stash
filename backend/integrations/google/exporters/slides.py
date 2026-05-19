"""Google Slides exporter.

Builds the same PPTX as the local PPTX exporter, then uploads it to
the user's Drive with `mimeType=application/vnd.google-apps.presentation`
— Drive's PPTX→Slides converter handles rasterized images cleanly,
which is dramatically simpler than constructing native Slides shapes
via the Slides API.

Requires the `drive.file` scope (limits Drive access to files we
create — narrower than `drive`).
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ....celery_app import celery
from ....exports.pptx import build_pptx_bytes_for_page
from ....tasks._celery_helpers import run_async
from ...storage import get_valid_token

logger = logging.getLogger(__name__)

DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true"
DRIVE_FILE_URL = "https://www.googleapis.com/drive/v3/files/{file_id}?fields=id,webViewLink"


async def _export(user_id: UUID, page_id: UUID) -> dict:
    access_token = await get_valid_token(user_id, "google")
    stem, pptx_bytes = await build_pptx_bytes_for_page(page_id)

    metadata = {
        "name": stem,
        "mimeType": "application/vnd.google-apps.presentation",
    }

    boundary = "stash-slides-upload-boundary"
    multipart = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{_json_dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        "Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation\r\n\r\n"
    ).encode("utf-8") + pptx_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": f"multipart/related; boundary={boundary}",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(DRIVE_UPLOAD_URL, headers=headers, content=multipart)
        resp.raise_for_status()
        file_id = resp.json()["id"]

        meta_resp = await client.get(
            DRIVE_FILE_URL.format(file_id=file_id),
            headers={"Authorization": f"Bearer {access_token}"},
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()

    return {
        "format": "gslides",
        "drive_file_id": file_id,
        "drive_web_link": meta.get("webViewLink"),
    }


def _json_dumps(obj: dict) -> str:
    import json

    return json.dumps(obj)


@celery.task(name="backend.exports.gslides.export_to_google_slides")
def export_to_google_slides(user_id: str, page_id: str) -> dict:
    return run_async(_export(UUID(user_id), UUID(page_id)))


# Register self with the exporter registry. backend/exports/__init__.py
# imports this module to trigger registration.
from ...registry import register_exporter as _register  # noqa: E402

try:
    _register("gslides", "backend.exports.gslides.export_to_google_slides")
except RuntimeError:
    # Already registered (re-import during dev autoreload) — fine.
    pass
