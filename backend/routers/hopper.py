"""Hopper router: one front door into the VFS.

Three drop shapes — a file, a link, a note — each handed to the pipeline that
already knows how to read it: bytes through the files/pages ingest, a URL
through url_imports, typed text straight into a page. Nothing is recorded
here and nothing is parked: a drop becomes an ordinary VFS item the moment it
lands, which is the whole point of the hopper.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl

from ..auth import get_current_user, get_scope
from ..services import files_tree_service, url_import_service, user_scope_service
from .files import MAX_FILE_SIZE, _page_app_url, ingest_bytes

router = APIRouter(prefix="/api/v1/me/hopper", tags=["hopper"])

# A note is a page, and pages are markdown; the title is its first line so the
# VFS shows something recognizable.
NOTE_MAX_CHARS = 512_000
TITLE_MAX_CHARS = 80


class LinkDropRequest(BaseModel):
    url: HttpUrl


class NoteDropRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=NOTE_MAX_CHARS)


async def _writable_scope(current_user: dict, scope_user_id: UUID) -> UUID:
    if not await user_scope_service.can_write(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Only the owner can add to this stash")
    return scope_user_id


@router.post("/file", status_code=201)
async def drop_file(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
) -> dict:
    owner_user_id = await _writable_scope(current_user, scope_user_id)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 100 MB)")

    # Markdown and HTML become pages, everything else an S3-backed file whose
    # text extraction starts on insert — the ingest path decides, not us.
    uploaded = await ingest_bytes(
        owner_user_id=owner_user_id,
        user_id=current_user["id"],
        filename=file.filename or "upload",
        content=content,
        content_type=file.content_type or "application/octet-stream",
        folder_id=None,
    )
    return {
        "kind": uploaded.kind,
        "id": str(uploaded.id),
        "name": uploaded.name,
        "app_url": uploaded.app_url,
    }


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
    return {"kind": "link", "id": str(import_ids[0]), "name": url, "app_url": None}


@router.post("/note", status_code=201)
async def drop_note(
    body: NoteDropRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
) -> dict:
    owner_user_id = await _writable_scope(current_user, scope_user_id)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Note is empty")
    page = await files_tree_service.create_page_unique(
        owner_user_id,
        _title_from(body.text),
        current_user["id"],
        None,
        content=body.text,
        content_type="markdown",
    )
    return {
        "kind": "page",
        "id": str(page["id"]),
        "name": page["name"],
        "app_url": _page_app_url(page["id"]),
    }


def _title_from(text: str) -> str:
    """A note's page name: its first non-blank line. The endpoint rejects
    all-whitespace notes, so there is always one."""
    first_line = next(line for line in text.splitlines() if line.strip())
    return " ".join(first_line.split())[:TITLE_MAX_CHARS]
