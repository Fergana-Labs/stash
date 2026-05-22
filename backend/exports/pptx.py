"""PPTX export — native shapes via the remote aspose-pptx service.

Pipeline:
    page HTML → layout_probe → ShapeSpec[] → aspose_builder REST → PPTX

Replaces the old Playwright-screenshot exporter. Native shapes mean:
- Text is selectable / searchable / restyleable in PowerPoint.
- Tables are real PPTX tables.
- Charts (from Chart.js) emit as editable native charts.
- Gradients and SVGs stay vector.
- File sizes drop ~10-25x vs the screenshot path (no PNGs embedded).

Service runs on Render (`powerpoint-mcp/`). Backend talks to it over
plain REST; see `backend/exports/native/aspose_builder.py`.

Reused by the Google Slides exporter (uploads the same PPTX to Drive
with `convertTo=true`).

The sandbox / eval / comparison code under `backend/exports/native/`
(cli.py, diff.py, pptx_builder.py, fixtures/) is intentionally kept
out of the production hot path but available for fidelity iteration.
"""

from __future__ import annotations

import logging
import os
import re
from uuid import UUID, uuid4

from ..celery_app import celery
from ..database import get_pool
from ..services import storage_service
from ..tasks._celery_helpers import run_async
from .native.aspose_builder import build_pptx_via_aspose
from .native.layout_probe import probe

logger = logging.getLogger(__name__)


async def build_pptx_bytes_for_page(page_id: UUID) -> tuple[str, bytes]:
    """Render a page's slides to a PPTX. Returns (filename_stem, bytes).

    Exposed so the Google Slides exporter can call this without
    re-implementing the rendering pipeline.
    """
    pool = get_pool()
    page_row = await pool.fetchrow(
        "SELECT id, workspace_id, name, content_html, content_type, html_layout "
        "FROM pages WHERE id = $1",
        page_id,
    )
    if not page_row:
        raise RuntimeError("page not found")
    if page_row["content_type"] != "html" or page_row["html_layout"] != "fixed-aspect":
        raise RuntimeError("export requires a fixed-aspect HTML page")

    base_url = os.environ.get("ASPOSE_PPTX_URL")
    if not base_url:
        raise RuntimeError("ASPOSE_PPTX_URL is not configured")
    token = os.environ.get("ASPOSE_PPTX_TOKEN")

    source_html = page_row["content_html"] or ""
    specs = await probe(source_html)
    logger.info("probed %d slide(s) for page %s", len(specs), page_id)

    pptx_bytes = await build_pptx_via_aspose(
        specs,
        source_html,
        base_url=base_url,
        token=token,
    )
    return page_row["name"] or "slides", pptx_bytes


async def _export(user_id: UUID, page_id: UUID) -> dict:
    pool = get_pool()
    workspace_id = await pool.fetchval("SELECT workspace_id FROM pages WHERE id = $1", page_id)
    stem, pptx_bytes = await build_pptx_bytes_for_page(page_id)
    # SigV4 signing breaks on spaces / parens / other punctuation in S3 keys
    # once the URL gets percent-encoded. Collapse to an alnum-safe stem.
    safe_stem = re.sub(r"[^\w.-]+", "_", stem).strip("_") or "slides"
    filename = f"{safe_stem}-{uuid4().hex[:8]}.pptx"
    storage_key = await storage_service.upload_file(
        workspace_id=workspace_id,
        filename=filename,
        content=pptx_bytes,
        content_type=("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    )
    download_url = await storage_service.get_file_url(storage_key, expires_in=3600)
    return {
        "format": "pptx",
        "storage_key": storage_key,
        "download_url": download_url,
        "size_bytes": len(pptx_bytes),
    }


@celery.task(name="backend.exports.pptx.export_pptx")
def export_pptx(user_id: str, page_id: str) -> dict:
    return run_async(_export(UUID(user_id), UUID(page_id)))
