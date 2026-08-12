"""Hopper router: one front door into the VFS.

Two drop shapes — a file and a link — each handed to the pipeline that already
knows how to read it: bytes through the files/pages ingest, a URL through
url_imports. The hopper takes things that already exist; composing content is
what pages are for. Nothing is recorded here and nothing is parked: a drop
becomes an ordinary VFS item the moment it lands.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl

from ..auth import get_current_user, get_scope
from ..database import get_pool
from ..services import files_tree_service, url_import_service, user_scope_service
from .files import MAX_FILE_SIZE, _strip_ext, ingest_bytes

router = APIRouter(prefix="/api/v1/me/hopper", tags=["hopper"])

# Dropping a directory mirrors its structure, so the depth cap is the only
# guard against someone dragging in their home folder.
MAX_PATH_DEPTH = 10
MAX_SEGMENT_CHARS = 80


class LinkDropRequest(BaseModel):
    url: HttpUrl


async def _writable_scope(current_user: dict, scope_user_id: UUID) -> UUID:
    if not await user_scope_service.can_write(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Only the owner can add to this stash")
    return scope_user_id


@router.post("/file", status_code=201)
async def drop_file(
    file: UploadFile,
    # Relative folder path from a dropped directory ("catalogs/meritor"). The
    # user's own filing is the one destination we never have to guess at.
    path: str = Form(""),
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
) -> dict:
    owner_user_id = await _writable_scope(current_user, scope_user_id)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 100 MB)")

    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    folder_id = await _folder_for_path(owner_user_id, current_user["id"], path)

    # Re-dropping a directory must not double its contents. Same name, same
    # size, same folder is the same file for a person's purposes — and for a
    # page, whose name is unique in a folder anyway.
    existing = await _existing_item(owner_user_id, folder_id, filename, content_type, len(content))
    if existing:
        return {**existing, "duplicate": True}

    # Markdown and HTML become pages, everything else an S3-backed file whose
    # text extraction starts on insert — the ingest path decides, not us.
    uploaded = await ingest_bytes(
        owner_user_id=owner_user_id,
        user_id=current_user["id"],
        filename=filename,
        content=content,
        content_type=content_type,
        folder_id=folder_id,
    )
    return {
        "kind": uploaded.kind,
        "id": str(uploaded.id),
        "name": uploaded.name,
        "app_url": uploaded.app_url,
        "duplicate": False,
    }


async def _folder_for_path(owner_user_id: UUID, user_id: UUID, path: str) -> UUID | None:
    """Mirror a dropped directory's structure, creating folders as needed.
    An empty path means the top level, which is where single files land."""
    segments = [s.strip() for s in path.split("/") if s.strip() not in ("", ".", "..")]
    if not segments:
        return None
    if len(segments) > MAX_PATH_DEPTH:
        raise HTTPException(
            status_code=400, detail=f"Folder nesting deeper than {MAX_PATH_DEPTH} levels"
        )

    pool = get_pool()
    select = (
        "SELECT id, is_memory, is_protected FROM folders "
        "WHERE owner_user_id = $1 AND parent_folder_id IS NOT DISTINCT FROM $2 AND name = $3"
    )
    parent_id: UUID | None = None
    for segment in segments:
        name = segment[:MAX_SEGMENT_CHARS]
        row = await pool.fetchrow(select, owner_user_id, parent_id, name)
        if row is None:
            try:
                created = await files_tree_service.create_folder(
                    owner_user_id, name, user_id, parent_folder_id=parent_id
                )
                parent_id = created["id"]
                continue
            except files_tree_service.DuplicateFolderName:
                # Lost a race with a sibling upload in the same batch.
                row = await pool.fetchrow(select, owner_user_id, parent_id, name)
        # Memory and other protected folders are the product's, not the user's:
        # a dropped directory that happens to share a name must not pour its
        # contents into the wiki space, where Files would never show them again.
        if row["is_memory"] or row["is_protected"]:
            raise HTTPException(
                status_code=400,
                detail=f'"{name}" is reserved in your Stash — rename that folder and drop it again',
            )
        parent_id = row["id"]
    return parent_id


async def _existing_item(
    owner_user_id: UUID,
    folder_id: UUID | None,
    filename: str,
    content_type: str,
    size: int,
) -> dict | None:
    """The item this drop would duplicate, if there is one."""
    pool = get_pool()
    page_kind = files_tree_service.detect_page_kind(filename, content_type)
    if page_kind is not None:
        exts = (
            files_tree_service.MD_EXTS if page_kind == "markdown" else files_tree_service.HTML_EXTS
        )
        row = await pool.fetchrow(
            "SELECT id, name FROM pages WHERE owner_user_id = $1 "
            "AND folder_id IS NOT DISTINCT FROM $2 AND name = $3 AND deleted_at IS NULL",
            owner_user_id,
            folder_id,
            _strip_ext(filename, exts),
        )
        return (
            {"kind": "page", "id": str(row["id"]), "name": row["name"], "app_url": None}
            if row
            else None
        )
    row = await pool.fetchrow(
        "SELECT id, name FROM files WHERE owner_user_id = $1 "
        "AND folder_id IS NOT DISTINCT FROM $2 AND name = $3 AND size_bytes = $4 "
        "AND deleted_at IS NULL",
        owner_user_id,
        folder_id,
        filename,
        size,
    )
    return (
        {"kind": "file", "id": str(row["id"]), "name": row["name"], "app_url": None}
        if row
        else None
    )


@router.post("/link", status_code=201)
async def drop_link(
    body: LinkDropRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
) -> dict:
    from ..tasks.clips import dispatch_url_imports

    owner_user_id = await _writable_scope(current_user, scope_user_id)
    url = str(body.url)
    # The page behind the URL is fetched by a worker, so this returns as soon
    # as the job is queued; the clip lands in the VFS when it arrives.
    import_ids = await url_import_service.create_url_imports(
        owner_user_id=owner_user_id,
        created_by=current_user["id"],
        items=[{"url": url}],
    )
    await dispatch_url_imports(import_ids)
    return {
        "kind": "link",
        "id": str(import_ids[0]),
        "name": url,
        "app_url": None,
        "duplicate": False,
    }
