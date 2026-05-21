"""PPTX export — rasterized slides.

Uses Playwright to screenshot each `<section class="slide">` as a PNG
at 2x device scale, then assembles a 16:9 deck with one image per
slide.

Reused by the Google Slides exporter (uploads the same PPTX to Drive
with `convertTo=true`).

Why no text overlay: an earlier version of this exporter included
invisible-text overlays (`<a:alpha val="0"/>` on a white run color) so
the exported PPTX would be selectable / searchable in PowerPoint and
Keynote. The OOXML is valid but PowerPoint's text-run renderer
ignores the alpha child of `<a:srgbClr>`, so the "invisible" text
showed up as visible white text on top of the slide image — doubling
every label. Loss of selectability is the lesser evil.
"""

from __future__ import annotations

import io
import logging
import re
from uuid import UUID, uuid4

from playwright.async_api import async_playwright
from pptx import Presentation

from ..celery_app import celery
from ..database import get_pool
from ..services import storage_service
from ..tasks._celery_helpers import run_async
from .constants import (
    EXPORT_DEVICE_SCALE_FACTOR,
    SLIDE_HEIGHT_EMU,
    SLIDE_HEIGHT_PX,
    SLIDE_WIDTH_EMU,
    SLIDE_WIDTH_PX,
)

logger = logging.getLogger(__name__)

SECTION_RE = re.compile(
    r"<section\b[^>]*\bclass\s*=\s*[\"'][^\"']*\bslide\b[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)

# Mirrors the canvas-enforcing CSS the in-app slide viewer injects (see
# injectSlideDeckBootstrap in HtmlPageView.tsx). Without it, an agent that
# omits explicit dimensions ends up with a section sized to its content
# height — and the screenshot captures the white viewport below.
_CANVAS_CSS = f"""
  html, body {{ margin: 0; padding: 0; }}
  body > section.slide {{
    width: {SLIDE_WIDTH_PX}px;
    height: {SLIDE_HEIGHT_PX}px;
    overflow: hidden;
    position: relative;
    box-sizing: border-box;
    display: block;
  }}
"""


def _count_slides(html: str) -> int:
    return max(1, len(SECTION_RE.findall(html or "")))


def _strip_body_state(html: str) -> str:
    """Remove inline body attributes the viewer bootstrap leaves behind:
    `style="zoom: …"` from applyCanvasZoom, and `contenteditable` /
    `spellcheck` from the WYSIWYG. Legacy pages saved before this strip
    was added still have these baked in — without removing them, the
    export viewport renders the body shrunk to ~835px on a 1920px
    canvas, leaving the rest as body bg."""
    return re.sub(
        r"<body([^>]*)>",
        lambda m: "<body" + _clean_body_attrs(m.group(1)) + ">",
        html,
        count=1,
        flags=re.I,
    )


def _clean_body_attrs(attrs: str) -> str:
    # Drop contenteditable + spellcheck attributes entirely.
    attrs = re.sub(r"\s*contenteditable\s*=\s*\"[^\"]*\"", "", attrs, flags=re.I)
    attrs = re.sub(r"\s*spellcheck\s*=\s*\"[^\"]*\"", "", attrs, flags=re.I)

    # Drop `zoom: …;` from inline style. If style becomes empty, drop the attr.
    def _strip_zoom(m: re.Match) -> str:
        css = re.sub(r"\s*zoom\s*:\s*[^;\"]*;?", "", m.group(1), flags=re.I).strip()
        return "" if not css else f' style="{css}"'

    attrs = re.sub(r"\s*style\s*=\s*\"([^\"]*)\"", _strip_zoom, attrs, count=1, flags=re.I)
    return attrs


def _build_single_slide_html(source_html: str, slide_index: int) -> str:
    """Return HTML showing only the Nth <section class="slide"> with the
    canvas-enforcing CSS injected so the section fills the slide canvas
    even when the agent's HTML omitted explicit dimensions."""
    css = f"<style>{_CANVAS_CSS}</style>"
    script = (
        "<script>(function(){var s=document.querySelectorAll('body > section.slide');"
        + f"var i={slide_index};"
        + "for(var k=0;k<s.length;k++){s[k].style.display=(k===i)?'':'none';}})();</script>"
    )
    html = _strip_body_state(source_html)
    if re.search(r"</head\s*>", html, flags=re.I):
        html = re.sub(r"</head\s*>", css + "</head>", html, count=1, flags=re.I)
    else:
        html = css + html
    if re.search(r"</body\s*>", html, flags=re.I):
        return re.sub(r"</body\s*>", script + "</body>", html, count=1, flags=re.I)
    return html + script


async def _capture_slide(page, slide_index: int, html: str) -> bytes:
    """Render one slide, return the PNG bytes."""
    slide_html = _build_single_slide_html(html, slide_index)
    await page.set_content(slide_html, wait_until="networkidle")
    return await page.screenshot(
        type="png",
        full_page=False,
        clip={"x": 0, "y": 0, "width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
    )


async def _capture_all_slides(html: str, count: int) -> list[bytes]:
    async with async_playwright() as p:
        # `--no-sandbox` is required because the worker container runs as a
        # non-root user without the capabilities Chromium's sandbox needs.
        # `--disable-dev-shm-usage` makes Chromium fall back to /tmp instead
        # of /dev/shm — Render containers ship with a 64 MB /dev/shm which
        # is too small for 2x-DPI screenshots and Chromium will crash hard
        # enough that Render's supervisor restarts the whole worker.
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            results: list[bytes] = []
            context = await browser.new_context(
                viewport={"width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
                device_scale_factor=EXPORT_DEVICE_SCALE_FACTOR,
            )
            try:
                for i in range(count):
                    page = await context.new_page()
                    try:
                        results.append(await _capture_slide(page, i, html))
                    finally:
                        await page.close()
            finally:
                await context.close()
            return results
        finally:
            await browser.close()


def _build_pptx(shots: list[bytes]) -> bytes:
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH_EMU
    prs.slide_height = SLIDE_HEIGHT_EMU
    blank = prs.slide_layouts[6]  # blank layout
    for png in shots:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(
            io.BytesIO(png),
            left=0,
            top=0,
            width=SLIDE_WIDTH_EMU,
            height=SLIDE_HEIGHT_EMU,
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
    shots = await _capture_all_slides(source_html, count)
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
