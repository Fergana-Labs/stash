"""Repo zipball importer.

Streams the repo archive from the host, unzips into a tempdir under
strict size + count limits, and ingests every file:
  - *.md / *.mdx → pages (markdown)
  - everything else → files rows uploaded to S3; the extraction queue
    picks up text-extractable formats automatically.

Folder structure mirrors the repo. `.git/`, `node_modules/`, and any
path component starting with `.` (e.g. `.github/`, `.next/`) are
skipped.

GitHub zip archives wrap everything in a top-level `owner-repo-sha/`
directory. We auto-strip the first path segment if every entry shares
it — covers GitHub, GitLab, and Bitbucket without host-specific logic.
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path
from uuid import UUID

import asyncpg
import httpx

from ....celery_app import celery
from ....database import get_pool
from ....services import files_tree_service, storage_service
from ....tasks._celery_helpers import run_async
from ..archive import UnsupportedHostError, resolve_archive_url

logger = logging.getLogger(__name__)

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024   # 100 MB
MAX_FILES = 5000
MAX_PER_FILE_BYTES = 10 * 1024 * 1024   # 10 MB

MARKDOWN_SUFFIXES = {".md", ".mdx"}
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


async def _ensure_folder_path(
    workspace_id: UUID,
    user_id: UUID,
    root_folder_id: UUID | None,
    rel_dir: Path,
    cache: dict[tuple[UUID | None, str], UUID],
) -> UUID | None:
    """Walk a relative directory and create any missing folders. Returns leaf id."""
    current_id: UUID | None = root_folder_id
    if rel_dir == Path(".") or str(rel_dir) == "":
        return current_id
    for part in rel_dir.parts:
        cache_key = (current_id, part)
        if cache_key in cache:
            current_id = cache[cache_key]
            continue
        try:
            folder = await files_tree_service.create_folder(
                workspace_id=workspace_id,
                name=part,
                created_by=user_id,
                parent_folder_id=current_id,
            )
            current_id = folder["id"]
        except files_tree_service.DuplicateFolderName:
            pool = get_pool()
            row = await pool.fetchrow(
                "SELECT id FROM folders WHERE workspace_id = $1 AND name = $2 "
                "AND parent_folder_id IS NOT DISTINCT FROM $3",
                workspace_id,
                part,
                current_id,
            )
            if row is None:
                raise
            current_id = row["id"]
        cache[cache_key] = current_id  # type: ignore[assignment]
    return current_id


async def _insert_page(
    workspace_id: UUID,
    folder_id: UUID | None,
    user_id: UUID,
    name: str,
    content: str,
) -> None:
    pool = get_pool()
    try:
        await pool.execute(
            """
            INSERT INTO pages (
                workspace_id, folder_id, name, content_markdown,
                content_type, html_layout, created_by
            ) VALUES ($1, $2, $3, $4, 'markdown', 'responsive', $5)
            """,
            workspace_id,
            folder_id,
            name,
            content,
            user_id,
        )
    except asyncpg.UniqueViolationError:
        # Duplicate name within the same folder — append a counter.
        await pool.execute(
            """
            INSERT INTO pages (
                workspace_id, folder_id, name, content_markdown,
                content_type, html_layout, created_by
            ) VALUES ($1, $2, $3 || ' (imported)', $4, 'markdown', 'responsive', $5)
            """,
            workspace_id,
            folder_id,
            name,
            content,
            user_id,
        )


async def _insert_file(
    workspace_id: UUID,
    folder_id: UUID | None,
    user_id: UUID,
    filename: str,
    content: bytes,
) -> None:
    storage_key = await storage_service.upload_file(
        workspace_id=workspace_id,
        filename=filename,
        content=content,
        content_type="application/octet-stream",
    )
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO files (
            workspace_id, folder_id, name, content_type, size_bytes,
            storage_key, uploaded_by
        ) VALUES ($1, $2, $3, 'application/octet-stream', $4, $5, $6)
        RETURNING id
        """,
        workspace_id,
        folder_id,
        filename,
        len(content),
        storage_key,
        user_id,
    )
    # Dispatch text extraction so PDF/txt/JSON become searchable.
    from ....tasks.extraction import extract_file_text
    extract_file_text.delay(str(row["id"]))


