"""Render a URL in headless Chromium and return the settled DOM.

The escalation tier between a plain HTTP fetch and giving up: SPAs and
consent-walled pages serve an empty shell over HTTP but render fine in
the worker's Chromium (already shipped in the image for PDF exports).
A render costs seconds of CPU where a fetch costs milliseconds, so this
runs only after plain-fetch extraction failed, and at most two renders
run at once per worker process.
"""

import asyncio

from playwright.async_api import async_playwright

RENDER_TIMEOUT_MS = 30_000
# Give client-side rendering a beat to settle after `load` — networkidle
# never fires on pages with long-polling/analytics, so it can't be the wait.
SETTLE_MS = 2_000

_semaphore = asyncio.Semaphore(2)


async def render_page(url: str) -> str:
    """Return the rendered DOM's HTML. Raises on navigation failure or
    timeout — the caller records the error on the import row."""
    async with _semaphore, async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="load", timeout=RENDER_TIMEOUT_MS)
            await page.wait_for_timeout(SETTLE_MS)
            return await page.content()
        finally:
            await browser.close()
