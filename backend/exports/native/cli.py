"""Sandbox CLI for the native-shape exporter.

Usage:
    python -m backend.exports.native.cli <page_id> [--out file.pptx]
    python -m backend.exports.native.cli <page_id> --spec      # dump SlideSpec JSON to stdout

The page_id is whatever's in the `pages` table. Requires DATABASE_URL
(reads `.env` automatically via the dotenv loader).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env")

sys.path.insert(0, str(REPO_ROOT))

from backend import database  # noqa: E402
from backend.exports.native.aspose_builder import build_pptx_via_aspose  # noqa: E402
from backend.exports.native.layout_probe import probe  # noqa: E402
from backend.exports.native.pptx_builder import build_pptx  # noqa: E402

log = logging.getLogger("native-export")


async def _load_page(page_id: UUID) -> tuple[str, str]:
    pool = database.get_pool()
    row = await pool.fetchrow(
        "SELECT name, content_html, content_type, html_layout " "FROM pages WHERE id = $1",
        page_id,
    )
    if not row:
        raise SystemExit(f"page {page_id} not found")
    if row["content_type"] != "html" or row["html_layout"] != "fixed-aspect":
        raise SystemExit(
            f"page {page_id} is not a fixed-aspect HTML deck "
            f"(content_type={row['content_type']!r}, html_layout={row['html_layout']!r})"
        )
    return row["name"] or "slides", row["content_html"] or ""


async def main_async(args: argparse.Namespace) -> None:
    used_db = False
    if args.html_file:
        path = Path(args.html_file)
        html = path.read_text()
        name = path.stem
        log.info("loaded %s — %d bytes (from file)", path, len(html))
    else:
        if not args.page_id:
            raise SystemExit("page_id or --html-file is required")
        await database.init_db()
        used_db = True
        name, html = await _load_page(UUID(args.page_id))
        log.info("loaded %s — %d bytes (from db)", name, len(html))
    try:

        specs = await probe(html)
        log.info("probed %d slide(s)", len(specs))

        if args.spec:
            json.dump([asdict(s) for s in specs], sys.stdout, indent=2)
            sys.stdout.write("\n")
            return

        if args.builder == "aspose":
            base_url = os.environ.get("ASPOSE_PPTX_URL")
            if not base_url:
                raise SystemExit("ASPOSE_PPTX_URL must be set when --builder=aspose")
            token = os.environ.get("ASPOSE_PPTX_TOKEN")
            pptx_bytes = await build_pptx_via_aspose(
                specs,
                html,
                base_url=base_url,
                token=token,
            )
            suffix = "aspose"
        else:
            pptx_bytes = await build_pptx(specs, html)
            suffix = "native"

        out_path = (
            Path(args.out) if args.out else Path(f"/tmp/{name.replace(' ', '_')}-{suffix}.pptx")
        )
        out_path.write_bytes(pptx_bytes)
        log.info("wrote %s (%d bytes)", out_path, len(pptx_bytes))
    finally:
        if used_db:
            await database.close_db()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Native-shape PPTX export sandbox driver.")
    parser.add_argument(
        "page_id",
        nargs="?",
        help="UUID of a fixed-aspect HTML slide page (omit if using --html-file)",
    )
    parser.add_argument(
        "--html-file",
        help="run against a local HTML file (bypasses DB)",
    )
    parser.add_argument("--out", help="output .pptx path (default: /tmp/<name>-native.pptx)")
    parser.add_argument(
        "--spec", action="store_true", help="dump SlideSpec JSON to stdout instead of writing PPTX"
    )
    parser.add_argument(
        "--builder",
        choices=["python-pptx", "aspose"],
        default="python-pptx",
        help="which builder to use; aspose hits the remote REST service "
        "and requires ASPOSE_PPTX_URL (+ optional ASPOSE_PPTX_TOKEN)",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
