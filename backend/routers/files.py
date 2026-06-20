"""Files router: workspace file upload/serve/delete.

Text extraction runs out-of-band: uploads insert the file row with
`extraction_status='pending'` and dispatch `extract_file_text.delay(file_id)`
to a Celery worker, which spawns a short-lived child to run pypdf under
RLIMIT_AS — keeping extraction off the request path and OOMs isolated."""

import csv
import io
import logging
import re
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..database import get_pool
from ..models import (
    CopyRequest,
    FileListResponse,
    FileResponse,
    FileUpdateRequest,
    TableListResponse,
    TableResponse,
    UploadResponse,
)
from ..services import (
    files_service,
    files_tree_service,
    permission_service,
    security_audit_service,
    storage_service,
    table_service,
    user_scope_service,
)
from ..services.csv_inference import coerce_value, infer_column_type
from ..services.xlsx_ingest import ingest_xlsx_bytes

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/api/v1/workspaces/{owner_user_id}/files", tags=["files"])
canonical_router = APIRouter(prefix="/api/v1/files", tags=["files"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# File rows are always read joined to their uploader so responses can show
# attribution ("Uploaded by Sam") without a second round trip.
_FILE_COLS = (
    "f.id, f.owner_user_id, f.folder_id, f.name, f.content_type, f.size_bytes, "
    "f.storage_key, f.uploaded_by, f.created_at, f.linked_table_id, "
    "u.name AS uploaded_by_name, u.display_name AS uploaded_by_display_name"
)
_FILE_FROM = "FROM files f JOIN users u ON u.id = f.uploaded_by"


async def _check_member(owner_user_id: UUID, user_id: UUID) -> None:
    """Read gate: any member."""
    if not await user_scope_service.is_member(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _check_write(owner_user_id: UUID, user_id: UUID) -> None:
    """Write gate: owner or editor only."""
    if not await user_scope_service.can_write(owner_user_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="Viewers can read but not modify files",
        )


async def _can_access_file(
    file_id: UUID,
    owner_user_id: UUID,
    user_id: UUID | None,
    *,
    require_write: bool = False,
) -> bool:
    if await permission_service.check_access(
        "file",
        file_id,
        user_id,
        owner_user_id=owner_user_id,
        require="write" if require_write else "read",
    ):
        return True
    return False


def _file_app_url(row: dict) -> str:
    return f"{settings.PUBLIC_URL.rstrip('/')}/f/{row['id']}"


def _page_app_url(page_id: UUID) -> str:
    return f"{settings.PUBLIC_URL.rstrip('/')}/p/{page_id}"


def _strip_ext(filename: str, exts: tuple[str, ...]) -> str:
    lower = filename.lower()
    for ext in exts:
        if lower.endswith(ext):
            return filename[: -len(ext)] or filename
    return filename


async def _file_to_response(row: dict) -> FileResponse:
    url = await storage_service.get_file_url(row["storage_key"])
    return FileResponse(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        folder_id=row.get("folder_id"),
        name=row["name"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        url=url,
        app_url=_file_app_url(row),
        uploaded_by=row["uploaded_by"],
        uploaded_by_name=row["uploaded_by_name"],
        uploaded_by_display_name=row.get("uploaded_by_display_name"),
        created_at=row["created_at"],
        linked_table_id=row.get("linked_table_id"),
    )


async def _fetch_file_row(file_id: UUID, owner_user_id: UUID) -> dict | None:
    """Fetch a single workspace file joined to its uploader, or None."""
    row = await get_pool().fetchrow(
        f"SELECT {_FILE_COLS} {_FILE_FROM} "
        "WHERE f.id = $1 AND f.owner_user_id = $2 AND f.deleted_at IS NULL",
        file_id,
        owner_user_id,
    )
    return dict(row) if row else None


async def _download_storage_file_or_502(storage_key: str, operation: str) -> bytes:
    try:
        return await storage_service.download_file(storage_key)
    except Exception as exc:
        logger.warning(
            "file storage download failed operation=%s exception_type=%s",
            operation,
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="File storage download failed") from exc


# ===== Workspace file endpoints =====


@ws_router.post("", response_model=UploadResponse, status_code=201)
async def upload_ws_file(
    owner_user_id: UUID,
    file: UploadFile,
    folder_id: UUID | None = Form(None),
    current_user: dict = Depends(get_current_user),
):
    # Workspace writers can upload anywhere; non-members can upload into a
    # specific folder shared with them with write permission.
    if not await user_scope_service.can_write(owner_user_id, current_user["id"]):
        can_write_folder = folder_id is not None and await permission_service.check_access(
            "folder",
            folder_id,
            current_user["id"],
            owner_user_id=owner_user_id,
            require="write",
        )
        if not can_write_folder:
            raise HTTPException(
                status_code=403,
                detail="Viewers can read but not modify files",
            )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"

    # Markdown and HTML belong in the pages table — they're editable in-app,
    # support comments, and live in the same VFS tree as binary files.
    # Anything else is a binary upload (S3-backed file row). Frontend, CLI,
    # and MCP all hit this single endpoint and get the routing for free.
    page_kind = files_tree_service.detect_page_kind(filename, content_type)
    if page_kind is not None:
        if folder_id is not None:
            pool = get_pool()
            owns = await pool.fetchval(
                "SELECT 1 FROM folders WHERE id = $1 AND owner_user_id = $2",
                folder_id,
                owner_user_id,
            )
            if not owns:
                raise HTTPException(
                    status_code=400,
                    detail="folder_id does not belong to workspace",
                )

        text = content.decode("utf-8", errors="replace")
        exts = (
            files_tree_service.MD_EXTS if page_kind == "markdown" else files_tree_service.HTML_EXTS
        )
        name = _strip_ext(filename, exts)

        try:
            page = await files_tree_service.create_page(
                owner_user_id=owner_user_id,
                name=name,
                created_by=current_user["id"],
                folder_id=folder_id,
                content=text if page_kind == "markdown" else "",
                content_html=text if page_kind == "html" else "",
                content_type=page_kind,
            )
        except files_tree_service.DuplicatePageName as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return UploadResponse(
            kind="page",
            id=page["id"],
            owner_user_id=page["owner_user_id"],
            folder_id=page.get("folder_id"),
            name=page["name"],
            content_type=page["content_type"],
            app_url=_page_app_url(page["id"]),
            created_at=page["created_at"],
            content_markdown=page.get("content_markdown") or None,
            content_html=page.get("content_html") or None,
            created_by=page["created_by"],
        )

    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")

    # HEIC is unsupported in every browser except Safari, so an iPhone
    # photo dropped onto a page renders as a broken image. Convert to
    # JPEG before storage.
    from ..services import image_transcode

    content, filename, content_type = await image_transcode.maybe_transcode_heic(
        content, filename, content_type
    )

    storage_key = await storage_service.upload_file(
        str(owner_user_id),
        filename,
        content,
        content_type,
    )

    pool = get_pool()
    if folder_id is not None:
        owns = await pool.fetchval(
            "SELECT 1 FROM folders WHERE id = $1 AND owner_user_id = $2",
            folder_id,
            owner_user_id,
        )
        if not owns:
            raise HTTPException(status_code=400, detail="folder_id does not belong to workspace")
    row = await pool.fetchrow(
        "INSERT INTO files (owner_user_id, name, content_type, size_bytes, storage_key, uploaded_by, folder_id) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) "
        "RETURNING id, owner_user_id, folder_id, name, content_type, size_bytes, storage_key, uploaded_by, created_at",
        owner_user_id,
        filename,
        content_type,
        len(content),
        storage_key,
        current_user["id"],
        folder_id,
    )
    from ..tasks.extraction import extract_file_text

    extract_file_text.delay(str(row["id"]))
    row_dict = dict(row)
    url = await storage_service.get_file_url(row_dict["storage_key"])
    return UploadResponse(
        kind="file",
        id=row_dict["id"],
        owner_user_id=row_dict["owner_user_id"],
        folder_id=row_dict.get("folder_id"),
        name=row_dict["name"],
        content_type=row_dict["content_type"],
        app_url=_file_app_url(row_dict),
        created_at=row_dict["created_at"],
        size_bytes=row_dict["size_bytes"],
        url=url,
        uploaded_by=row_dict["uploaded_by"],
        linked_table_id=row_dict.get("linked_table_id"),
    )


@ws_router.get("", response_model=FileListResponse)
async def list_ws_files(
    owner_user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(owner_user_id, current_user["id"])
    pool = get_pool()
    readable_file = permission_service.readable_content_condition("file", "f", 2)
    rows = await pool.fetch(
        f"SELECT {_FILE_COLS} {_FILE_FROM} "
        "WHERE f.owner_user_id = $1 AND f.deleted_at IS NULL "
        f"AND {readable_file} "
        "ORDER BY f.created_at DESC",
        owner_user_id,
        current_user["id"],
    )
    files = [await _file_to_response(dict(row)) for row in rows]
    return FileListResponse(files=files)


@canonical_router.get("/{file_id}", response_model=FileResponse)
async def get_file_by_id(
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Any failure is a 404: an unscoped lookup must not confirm that a
    file the caller can't read exists."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_FILE_COLS} {_FILE_FROM} WHERE f.id = $1 AND f.deleted_at IS NULL",
        file_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if not await _can_access_file(file_id, row["owner_user_id"], current_user["id"]):
        raise HTTPException(status_code=404, detail="File not found")
    return await _file_to_response(dict(row))


@ws_router.get("/{file_id}", response_model=FileResponse)
async def get_ws_file(
    owner_user_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    row = await _fetch_file_row(file_id, owner_user_id)
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if not await _can_access_file(file_id, owner_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="You don't have access to this file")
    return await _file_to_response(row)


@ws_router.get("/{file_id}/download")
async def download_ws_file(
    owner_user_id: UUID,
    file_id: UUID,
    current_user: dict | None = Depends(get_current_user_optional),
):
    """Permanent workspace URL for file links embedded in wiki pages."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT name, content_type, storage_key FROM files "
        "WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
        file_id,
        owner_user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    viewer_id = current_user["id"] if current_user else None
    if not await _can_access_file(file_id, owner_user_id, viewer_id):
        raise HTTPException(status_code=404, detail="File not found")
    content = await _download_storage_file_or_502(row["storage_key"], "file download")
    content_type = row["content_type"] or "application/octet-stream"
    # content_type is stored verbatim from the upload, so normalize away MIME
    # parameters and casing before the SVG check — 'image/svg+xml;charset=utf-8'
    # must not slip through.
    content_type = content_type.split(";")[0].strip().lower()
    # SVG is the one image type that executes script when rendered inline, so
    # it must download as an attachment — uploads are attacker-controlled.
    is_inline_image = content_type.startswith("image/") and content_type != "image/svg+xml"
    disposition = "inline" if is_inline_image else "attachment"
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(row['name'])}",
        },
    )


@ws_router.get("/{file_id}/text")
async def get_ws_file_text(
    owner_user_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(owner_user_id, current_user["id"])
    pool = get_pool()
    readable_file = permission_service.readable_content_condition("file", "f", 3)
    row = await pool.fetchrow(
        "SELECT extracted_text, extraction_status, extraction_error "
        "FROM files f WHERE f.id = $1 AND f.owner_user_id = $2 AND f.deleted_at IS NULL "
        f"AND {readable_file}",
        file_id,
        owner_user_id,
        current_user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "text": row["extracted_text"],
        "status": row["extraction_status"],
        "error": row["extraction_error"],
    }


@ws_router.patch("/{file_id}", response_model=FileResponse)
async def update_ws_file(
    owner_user_id: UUID,
    file_id: UUID,
    req: FileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update a file. Supports rename (`name`) and reparent
    (`folder_id` / `move_to_root`). Any subset can be passed; an empty
    request returns the file unchanged."""
    pool = get_pool()
    file_row = await pool.fetchrow(
        "SELECT * FROM files WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
        file_id,
        owner_user_id,
    )
    if not file_row:
        raise HTTPException(status_code=404, detail="File not found")
    if not await _can_access_file(file_id, owner_user_id, current_user["id"], require_write=True):
        raise HTTPException(status_code=404, detail="File not found")

    # Build the SET clause dynamically so we only touch fields the caller
    # actually sent — keeps name and folder_id independent.
    updates: list[str] = []
    params: list = []

    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        params.append(name)
        updates.append(f"name = ${len(params)}")

    if req.move_to_root:
        params.append(None)
        updates.append(f"folder_id = ${len(params)}")
    elif req.folder_id is not None:
        # Target folder must belong to the same workspace; otherwise files
        # could escape their workspace by getting reparented across the
        # boundary.
        owner = await pool.fetchrow(
            "SELECT owner_user_id FROM folders WHERE id = $1",
            req.folder_id,
        )
        if not owner or owner["owner_user_id"] != owner_user_id:
            raise HTTPException(status_code=404, detail="Folder not found")
        can_write_folder = await permission_service.check_access(
            "folder",
            req.folder_id,
            current_user["id"],
            owner_user_id=owner_user_id,
            require="write",
        )
        if not can_write_folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        params.append(req.folder_id)
        updates.append(f"folder_id = ${len(params)}")

    if not updates:
        return await _file_to_response(await _fetch_file_row(file_id, owner_user_id))

    params.append(file_id)
    file_id_pos = len(params)
    params.append(owner_user_id)
    ws_pos = len(params)
    await pool.execute(
        f"UPDATE files SET {', '.join(updates)} WHERE id = ${file_id_pos} AND owner_user_id = ${ws_pos}",
        *params,
    )
    return await _file_to_response(await _fetch_file_row(file_id, owner_user_id))


@ws_router.delete("/{file_id}", status_code=204)
async def delete_ws_file(
    owner_user_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Soft delete: stamps deleted_at + deleted_by. Object storage blob stays
    so a restore is fully reversible. Use POST /restore to undo or DELETE
    /purge to wipe permanently."""
    if not await _can_access_file(file_id, owner_user_id, current_user["id"], require_write=True):
        raise HTTPException(status_code=404, detail="File not found")
    trashed = await files_service.delete_file(file_id, owner_user_id, current_user["id"])
    if not trashed:
        raise HTTPException(status_code=404, detail="File not found")


@ws_router.post("/{file_id}/copy", response_model=FileResponse, status_code=201)
async def copy_ws_file(
    owner_user_id: UUID,
    file_id: UUID,
    req: CopyRequest,
    current_user: dict = Depends(get_current_user),
):
    """Duplicate a file (and its S3 blob) as 'Copy of <name>'."""
    if not await _can_access_file(file_id, owner_user_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="File not found")
    if req.target_folder_id is not None:
        can_write_folder = await permission_service.check_access(
            "folder",
            req.target_folder_id,
            current_user["id"],
            owner_user_id=owner_user_id,
            require="write",
        )
        if not can_write_folder:
            raise HTTPException(status_code=404, detail="Folder not found")
    else:
        await _check_write(owner_user_id, current_user["id"])
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")
    copied = await files_tree_service.copy_file(
        file_id, owner_user_id, current_user["id"], target_folder_id=req.target_folder_id
    )
    if not copied:
        raise HTTPException(status_code=404, detail="File not found")
    return await _file_to_response(await _fetch_file_row(copied["id"], owner_user_id))


@ws_router.post("/{file_id}/restore", status_code=204)
async def restore_ws_file(
    owner_user_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await _can_access_file(file_id, owner_user_id, current_user["id"], require_write=True):
        raise HTTPException(status_code=404, detail="File not found")
    restored = await files_service.restore_file(file_id, owner_user_id, current_user["id"])
    if not restored:
        raise HTTPException(status_code=404, detail="File not in trash")


@ws_router.delete("/{file_id}/purge", status_code=204)
async def purge_ws_file(
    owner_user_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Permanent delete — only callable on a file already in trash."""
    if not await _can_access_file(file_id, owner_user_id, current_user["id"], require_write=True):
        raise HTTPException(status_code=404, detail="File not found")
    row = await files_service.get_trashed_file(file_id, owner_user_id)
    if not row:
        raise HTTPException(status_code=404, detail="File not in trash")
    keep_blob = await files_service.storage_key_referenced_elsewhere(
        file_id,
        row["storage_key"],
    )
    if not keep_blob:
        await storage_service.delete_file(row["storage_key"])
    purged = await files_service.purge_file(file_id, owner_user_id)
    if not purged:
        raise HTTPException(status_code=404, detail="File not in trash")
    await security_audit_service.record_content_lifecycle_event(
        operation="purged",
        actor_user_id=current_user["id"],
        owner_user_id=owner_user_id,
        target_type="file",
        target_id=file_id,
        metadata={"storage_key_count": 0 if keep_blob else 1},
    )


# ===== CSV → Table ingest =====


@ws_router.post("/{file_id}/ingest-csv", response_model=TableResponse)
async def ingest_csv_file(
    owner_user_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Parse a CSV file into a real Table and link them.

    Idempotent: if the file is already linked, returns the existing table.
    """
    await _check_write(owner_user_id, current_user["id"])
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, owner_user_id, name, content_type, storage_key, linked_table_id "
        "FROM files WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
        file_id,
        owner_user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if not await _can_access_file(file_id, owner_user_id, current_user["id"], require_write=True):
        raise HTTPException(status_code=404, detail="File not found")
    if "csv" not in (row["content_type"] or ""):
        raise HTTPException(status_code=400, detail="File is not a CSV")
    if row["linked_table_id"]:
        existing = await table_service.get_table(row["linked_table_id"])
        if existing:
            return TableResponse(**existing)

    content = await _download_storage_file_or_502(row["storage_key"], "csv ingest")

    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    csv_rows = list(reader)
    if not csv_rows:
        raise HTTPException(status_code=400, detail="CSV is empty")

    header = csv_rows[0]
    data_rows = csv_rows[1:]
    sample = data_rows[:50]

    columns = []
    for ci, name in enumerate(header):
        samples = [(r[ci] if ci < len(r) else "") for r in sample]
        col_type = infer_column_type(samples)
        columns.append(
            {
                "id": _slugify(name) or f"col_{ci}",
                "name": name or f"col_{ci}",
                "type": col_type,
                "order": ci,
                "required": False,
                "default": None,
                "options": None,
            }
        )

    table_name = row["name"].rsplit(".", 1)[0] or row["name"]
    table = await table_service.create_table(
        owner_user_id=owner_user_id,
        name=table_name,
        description=f"Imported from {row['name']}",
        columns=columns,
        created_by=current_user["id"],
    )

    payload = []
    for r in data_rows:
        rec = {}
        for ci, col in enumerate(columns):
            raw = r[ci] if ci < len(r) else ""
            rec[col["id"]] = coerce_value(raw, col["type"])
        payload.append(rec)
    if payload:
        await table_service.create_rows_batch(
            table_id=table["id"], rows_data=payload, created_by=current_user["id"]
        )

    await pool.execute("UPDATE files SET linked_table_id = $1 WHERE id = $2", table["id"], file_id)

    refreshed = await table_service.get_table(table["id"])
    return TableResponse(**(refreshed or table))


_XLSX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


@ws_router.post("/{file_id}/ingest-xlsx", response_model=TableListResponse)
async def ingest_xlsx_file(
    owner_user_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Parse an .xlsx file into one table per sheet.

    Idempotent on the file's `linked_table_id` field, which points at the
    first sheet's table — re-running won't create duplicates, but it also
    won't re-discover sheets added to the workbook after the first
    ingest. (Re-import as a new file if the source workbook changes
    sheets.)
    """
    await _check_write(owner_user_id, current_user["id"])
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, owner_user_id, name, content_type, storage_key, linked_table_id "
        "FROM files WHERE id = $1 AND owner_user_id = $2 AND deleted_at IS NULL",
        file_id,
        owner_user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if not await _can_access_file(file_id, owner_user_id, current_user["id"], require_write=True):
        raise HTTPException(status_code=404, detail="File not found")

    ct = (row["content_type"] or "").lower()
    if not (ct in _XLSX_CONTENT_TYPES or row["name"].lower().endswith((".xlsx", ".xls"))):
        raise HTTPException(status_code=400, detail="File is not an Excel workbook")

    if row["linked_table_id"]:
        existing = await table_service.get_table(row["linked_table_id"])
        if existing:
            return TableListResponse(tables=[TableResponse(**existing)])

    content = await _download_storage_file_or_502(row["storage_key"], "xlsx ingest")

    base_name = row["name"].rsplit(".", 1)[0] or row["name"]
    try:
        created = await ingest_xlsx_bytes(
            owner_user_id=owner_user_id,
            user_id=current_user["id"],
            content=content,
            base_name=base_name,
            description_template=(f"Imported from {row['name']} (sheet: {{sheet}})"),
        )
    except Exception as exc:
        logger.warning(
            "xlsx ingest failed file_id=%s exception_type=%s",
            file_id,
            type(exc).__name__,
        )
        raise HTTPException(status_code=400, detail="Could not read workbook") from exc

    if not created:
        raise HTTPException(status_code=400, detail="Workbook had no visible sheets with data")

    await pool.execute(
        "UPDATE files SET linked_table_id = $1 WHERE id = $2",
        created[0]["id"],
        file_id,
    )

    return TableListResponse(tables=[TableResponse(**t) for t in created])


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", s.strip().lower())
    return re.sub(r"_+", "_", s).strip("_")
