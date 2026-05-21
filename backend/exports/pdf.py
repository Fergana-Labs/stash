"""PDF export of a fixed-aspect slide page.

Reads the source page directly from the DB — no internal render route
needed since the worker has DB access. Builds a single HTML document
with one CSS page per `<section class="slide">` element, then calls
Playwright's `page.pdf()` once to produce the whole deck.

If the page has zero `<section class="slide">` elements, exports a
single page rendering of the whole HTML body (matches the renderer's
spec: zero sections = one slide).
"""

from __future__ import annotations

import logging
import re
from uuid import UUID, uuid4

from playwright.async_api import async_playwright

from ..celery_app import celery
from ..database import get_pool
from ..services import storage_service
from ..tasks._celery_helpers import run_async
from .constants import SLIDE_HEIGHT_PX, SLIDE_WIDTH_PX

logger = logging.getLogger(__name__)


def _safe_stem(name: str) -> str:
    """S3-safe filename stem. SigV4 signing breaks on spaces and parens
    in object keys when the URL gets percent-encoded, so we collapse any
    non-word character to an underscore."""
    stem = re.sub(r"[^\w.-]+", "_", name).strip("_")
    return stem or "slides"


# `@page size` accepts px; Chromium converts at 96dpi.
# Text in the resulting PDF is vector (selectable, searchable).
PAGED_CSS = """
  @page {{ size: {w}px {h}px; margin: 0; }}
  html, body {{ margin: 0; padding: 0; overflow: hidden; }}
  body > section.slide {{
    width: {w}px;
    height: {h}px;
    overflow: hidden;
    page-break-after: always;
    box-sizing: border-box;
    display: block !important;
  }}
  body > section.slide:last-of-type {{ page-break-after: auto; }}
"""


def _inject_paged_css(html: str) -> str:
    css = "<style>" + PAGED_CSS.format(w=SLIDE_WIDTH_PX, h=SLIDE_HEIGHT_PX) + "</style>"
    if re.search(r"</head\s*>", html, flags=re.I):
        return re.sub(r"</head\s*>", css + "</head>", html, count=1, flags=re.I)
    return css + html


async def _render_pdf(html: str) -> bytes:
    async with async_playwright() as p:
        # See pptx.py for why these args matter in the Render worker.
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = await browser.new_page(
                viewport={"width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
            )
            await page.set_content(html, wait_until="networkidle")
            # `prefer_css_page_size=True` honours the injected @page block;
            # this keeps slide dims locked to the shared constants instead
            # of relying on the width/height args (which Chromium otherwise
            # uses as a fallback).
            pdf = await page.pdf(
                width=f"{SLIDE_WIDTH_PX}px",
                height=f"{SLIDE_HEIGHT_PX}px",
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            await browser.close()
    return pdf


async def _export(user_id: UUID, page_id: UUID) -> dict:
    pool = get_pool()
    page_row = await pool.fetchrow(
        """
        SELECT id, workspace_id, name, content_html, content_type, html_layout
        FROM pages WHERE id = $1
        """,
        page_id,
    )
    if not page_row:
        raise RuntimeError("page not found")
    if page_row["content_type"] != "html" or page_row["html_layout"] != "fixed-aspect":
        raise RuntimeError("export requires a fixed-aspect HTML page")

    source_html = page_row["content_html"] or ""
    html = _inject_paged_css(source_html)
    pdf_bytes = await _render_pdf(html)

    filename = f"{_safe_stem(page_row['name'] or 'slides')}-{uuid4().hex[:8]}.pdf"
    storage_key = await storage_service.upload_file(
        workspace_id=page_row["workspace_id"],
        filename=filename,
        content=pdf_bytes,
        content_type="application/pdf",
    )
    download_url = await storage_service.get_file_url(storage_key, expires_in=3600)
    return {
        "format": "pdf",
        "storage_key": storage_key,
        "download_url": download_url,
        "size_bytes": len(pdf_bytes),
    }


@celery.task(name="backend.exports.pdf.export_pdf")
def export_pdf(user_id: str, page_id: str) -> dict:
    return run_async(_export(UUID(user_id), UUID(page_id)))
