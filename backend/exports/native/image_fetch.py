"""Resolve image URLs to bytes for native PPTX picture shapes.

Supports three flavours we see in agent-authored decks:
    - `data:image/...;base64,…` URIs (inline)
    - `/api/v1/workspaces/{wid}/files/{fid}/download` (local Stash files)
    - Arbitrary http(s) URLs (CDN, R2, etc.)

The fetcher is per-run: instantiate once at the top of pptx_builder.build
so a deck that uses the same image on multiple slides only downloads it
once.
"""

from __future__ import annotations

import base64
import logging
import re
from uuid import UUID

import httpx

from ...database import get_pool
from ...services import storage_service

logger = logging.getLogger(__name__)

# Pre-compile regexes used in hot loops.
_DATA_URI_RE = re.compile(r"^data:[^;,]+;base64,(?P<b64>.+)$", re.DOTALL)
_DATA_URI_PLAIN_RE = re.compile(r"^data:[^;,]+,(?P<raw>.+)$", re.DOTALL)
_STASH_FILE_RE = re.compile(
    r"^(?:https?://[^/]+)?/api/v1/workspaces/(?P<wid>[0-9a-f-]+)/files/(?P<fid>[0-9a-f-]+)/download",
    re.IGNORECASE,
)

_MAX_BYTES = 25 * 1024 * 1024  # 25 MB hard cap per image
_HTTP_TIMEOUT_S = 10.0


class ImageFetchError(Exception):
    pass


class ImageFetcher:
    """Per-run cache so the same URL is fetched at most once per export."""

    def __init__(self) -> None:
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
            return await _download_stash_file(UUID(stash.group("fid")))

        if src.startswith("http://") or src.startswith("https://"):
            return await _download_http(src)

        # Protocol-relative or root-relative — try as http(s) on a best-effort
        # basis. PUBLIC_URL would be the right base; agents shouldn't be
        # emitting these in well-formed decks.
        logger.info("skipping unrecognised image src: %s", src[:120])
        return None


def _decode_data_uri(uri: str) -> bytes | None:
    m = _DATA_URI_RE.match(uri)
    if m:
        return base64.b64decode(m.group("b64"))
    m2 = _DATA_URI_PLAIN_RE.match(uri)
    if m2:
        from urllib.parse import unquote_to_bytes

        return unquote_to_bytes(m2.group("raw"))
    return None


async def _download_stash_file(file_id: UUID) -> bytes | None:
    pool = get_pool()
    row = await pool.fetchrow("SELECT storage_key FROM files WHERE id = $1", file_id)
    if not row or not row["storage_key"]:
        return None
    return await storage_service.download_file(row["storage_key"])


async def _download_http(url: str) -> bytes | None:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            buf = bytearray()
            async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                buf.extend(chunk)
                if len(buf) > _MAX_BYTES:
                    raise ImageFetchError(f"image exceeds {_MAX_BYTES} byte cap")
            return bytes(buf)
