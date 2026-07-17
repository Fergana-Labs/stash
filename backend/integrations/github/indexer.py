"""GitHub repo → github_documents indexer.

The repo is a *connected source*, kept separate from the native file system.
We crawl the zipball (reusing the importer's streaming download + skip rules)
and copy each text file into github_documents keyed by its repo-relative path,
so the agent navigates the repo like a file system via the source tools.

Binary files are skipped — code and docs are text, and we don't want to push
every asset to S3 on each scheduled sync. Idempotent re-sync is handled upstream
by source_service (content-hash dedupe + soft-delete of paths that disappeared).
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ...services import source_service
from ..storage import get_valid_token
from .archive import UnsupportedHostError, _parse_owner_repo, resolve_archive_url
from .importers.repo import (
    MAX_FILES,
    _download_archive,
    _is_skipped_path,
    _strip_top_level_prefix,
)

logger = logging.getLogger(__name__)

# Postgres caps a row's tsvector at 1MB, and github_documents carries a
# full-text index on content — a bigger file aborts the whole repo's sync
# at insert time. Text files over this cap (minified bundles, lockfiles,
# data dumps) are skipped like binaries; 512KB keeps the vector safely
# under the limit.
MAX_INDEXED_TEXT_BYTES = 512 * 1024


async def _github_head_sha(url: str, headers: dict) -> str:
    """Latest commit SHA on the default branch — one cheap API call, used to
    skip the full zipball download when nothing changed since the last sync."""
    owner, repo = _parse_owner_repo(urlparse(url).path)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            params={"per_page": 1},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()[0]["sha"]


async def _crawl_archive(
    archive_url: str,
    headers: dict,
    on_text_file: Callable[[str, str], Awaitable[None]],
) -> list[str]:
    """Download + walk the archive, calling `on_text_file(rel_path, text)` for
    every readable text file. Returns the list of paths seen (for soft-delete)."""
    present: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        archive_path = Path(td) / "archive.zip"
        await _download_archive(archive_url, headers, archive_path)
        with zipfile.ZipFile(archive_path) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if len(names) > MAX_FILES:
                raise RuntimeError(f"archive has {len(names)} files; cap is {MAX_FILES}")
            top = _strip_top_level_prefix(zf.namelist())
            for member in names:
                rel = member
                if top is not None:
                    if not (rel == top or rel.startswith(top + "/")):
                        continue
                    rel = rel[len(top) + 1 :] if rel != top else ""
                if not rel or _is_skipped_path(Path(rel)):
                    continue
                info = zf.getinfo(member)
                if info.file_size > MAX_INDEXED_TEXT_BYTES:
                    continue
                with zf.open(info) as src:
                    raw = src.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue  # binary — skip
                await on_text_file(rel, text)
                present.append(rel)
    return present


async def index_github_repo(source: dict) -> str | None:
    """Crawl a connected GitHub repo into github_documents. `source` is the
    shape from source_service.get_source_for_sync. Returns the sync cursor."""
    from uuid import UUID

    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    external_ref = source["external_ref"]

    try:
        token = await get_valid_token(owner_user_id, "github")
    except Exception:
        token = None

    url = external_ref if "://" in external_ref else f"https://github.com/{external_ref}"
    try:
        resolved = resolve_archive_url(url, None, github_token=token)
    except UnsupportedHostError as e:
        raise RuntimeError(str(e))

    # Change detection is GitHub-only; other hosts always crawl.
    head_sha = None
    if resolved.host_kind == "github":
        head_sha = await _github_head_sha(url, resolved.headers)
        if head_sha == source["sync_cursor"]:
            logger.info("github source %s: HEAD unchanged, skipping crawl", source_id)
            return head_sha

    async def _on_text_file(rel: str, text: str) -> None:
        await source_service.upsert_content_document(
            table="github_documents",
            source_id=source_id,
            owner_user_id=owner_user_id,
            path=rel,
            name=rel.rsplit("/", 1)[-1],
            kind="file",
            content=text,
        )

    present = await _crawl_archive(resolved.archive_url, resolved.headers, _on_text_file)
    await source_service.remove_missing_documents("github_documents", source_id, present)
    logger.info("github source %s: indexed %d file(s)", source_id, len(present))
    return head_sha