async def _import(
    user_id: UUID,
    workspace_id: UUID,
    url: str,
    ref: str | None,
    subpath: str | None,
    pat: str | None,
    folder_id: UUID | None,
) -> dict:
    from ..archive import resolve_archive_url as _resolve

    # Use the user's stored GitHub token if they have one.
    github_token: str | None = None
    try:
        from ...storage import get_valid_token

        github_token = await get_valid_token(user_id, "github")
    except Exception:
        github_token = None

    try:
        resolved = _resolve(url, ref, github_token=github_token, pat=pat)
    except UnsupportedHostError as e:
        raise RuntimeError(str(e))

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        archive_path = td_path / "archive.zip"
        size = await _download_archive(resolved.archive_url, resolved.headers, archive_path)
        logger.info(
            "git import: fetched %s (%d bytes, host=%s)",
            url,
            size,
            resolved.host_kind,
        )

        unpack_dir = td_path / "unpacked"
        unpack_dir.mkdir()
        pages_created = 0
        files_created = 0
        skipped = 0
        folder_cache: dict[tuple[UUID | None, str], UUID] = {}
        with zipfile.ZipFile(archive_path) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if len(names) > MAX_FILES:
                raise RuntimeError(
                    f"archive has {len(names)} files; cap is {MAX_FILES}"
                )
            top = _strip_top_level_prefix(zf.namelist())

            subpath_clean = (subpath or "").strip("/")
            for member in names:
                rel = member
                if top is not None:
                    if not rel.startswith(top + "/") and rel != top:
                        continue
                    rel = rel[len(top) + 1:] if rel != top else ""
                if not rel:
                    continue
                if subpath_clean and not (
                    rel == subpath_clean or rel.startswith(subpath_clean + "/")
                ):
                    continue
                if subpath_clean:
                    rel_inside_sub = rel[len(subpath_clean):].lstrip("/")
                else:
                    rel_inside_sub = rel
                rel_path = Path(rel_inside_sub)
                if _is_skipped_path(rel_path):
                    skipped += 1
                    continue

                info = zf.getinfo(member)
                if info.file_size > MAX_PER_FILE_BYTES:
                    skipped += 1
                    logger.info("git import: skip oversized file %s (%d bytes)", rel, info.file_size)
                    continue

                with zf.open(info) as src:
                    content = src.read()

                rel_dir = rel_path.parent
                leaf_folder = await _ensure_folder_path(
                    workspace_id, user_id, folder_id, rel_dir, folder_cache
                )

                if rel_path.suffix.lower() in MARKDOWN_SUFFIXES:
                    page_name = rel_path.stem
                    try:
                        await _insert_page(
                            workspace_id, leaf_folder, user_id, page_name, content.decode("utf-8", errors="replace")
                        )
                        pages_created += 1
                    except Exception:
                        logger.exception("git import: failed page insert %s", rel)
                        skipped += 1
                else:
                    try:
                        await _insert_file(
                            workspace_id, leaf_folder, user_id, rel_path.name, content
                        )
                        files_created += 1
                    except Exception:
                        logger.exception("git import: failed file insert %s", rel)
                        skipped += 1

        return {
            "pages_created": pages_created,
            "files_created": files_created,
            "skipped": skipped,
            "host": resolved.host_kind,
            "archive_bytes": size,
        }


@celery.task(name="backend.integrations.github.importers.repo.import_repo")
def import_repo(
    user_id: str,
    workspace_id: str,
    url: str,
    ref: str | None = None,
    subpath: str | None = None,
    pat: str | None = None,
    folder_id: str | None = None,
) -> dict:
    return run_async(
        _import(
            user_id=UUID(user_id),
            workspace_id=UUID(workspace_id),
            url=url,
            ref=ref,
            subpath=subpath,
            pat=pat,
            folder_id=UUID(folder_id) if folder_id else None,
        )
    )
