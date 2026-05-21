"""Side-by-side diff report: original HTML render vs screenshot exporter
vs native exporter.

Writes an HTML page with one row per slide and three columns:
    1. The page's HTML rendered live in an iframe at 1920x1080 (the
       in-app viewer's reference render).
    2. The legacy screenshot exporter's PNG for that slide.
    3. The native exporter's PNG for that slide (rendered from the
       generated PPTX via LibreOffice headless).

LibreOffice is already installed in the worker container; locally we
fall back gracefully if it's missing.

Usage:
    python -m backend.exports.native.diff <page_id>
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env")

sys.path.insert(0, str(REPO_ROOT))

from backend import database  # noqa: E402
from backend.exports.constants import SLIDE_HEIGHT_PX, SLIDE_WIDTH_PX  # noqa: E402
from backend.exports.native.layout_probe import probe  # noqa: E402
from backend.exports.native.pptx_builder import build_pptx  # noqa: E402
from backend.exports.pptx import (  # noqa: E402
    _build_single_slide_html,
    _count_slides,
    _strip_body_state,
)

log = logging.getLogger("native-diff")


async def _render_slides(html: str) -> list[bytes]:
    """Screenshot each slide via the same path the legacy exporter uses."""
    html = _strip_body_state(html or "")
    count = _count_slides(html)
    shots: list[bytes] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            ctx = await browser.new_context(
                viewport={"width": SLIDE_WIDTH_PX, "height": SLIDE_HEIGHT_PX},
                device_scale_factor=1,
            )
            try:
                for i in range(count):
                    page = await ctx.new_page()
                    try:
                        await page.set_content(
                            _build_single_slide_html(html, i), wait_until="networkidle"
                        )
                        shots.append(await page.screenshot(type="png", full_page=False))
                    finally:
                        await page.close()
            finally:
                await ctx.close()
        finally:
            await browser.close()
    return shots


def _pptx_to_pngs(pptx_bytes: bytes) -> list[bytes]:
    """Render a PPTX to one PNG per slide via LibreOffice + pdftoppm.
    Returns [] if either binary is missing — the diff still works, just
    without the native column."""
    if not _has("soffice") or not _has("pdftoppm"):
        log.warning("soffice / pdftoppm not on PATH — native column will be blank")
        return []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)
        try:
            subprocess.run(
                [
                    "soffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(pptx_path),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as e:
            log.warning("soffice failed: %s", e.stderr[:400] if e.stderr else e)
            return []
        pdf_path = tmp_path / "deck.pdf"
        if not pdf_path.exists():
            return []
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", "96", str(pdf_path), str(tmp_path / "page")],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as e:
            log.warning("pdftoppm failed: %s", e.stderr[:400] if e.stderr else e)
            return []
        pngs = sorted(tmp_path.glob("page-*.png"))
        return [p.read_bytes() for p in pngs]


def _has(binary: str) -> bool:
    return subprocess.run(["which", binary], capture_output=True).returncode == 0


def _b64(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


async def main_async(args: argparse.Namespace) -> None:
    await database.init_db()
    try:
        pool = database.get_pool()
        row = await pool.fetchrow(
            "SELECT name, content_html FROM pages WHERE id = $1", UUID(args.page_id)
        )
        if not row:
            raise SystemExit("page not found")
        name = row["name"] or "slides"
        html = row["content_html"] or ""

        log.info("rendering original screenshots…")
        screenshot_pngs = await _render_slides(html)

        log.info("running native probe + builder…")
        specs = await probe(html)
        pptx_bytes = await build_pptx(specs, html)

        log.info("rasterising native pptx via libreoffice…")
        native_pngs = _pptx_to_pngs(pptx_bytes)

        out = _render_diff_html(name, html, screenshot_pngs, native_pngs)
        out_path = Path(f"/tmp/diff-{args.page_id}.html")
        out_path.write_text(out)
        log.info("wrote %s (open in your browser)", out_path)
    finally:
        await database.close_db()


def _render_diff_html(name: str, html: str, screenshots: list[bytes], natives: list[bytes]) -> str:
    rows = []
    n = max(len(screenshots), len(natives), 1)
    for i in range(n):
        shot = _b64(screenshots[i]) if i < len(screenshots) else ""
        native = _b64(natives[i]) if i < len(natives) else ""
        rows.append(f"""
            <tr>
              <td><iframe srcdoc='{_iframe_doc(html, i)}' style='width:540px;height:304px;border:1px solid #ccc;'></iframe></td>
              <td>{f'<img src=\"{shot}\" style=\"width:540px;height:auto;\">' if shot else '(missing)'}</td>
              <td>{f'<img src=\"{native}\" style=\"width:540px;height:auto;\">' if native else '(install libreoffice + poppler)'}</td>
            </tr>
            """)
    return f"""<!doctype html>
<html><head><meta charset=utf-8><title>diff — {name}</title>
<style>
  body {{ font-family: system-ui, sans-serif; padding: 24px; background: #f8fafc; }}
  h1 {{ font-size: 18px; margin: 0 0 16px; }}
  table {{ border-collapse: collapse; }}
  th {{ text-align: left; padding: 8px 12px; background: #e2e8f0; }}
  td {{ padding: 8px 12px; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #fff; }}
</style>
</head><body>
<h1>{name} — diff</h1>
<table>
<thead><tr><th>HTML render</th><th>Screenshot export</th><th>Native export (PPTX→PDF→PNG)</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody></table>
</body></html>"""


def _iframe_doc(html: str, slide_idx: int) -> str:
    """Build a tiny standalone HTML snippet for the diff iframe that
    shows only the Nth slide at a scaled size."""
    from backend.exports.pptx import _strip_body_state as strip

    body = strip(html)
    body = _build_single_slide_html(body, slide_idx)
    # Single-quote-safe for the srcdoc attribute.
    return body.replace("'", "&#39;")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Diff: HTML render vs screenshot export vs native export."
    )
    parser.add_argument("page_id", help="UUID of a fixed-aspect HTML slide page")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
