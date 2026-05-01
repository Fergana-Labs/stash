"""Session transcripts: upload full .jsonl transcripts, fetch by session_id."""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from ..auth import get_current_user
from ..database import get_pool
from ..models import SessionTranscriptResponse
from ..services import storage_service, workspace_service

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/transcripts", tags=["transcripts"])

MAX_TRANSCRIPT_SIZE = 50 * 1024 * 1024  # matches files.py


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


@router.post("", response_model=SessionTranscriptResponse, status_code=201)
async def upload_transcript(
    workspace_id: UUID,
    file: UploadFile,
    session_id: str = Form(...),
    tag_name: str = Form(...),
    cwd: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")
    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")

    content = await file.read()
    if len(content) > MAX_TRANSCRIPT_SIZE:
        raise HTTPException(status_code=413, detail="Transcript too large (max 50 MB)")

    storage_key = await storage_service.upload_file(
        str(workspace_id),
        file.filename or f"{session_id}.jsonl",
        content,
        file.content_type or "application/jsonl",
    )

    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO session_transcripts "
        "(workspace_id, session_id, tag_name, storage_key, size_bytes, cwd, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) "
        "ON CONFLICT (workspace_id, session_id) DO NOTHING "
        "RETURNING id, workspace_id, session_id, tag_name, size_bytes, cwd, uploaded_by, uploaded_at",
        workspace_id,
        session_id,
        tag_name,
        storage_key,
        len(content),
        cwd,
        current_user["id"],
    )
    if not row:
        raise HTTPException(status_code=409, detail="Transcript already exists for this session")
    return SessionTranscriptResponse(**dict(row), download_url=None)


@router.get("/{session_id}", response_model=SessionTranscriptResponse)
async def get_transcript(
    workspace_id: UUID,
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, session_id, tag_name, storage_key, size_bytes, cwd, "
        "uploaded_by, uploaded_at FROM session_transcripts "
        "WHERE workspace_id = $1 AND session_id = $2 "
        "ORDER BY uploaded_at DESC LIMIT 1",
        workspace_id,
        session_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Transcript not found")
    url = await storage_service.get_file_url(row["storage_key"])
    return SessionTranscriptResponse(
        **{k: v for k, v in dict(row).items() if k != "storage_key"}, download_url=url
    )
