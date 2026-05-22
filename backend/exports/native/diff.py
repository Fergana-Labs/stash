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

# ruff: noqa: E402
import argparse
import asyncio
import base64
import logging
import os
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

from backend import database
from backend.exports.constants import SLIDE_HEIGHT_PX, SLIDE_WIDTH_PX
from backend.exports.html_canvas import (
    build_single_slide_html as _build_single_slide_html,
)
from backend.exports.html_canvas import (
    count_slides as _count_slides,
)
from backend.exports.html_canvas import (
    strip_body_state as _strip_body_state,
)
from backend.exports.native.aspose_builder import build_pptx_via_aspose
from backend.exports.native.layout_probe import probe
from backend.exports.native.pptx_builder import build_pptx

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
    html: str
    name: str
    slug: str
    if args.html_file:
        path = Path(args.html_file)
        html = path.read_text()
        name = path.stem
        slug = path.stem
    else:
        await database.init_db()
        pool = database.get_pool()
        row = await pool.fetchrow(
            "SELECT name, content_html FROM pages WHERE id = $1", UUID(args.page_id)
        )
        if not row:
            raise SystemExit("page not found")
        name = row["name"] or "slides"
        html = row["content_html"] or ""
        slug = args.page_id

    try:

        log.info("rendering original screenshots…")
        screenshot_pngs = await _render_slides(html)

        log.info("running native probe + builder…")
        specs = await probe(html)
        pptx_bytes = await build_pptx(specs, html)

        log.info("rasterising native pptx via libreoffice…")
        native_pngs = _pptx_to_pngs(pptx_bytes)

        aspose_pngs: list[bytes] = []
        if args.aspose:
            base_url = os.environ.get("ASPOSE_PPTX_URL")
            if not base_url:
                raise SystemExit("--aspose requires ASPOSE_PPTX_URL to be set")
            token = os.environ.get("ASPOSE_PPTX_TOKEN")
            log.info("running aspose builder against %s…", base_url)
            aspose_pptx = await build_pptx_via_aspose(
                specs,
                html,
                base_url=base_url,
                token=token,
            )
            log.info("rasterising aspose pptx via libreoffice…")
            aspose_pngs = _pptx_to_pngs(aspose_pptx)

        out = _render_diff_html(name, html, screenshot_pngs, native_pngs, aspose_pngs)
        out_path = Path(f"/tmp/diff-{slug}.html")
        out_path.write_text(out)
        log.info("wrote %s (open in your browser)", out_path)
    finally:
        if not args.html_file:
            await database.close_db()


def _render_diff_html(
    name: str,
    html: str,
    screenshots: list[bytes],
    natives: list[bytes],
    asposes: list[bytes],
) -> str:
    show_aspose = bool(asposes)
    rows = []
    n = max(len(screenshots), len(natives), len(asposes), 1)
    for i in range(n):
        shot = _b64(screenshots[i]) if i < len(screenshots) else ""
        native = _b64(natives[i]) if i < len(natives) else ""
        aspose = _b64(asposes[i]) if i < len(asposes) else ""
        cells = [
            f"<td><div style='width:540px;height:304px;overflow:hidden;border:1px solid #ccc;'><iframe srcdoc='{_iframe_doc(html, i)}' style='width:1920px;height:1080px;border:0;transform:scale(0.28125);transform-origin:top left;'></iframe></div></td>",
            f"<td>{f'<img src=\"{shot}\" style=\"width:540px;height:auto;\">' if shot else '(missing)'}</td>",
            f"<td>{f'<img src=\"{native}\" style=\"width:540px;height:auto;\">' if native else '(install libreoffice + poppler)'}</td>",
        ]
        if show_aspose:
            cells.append(
                f"<td>{f'<img src=\"{aspose}\" style=\"width:540px;height:auto;\">' if aspose else '(missing)'}</td>"
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")

    headers = ["HTML render", "Screenshot export", "Native export (PPTX→PDF→PNG)"]
    if show_aspose:
        headers.append("Aspose export (PPTX→PDF→PNG)")
    header_row = "".join(f"<th>{h}</th>" for h in headers)

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
<thead><tr>{header_row}</tr></thead>
<tbody>
{''.join(rows)}
</tbody></table>
</body></html>"""


def _iframe_doc(html: str, slide_idx: int) -> str:
    """Build a tiny standalone HTML snippet for the diff iframe that
    shows only the Nth slide at a scaled size."""
    from backend.exports.html_canvas import strip_body_state as strip

    body = strip(html)
    body = _build_single_slide_html(body, slide_idx)
    # Single-quote-safe for the srcdoc attribute.
    return body.replace("'", "&#39;")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Diff: HTML render vs screenshot export vs native export."
    )
    parser.add_argument(
        "page_id",
        nargs="?",
        help="UUID of a fixed-aspect HTML slide page (omit if using --html-file)",
    )
    parser.add_argument(
        "--html-file",
        help="diff against a local HTML file (bypasses DB; used for fixtures)",
    )
    parser.add_argument(
        "--aspose",
        action="store_true",
        help="also build via the remote aspose-pptx service "
        "(requires ASPOSE_PPTX_URL + optional ASPOSE_PPTX_TOKEN)",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
