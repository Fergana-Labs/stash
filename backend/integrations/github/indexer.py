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

from ...services import source_service
from ..storage import get_valid_token
from .archive import UnsupportedHostError, resolve_archive_url
from .importers.repo import (
    MAX_FILES,
    MAX_PER_FILE_BYTES,
    _download_archive,
    _is_skipped_path,
    _strip_top_level_prefix,
)

logger = logging.getLogger(__name__)


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
                if info.file_size > MAX_PER_FILE_BYTES:
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
    workspace_id = UUID(source["workspace_id"])
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

    async def _on_text_file(rel: str, text: str) -> None:
        await source_service.upsert_content_document(
            table="github_documents",
            source_id=source_id,
            workspace_id=workspace_id,
            path=rel,
            name=rel.rsplit("/", 1)[-1],
            kind="file",
            content=text,
        )

    present = await _crawl_archive(resolved.archive_url, resolved.headers, _on_text_file)
    await source_service.soft_delete_missing("github_documents", source_id, present)
    logger.info("github source %s: indexed %d file(s)", source_id, len(present))
    return None
