"""Repo archive helpers — streaming download + path-walk rules.

Reused by backend/integrations/github/indexer.py to crawl a connected repo's
zipball into source_documents. (Formerly also held the one-shot
import-into-the-file-system task; that path was removed when repos became a
connected, indexed source.)

GitHub zip archives wrap everything in a top-level `owner-repo-sha/` directory.
We auto-strip the first path segment if every entry shares it — covers GitHub,
GitLab, and Bitbucket without host-specific logic. `.git/`, `node_modules/`, and
any path component starting with `.` are skipped.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_FILES = 5000
MAX_PER_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

SKIP_DIR_NAMES = {".git", "node_modules"}


def _is_skipped_path(rel_path: Path) -> bool:
    for part in rel_path.parts:
        if part in SKIP_DIR_NAMES:
            return True
        if part.startswith(".") and part not in (".",):
            return True
    return False


def _strip_top_level_prefix(names: list[str]) -> str | None:
    """Return the common top-level directory shared by every entry, or None."""
    if not names:
        return None
    first = names[0].split("/", 1)[0]
    if not first:
        return None
    for n in names[1:]:
        if not (n == first or n.startswith(first + "/")):
            return None
    return first


async def _download_archive(url: str, headers: dict, dest: Path) -> int:
    """Stream the archive to disk with a hard byte cap. Returns bytes written."""
    total = 0
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 404:
                raise RuntimeError("repo or ref not found (404)")
            if resp.status_code == 401:
                raise RuntimeError("authentication required (401) — connect GitHub or supply a PAT")
            resp.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(64 * 1024):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise RuntimeError(
                            f"archive exceeds {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB cap"
                        )
                    f.write(chunk)
    return total
