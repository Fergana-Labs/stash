"""Resolve image URLs to bytes for native PPTX picture shapes.

Supports two flavours we see in agent-authored decks:
    - `data:image/...;base64,…` URIs (inline)
    - `/api/v1/workspaces/{wid}/files/{fid}/download` (local Stash files)

The fetcher is per-run: instantiate once at the top of pptx_builder.build
so a deck that uses the same image on multiple slides only downloads it
once.
"""

from __future__ import annotations

import base64
import logging
import re
from uuid import UUID

from ...database import get_pool
from ...services import permission_service, storage_service

logger = logging.getLogger(__name__)

# Pre-compile regexes used in hot loops.
_DATA_URI_RE = re.compile(r"^data:[^;,]+;base64,(?P<b64>.+)$", re.DOTALL)
_DATA_URI_PLAIN_RE = re.compile(r"^data:[^;,]+,(?P<raw>.+)$", re.DOTALL)
_STASH_FILE_RE = re.compile(
    r"^(?:https?://[^/]+)?/api/v1/workspaces/(?P<wid>[0-9a-f-]+)/files/(?P<fid>[0-9a-f-]+)/download",
    re.IGNORECASE,
)

_MAX_BYTES = 25 * 1024 * 1024  # 25 MB hard cap per image


class ImageFetchError(Exception):
    pass


class ImageFetcher:
    """Per-run cache so the same URL is fetched at most once per export."""

    def __init__(self, workspace_id: UUID | None = None, user_id: UUID | None = None) -> None:
        self.workspace_id = workspace_id
        self.user_id = user_id
        self._cache: dict[str, bytes | None] = {}

    async def fetch(self, src: str | None) -> bytes | None:
        if not src:
            return None
        if src in self._cache:
            return self._cache[src]
        try:
            data = await self._fetch_uncached(src)
        except Exception as e:
            logger.warning("image fetch failed for %s: %s", src[:120], e)
            data = None
        self._cache[src] = data
        return data

    async def _fetch_uncached(self, src: str) -> bytes | None:
        if src.startswith("data:"):
            return _decode_data_uri(src)

        stash = _STASH_FILE_RE.match(src)
        if stash:
            return await _download_skill_file(
                UUID(stash.group("wid")),
                UUID(stash.group("fid")),
                self.workspace_id,
                self.user_id,
            )

        if src.startswith("http://") or src.startswith("https://"):
            logger.info("skipping remote image src during export: %s", src[:120])
            return None

        logger.info("skipping unrecognised image src: %s", src[:120])
        return None


def _decode_data_uri(uri: str) -> bytes | None:
    m = _DATA_URI_RE.match(uri)
    if m:
        raw = base64.b64decode(m.group("b64"))
        if len(raw) > _MAX_BYTES:
            raise ImageFetchError(f"image exceeds {_MAX_BYTES} byte cap")
        # python-pptx / PIL can't decode SVG — rasterize it via Pillow
        # if we recognise the prefix. Fall through to None otherwise so
        # the builder can skip rather than crash.
        if raw[:5] == b"<?xml" or raw[:4] == b"<svg":
            return _svg_to_png(raw)
        return raw
    m2 = _DATA_URI_PLAIN_RE.match(uri)
    if m2:
        from urllib.parse import unquote_to_bytes

        raw = unquote_to_bytes(m2.group("raw"))
        if len(raw) > _MAX_BYTES:
            raise ImageFetchError(f"image exceeds {_MAX_BYTES} byte cap")
        if raw[:5] == b"<?xml" or raw[:4] == b"<svg":
            return _svg_to_png(raw)
        return raw
    return None


def _svg_to_png(svg: bytes) -> bytes | None:
    """Render an SVG byte-string to PNG via Pillow's CairoSVG support if
    available, otherwise None. Skipping is better than crashing."""
    try:
        import cairosvg  # type: ignore[import-untyped]

        return cairosvg.svg2png(bytestring=svg)
    except Exception:
        logger.warning("cairosvg not available; SVG image will be skipped")
        return None


async def _download_skill_file(
    url_workspace_id: UUID,
    file_id: UUID,
    export_workspace_id: UUID | None,
    user_id: UUID | None,
) -> bytes | None:
    if export_workspace_id is None or user_id is None or url_workspace_id != export_workspace_id:
        return None


    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT workspace_id, storage_key FROM files WHERE id = $1",
        file_id,
    )
    if not row or not row["storage_key"]:
        return None
    if row["workspace_id"] != export_workspace_id:
        return None
    can_read = await permission_service.check_access(
        "file",
        file_id,
        user_id,
        workspace_id=export_workspace_id,
    )
    if not can_read:
        return None
    return await storage_service.download_file(row["storage_key"])
