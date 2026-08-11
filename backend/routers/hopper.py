"""Hopper router: one front door for "make this legible to my agent".

Three drop shapes — a file, a link, a note — each routed to the pipeline that
already knows how to read it, and one feed that answers whether the agent can
read it yet. Everything lands in the reserved Hopper folder, so the VFS has a
single place to browse what was dropped.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl

from ..auth import get_current_user, get_scope
from ..services import files_tree_service, hopper_service, url_import_service, user_scope_service
from .files import MAX_FILE_SIZE, ingest_bytes

router = APIRouter(prefix="/api/v1/me/hopper", tags=["hopper"])

FEED_LIMIT = 100

# A note is a page, and pages are markdown; the title is the first line so the
# VFS shows something recognizable.
NOTE_MAX_CHARS = 512_000
TITLE_MAX_CHARS = 80


class LinkDropRequest(BaseModel):
    url: HttpUrl


class NoteDropRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=NOTE_MAX_CHARS)


async def _writable_scope(current_user: dict, scope_user_id: UUID) -> UUID:
    if not await user_scope_service.can_write(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Only the owner can add to this hopper")
    return scope_user_id


@router.get("")
async def list_hopper(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
) -> dict:
    await _writable_scope(current_user, scope_user_id)
    folder = await hopper_service.find_folder(scope_user_id)
    return {
        "items": await hopper_service.list_items(scope_user_id, FEED_LIMIT),
        # Null until the first drop creates the folder — a read never does.
        "folder_id": str(folder["id"]) if folder else None,
    }


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

    folder = await hopper_service.get_or_create_folder(owner_user_id, current_user["id"])
    filename = file.filename or "upload"
    # Markdown and HTML become pages, everything else an S3-backed file whose
    # text extraction starts on insert — the ingest path decides, not us.
    uploaded = await ingest_bytes(
        owner_user_id=owner_user_id,
        user_id=current_user["id"],
        filename=filename,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        folder_id=folder["id"],
    )
    item_id = await hopper_service.record(
        owner_user_id=owner_user_id,
        created_by=current_user["id"],
        kind="file",
        label=filename,
        page_id=uploaded.id if uploaded.kind == "page" else None,
        file_id=uploaded.id if uploaded.kind == "file" else None,
    )
    return await hopper_service.get_item(item_id, owner_user_id)


@router.post("/link", status_code=201)
async def drop_link(
    body: LinkDropRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
) -> dict:
    from ..tasks.clips import dispatch_url_imports

    owner_user_id = await _writable_scope(current_user, scope_user_id)
    folder = await hopper_service.get_or_create_folder(owner_user_id, current_user["id"])
    url = str(body.url)
    import_ids = await url_import_service.create_url_imports(
        owner_user_id=owner_user_id,
        created_by=current_user["id"],
        items=[{"url": url, "folder_id": folder["id"]}],
    )
    await dispatch_url_imports(import_ids)
    item_id = await hopper_service.record(
        owner_user_id=owner_user_id,
        created_by=current_user["id"],
        kind="link",
        label=url,
        url_import_id=import_ids[0],
    )
    return await hopper_service.get_item(item_id, owner_user_id)


@router.post("/note", status_code=201)
async def drop_note(
    body: NoteDropRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
) -> dict:
    owner_user_id = await _writable_scope(current_user, scope_user_id)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Note is empty")
    folder = await hopper_service.get_or_create_folder(owner_user_id, current_user["id"])
    title = _title_from(body.text)
    page = await files_tree_service.create_page_unique(
        owner_user_id,
        title,
        current_user["id"],
        folder["id"],
        content=body.text,
        content_type="markdown",
    )
    item_id = await hopper_service.record(
        owner_user_id=owner_user_id,
        created_by=current_user["id"],
        kind="note",
        label=title,
        page_id=page["id"],
    )
    return await hopper_service.get_item(item_id, owner_user_id)


def _title_from(text: str) -> str:
    """A note's page name: its first non-blank line. The endpoint rejects
    all-whitespace notes, so there is always one."""
    first_line = next(line for line in text.splitlines() if line.strip())
    return " ".join(first_line.split())[:TITLE_MAX_CHARS]
