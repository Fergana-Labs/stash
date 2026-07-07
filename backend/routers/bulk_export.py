"""Bulk export: download everything you own as one zip of standard files.

This is the no-lock-in escape hatch we promise customers: folders become
directories, pages become plain .md/.html files, and uploads keep their
original bytes — nothing proprietary, so a customer can take their whole
company brain and leave (or just keep backups) at any time.
"""

import asyncio
import io
import zipfile
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..auth import get_current_user
from ..database import get_pool
from ..services import storage_service

router = APIRouter(prefix="/api/v1/me", tags=["export"])


def _clean(name: str) -> str:
    """A DB name must stay a single path segment inside the zip."""
    cleaned = name.replace("/", "_").replace("\\", "_").strip()
    return cleaned or "untitled"


def _folder_paths(folders: list) -> dict[UUID, str]:
    """Folder id -> zip directory path, mirroring the folder tree."""
    by_id = {f["id"]: f for f in folders}
    paths: dict[UUID, str] = {}

    def path_of(folder_id: UUID) -> str:
        if folder_id in paths:
            return paths[folder_id]
        folder = by_id[folder_id]
        parent_id = folder["parent_folder_id"]
        prefix = f"{path_of(parent_id)}/" if parent_id in by_id else ""
        paths[folder_id] = f"{prefix}{_clean(folder['name'])}"
        return paths[folder_id]

    for folder_id in by_id:
        path_of(folder_id)
    return paths


def _entry_path(folder_paths: dict[UUID, str], folder_id: UUID | None, filename: str) -> str:
    if folder_id in folder_paths:
        return f"{folder_paths[folder_id]}/{filename}"
    return filename


def _reserve(taken: set[str], path: str) -> str:
    """Zip entries silently shadow each other on duplicate names; number them."""
    candidate = path
    n = 2
    while candidate in taken:
        stem, dot, ext = path.rpartition(".")
        candidate = f"{stem} ({n}).{ext}" if dot else f"{path} ({n})"
        n += 1
    taken.add(candidate)
    return candidate


@router.get("/export")
async def export_everything(current_user: dict = Depends(get_current_user)):
    """The caller's entire scope as a zip.

    Embedded files (images pasted into pages) go under attachments/, named by
    the file id that page bodies reference in their download URLs, so the
    links inside exported markdown stay traceable to the exported bytes.
    """
    owner_user_id = current_user["id"]
    pool = get_pool()
    folder_rows, page_rows, file_rows = await asyncio.gather(
        pool.fetch(
            "SELECT id, name, parent_folder_id FROM folders WHERE owner_user_id = $1",
            owner_user_id,
        ),
        pool.fetch(
            "SELECT name, folder_id, content_type, content_markdown, content_html "
            "FROM pages WHERE owner_user_id = $1 AND deleted_at IS NULL",
            owner_user_id,
        ),
        pool.fetch(
            "SELECT id, name, folder_id, owner_page_id, storage_key "
            "FROM files WHERE owner_user_id = $1 AND deleted_at IS NULL",
            owner_user_id,
        ),
    )

    folder_paths = _folder_paths(folder_rows)
    taken: set[str] = set()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for dir_path in folder_paths.values():
            archive.writestr(f"{dir_path}/", b"")

        for page in page_rows:
            is_html = page["content_type"] == "html"
            ext = ".html" if is_html else ".md"
            name = _clean(page["name"])
            # Uploaded pages keep their extension in the page name; don't
            # double it (guide.md must round-trip as guide.md, not guide.md.md).
            filename = name if name.endswith(ext) else f"{name}{ext}"
            content = page["content_html"] if is_html else page["content_markdown"]
            path = _reserve(taken, _entry_path(folder_paths, page["folder_id"], filename))
            archive.writestr(path, content.encode())

        for file in file_rows:
            blob = await storage_service.download_file(file["storage_key"])
            if file["owner_page_id"]:
                path = f"attachments/{file['id']}-{_clean(file['name'])}"
            else:
                path = _entry_path(folder_paths, file["folder_id"], _clean(file["name"]))
            archive.writestr(_reserve(taken, path), blob)

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="stash-export-{stamp}.zip"'},
    )
