"""PPTX export — rasterized slides.

Uses Playwright to screenshot each `<section class="slide">` as a PNG,
then assembles a 16:9 deck with one slide per image (full-bleed). Text
is not editable in the resulting PPTX — this is intentional; extracting
Tiptap structure into PPTX shapes is a rabbit hole.

Reused by the Google Slides exporter (uploads the same PPTX to Drive
with `convertTo=true`).
"""

from __future__ import annotations

import io
import logging
import re
from uuid import UUID, uuid4

from playwright.async_api import async_playwright
from pptx import Presentation
from pptx.util import Emu

from ..celery_app import celery
from ..database import get_pool
from ..services import storage_service
from ..tasks._celery_helpers import run_async

logger = logging.getLogger(__name__)

SLIDE_WIDTH_PX = 1920
SLIDE_HEIGHT_PX = 1080
# python-pptx uses EMU (English Metric Units). 1 inch = 914400 EMU.
# 16:9 at 13.33 in x 7.5 in is the standard widescreen size.
PPTX_SLIDE_WIDTH = Emu(12192000)  # 13.333"
PPTX_SLIDE_HEIGHT = Emu(6858000)  # 7.5"

SECTION_RE = re.compile(
    r"<section\b[^>]*\bclass\s*=\s*[\"'][^\"']*\bslide\b[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)


def _count_slides(html: str) -> int:
    return max(1, len(SECTION_RE.findall(html or "")))


def _build_single_slide_html(source_html: str, slide_index: int) -> str:
    """Return HTML showing only the Nth <section class="slide">."""
    # Inject a bootstrap that hides every other section. Cheaper than
    # splitting the source HTML server-side.
    script = (
        "<script>(function(){var s=document.querySelectorAll('body > section.slide');"
        + f"var i={slide_index};"
        + "for(var k=0;k<s.length;k++){s[k].style.display=(k===i)?'':'none';}})();</script>"
    )
    if re.search(r"</body\s*>", source_html, flags=re.I):
        return re.sub(r"</body\s*>", script + "</body>", source_html, count=1, flags=re.I)
    return source_html + script


async def _screenshot_slides(html: str, count: int) -> list[bytes]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            shots: list[bytes] = []
            for i in range(count):
                page = await browser.new_page(
                    viewport={"width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
                )
                slide_html = _build_single_slide_html(html, i)
                await page.set_content(slide_html, wait_until="networkidle")
                png = await page.screenshot(
                    type="png",
                    full_page=False,
                    clip={"x": 0, "y": 0, "width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
                )
                shots.append(png)
                await page.close()
            return shots
        finally:
            await browser.close()


def _build_pptx(shots: list[bytes]) -> bytes:
    prs = Presentation()
    prs.slide_width = PPTX_SLIDE_WIDTH
    prs.slide_height = PPTX_SLIDE_HEIGHT
    blank = prs.slide_layouts[6]  # blank layout
    for png in shots:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(
            io.BytesIO(png),
            left=0,
            top=0,
            width=PPTX_SLIDE_WIDTH,
            height=PPTX_SLIDE_HEIGHT,
        )
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


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

    source_html = page_row["content_html"] or ""
    count = _count_slides(source_html)
    shots = await _screenshot_slides(source_html, count)
    pptx_bytes = _build_pptx(shots)
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
        content_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
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
