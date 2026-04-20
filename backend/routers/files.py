"""Files router: workspace file upload/serve/delete.

Text extraction runs out-of-band: uploads insert the file row with
`extraction_status='pending'` and the dispatcher in backend/workers spawns a
short-lived child per file to run pypdf under RLIMIT, keeping extraction
off the request path.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from ..auth import get_current_user
from ..database import get_pool
from ..models import FileListResponse, FileResponse
from ..services import storage_service, workspace_service

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/files", tags=["files"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _file_to_response(row: dict) -> FileResponse:
    url = await storage_service.get_file_url(row["storage_key"])
    return FileResponse(
        id=row["id"],
        workspace_id=row["workspace_id"],
        name=row["name"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        url=url,
        uploaded_by=row["uploaded_by"],
        created_at=row["created_at"],
    )


# ===== Workspace file endpoints =====


@ws_router.post("", response_model=FileResponse, status_code=201)
async def upload_ws_file(
    workspace_id: UUID,
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"

    storage_key = await storage_service.upload_file(
        str(workspace_id),
        filename,
        content,
        content_type,
    )

    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO files (workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6) "
        "RETURNING id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, created_at",
        workspace_id,
        filename,
        content_type,
        len(content),
        storage_key,
        current_user["id"],
    )
    return await _file_to_response(dict(row))


@ws_router.get("", response_model=FileListResponse)
async def list_ws_files(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, created_at "
        "FROM files WHERE workspace_id = $1 ORDER BY created_at DESC",
        workspace_id,
    )
    files = [await _file_to_response(dict(r)) for r in rows]
    return FileListResponse(files=files)


@ws_router.get("/{file_id}", response_model=FileResponse)
async def get_ws_file(
    workspace_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, created_at "
        "FROM files WHERE id = $1 AND workspace_id = $2",
        file_id,
        workspace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return await _file_to_response(dict(row))


@ws_router.get("/{file_id}/text")
async def get_ws_file_text(
    workspace_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT extracted_text, extraction_status, extraction_error "
        "FROM files WHERE id = $1 AND workspace_id = $2",
        file_id,
        workspace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "text": row["extracted_text"],
        "status": row["extraction_status"],
        "error": row["extraction_error"],
    }


@ws_router.delete("/{file_id}", status_code=204)
async def delete_ws_file(
    workspace_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT storage_key FROM files WHERE id = $1 AND workspace_id = $2",
        file_id,
        workspace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        await storage_service.delete_file(row["storage_key"])
    except Exception:
        pass  # Best-effort S3 cleanup
    await pool.execute(
        "DELETE FROM files WHERE id = $1 AND workspace_id = $2", file_id, workspace_id
    )


