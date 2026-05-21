"""Element-level screenshot fallback for shapes we can't emit natively.

Used for:
    - Slide backgrounds with gradients / patterns / `background-image`.
    - `<canvas>` and `<svg>` content (charts, diagrams).
    - Anything the agent has tagged `data-export-raster`.

The probe pass identifies *which* selectors to capture; this module
does the actual screenshots. We share one browser context across all
slides to amortise the launch cost.
"""

from __future__ import annotations

import logging

from playwright.async_api import async_playwright

from ..constants import (
    EXPORT_DEVICE_SCALE_FACTOR,
    SLIDE_HEIGHT_PX,
    SLIDE_WIDTH_PX,
)
from ..pptx import _build_single_slide_html, _strip_body_state

logger = logging.getLogger(__name__)


async def rasterize_targets(
    html: str,
    targets: list[tuple[int, str]],
) -> dict[tuple[int, str], bytes]:
    """Given (slide_index, css_selector) tuples, return a map of those
    tuples to PNG bytes captured at 2x DPI."""
    if not targets:
        return {}

    html = _strip_body_state(html or "")
    # Bucket by slide index so we open each slide page once.
    by_slide: dict[int, list[str]] = {}
    for slide_idx, sel in targets:
        by_slide.setdefault(slide_idx, []).append(sel)

    results: dict[tuple[int, str], bytes] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = await browser.new_context(
                viewport={"width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
                device_scale_factor=EXPORT_DEVICE_SCALE_FACTOR,
            )
            try:
                for slide_idx, selectors in sorted(by_slide.items()):
                    page = await context.new_page()
                    try:
                        slide_html = _build_single_slide_html(html, slide_idx)
                        await page.set_content(slide_html, wait_until="networkidle")
                        for sel in selectors:
                            try:
                                handle = await page.query_selector(sel)
                                if handle is None:
                                    logger.warning(
                                        "raster target missing on slide %s: %s", slide_idx, sel
                                    )
                                    continue
                                png = await handle.screenshot(type="png", omit_background=False)
                                results[(slide_idx, sel)] = png
                            except Exception:
                                logger.exception(
                                    "raster screenshot failed for %s on slide %s",
                                    sel,
                                    slide_idx,
                                )
                    finally:
                        await page.close()
            finally:
                await context.close()
        finally:
            await browser.close()
    return results
