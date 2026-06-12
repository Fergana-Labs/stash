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
from ..html_canvas import build_single_slide_html, strip_body_state
from ..playwright_network import abort_network_request

logger = logging.getLogger(__name__)


async def rasterize_targets(
    html: str,
    targets: list[tuple[int, str]],
) -> dict[tuple[int, str], bytes]:
    """Given (slide_index, css_selector) tuples, return a map of those
    tuples to PNG bytes captured at 2x DPI."""
    if not targets:
        return {}

    html = strip_body_state(html or "")
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
                await context.route("**/*", abort_network_request)
                for slide_idx, selectors in sorted(by_slide.items()):
                    page = await context.new_page()
                    try:
                        slide_html = build_single_slide_html(html, slide_idx)
                        await page.set_content(slide_html, wait_until="networkidle")
                        for sel in selectors:
                            try:
                                handle = await page.query_selector(sel)
                                if handle is None:
                                    logger.warning(
                                        "raster target missing on slide %s: %s", slide_idx, sel
                                    )
                                    continue
                                # Bail early if the element isn't visible —
                                # the screenshot call would otherwise spin
                                # for the default 30 s timeout retrying
                                # scrollIntoView on a hidden box.
                                if not await handle.is_visible():
                                    logger.warning(
                                        "raster target not visible on slide %s: %s",
                                        slide_idx,
                                        sel,
                                    )
                                    continue
                                # When capturing a slide-section background
                                # we don't want the section's children in
                                # the shot — we only need gradient / pattern.
                                # Native text shapes get composited on top
                                # by the builder. Without this strip the
                                # raster contains the text TOO, leading to
                                # visible duplicates in PowerPoint.
                                is_section_bg = sel.startswith("body > section.slide")
                                if is_section_bg:
                                    await page.evaluate(
                                        """(sel) => {
                                            const el = document.querySelector(sel);
                                            if (!el) return;
                                            el.dataset.__nativeBgHidden = '1';
                                            for (const c of Array.from(el.children)) {
                                                c.dataset.__nativeBgPrevVis = c.style.visibility || '';
                                                c.style.visibility = 'hidden';
                                            }
                                        }""",
                                        sel,
                                    )
                                try:
                                    # For non-background captures use a
                                    # viewport-clipped screenshot rather than
                                    # element-screenshot — Chart.js-style
                                    # responsive elements can grow past the
                                    # slide (canvas height 2186 in a 1080
                                    # slide), so we want just the visible
                                    # area, not the whole element.
                                    if is_section_bg:
                                        png = await handle.screenshot(
                                            type="png", omit_background=False, timeout=5000
                                        )
                                    else:
                                        box = await handle.bounding_box()
                                        if not box:
                                            continue
                                        clip = {
                                            "x": max(0.0, float(box["x"])),
                                            "y": max(0.0, float(box["y"])),
                                            "width": min(
                                                float(SLIDE_WIDTH_PX) - max(0.0, float(box["x"])),
                                                float(box["width"]),
                                            ),
                                            "height": min(
                                                float(SLIDE_HEIGHT_PX) - max(0.0, float(box["y"])),
                                                float(box["height"]),
                                            ),
                                        }
                                        if clip["width"] < 4 or clip["height"] < 4:
                                            continue
                                        png = await page.screenshot(
                                            type="png", clip=clip, timeout=5000
                                        )
                                    results[(slide_idx, sel)] = png
                                finally:
                                    if is_section_bg:
                                        await page.evaluate(
                                            """(sel) => {
                                                const el = document.querySelector(sel);
                                                if (!el || !el.dataset.__nativeBgHidden) return;
                                                for (const c of Array.from(el.children)) {
                                                    c.style.visibility = c.dataset.__nativeBgPrevVis || '';
                                                    delete c.dataset.__nativeBgPrevVis;
                                                }
                                                delete el.dataset.__nativeBgHidden;
                                            }""",
                                            sel,
                                        )
                            except Exception as exc:
                                logger.warning(
                                    "raster screenshot failed slide=%s exception_type=%s",
                                    slide_idx,
                                    type(exc).__name__,
                                )
                    finally:
                        await page.close()
            finally:
                await context.close()
        finally:
            await browser.close()
    return results
