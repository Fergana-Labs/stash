"""Documents router: upload, list, search, and delete documents for RAGFlow retrieval."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services import document_service, storage_service, workspace_service

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/documents", tags=["documents"])

MAX_DOC_SIZE = 100 * 1024 * 1024  # 100 MB


# --- Models ---


class DocumentResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    file_id: UUID | None
    name: str
    file_type: str
    status: str
    metadata: dict
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class DocumentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(20, ge=1, le=100)


class SearchChunk(BaseModel):
    content: str
    doc_name: str
    doc_id: str
    similarity: float


class DocumentSearchResponse(BaseModel):
    chunks: list[SearchChunk]


# --- Helpers ---


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


def _to_response(doc: dict) -> DocumentResponse:
    return DocumentResponse(
        id=doc["id"],
        workspace_id=doc["workspace_id"],
        file_id=doc.get("file_id"),
        name=doc["name"],
        file_type=doc["file_type"],
        status=doc["status"],
        metadata=doc.get("metadata", {}),
        created_by=doc["created_by"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


# --- Endpoints ---


@ws_router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    workspace_id: UUID,
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    """Upload a document (PDF, image, etc.) for RAGFlow processing and retrieval."""
    await _check_member(workspace_id, current_user["id"])

    from ..services import ragflow_client
    if not ragflow_client.is_configured():
        raise HTTPException(status_code=503, detail="RAGFlow is not configured")

    content = await file.read()
    if len(content) > MAX_DOC_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 100 MB)")

    filename = file.filename or "document"
    content_type = file.content_type or "application/octet-stream"
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"

    # Also store in S3 for archival
    file_id = None
    if storage_service.is_configured():
        from ..database import get_pool
        storage_key = await storage_service.upload_file(
            str(workspace_id), filename, content, content_type,
        )
        pool = get_pool()
        file_row = await pool.fetchrow(
            "INSERT INTO files (workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            workspace_id, filename, content_type, len(content), storage_key, current_user["id"],
        )
        file_id = file_row["id"]

    doc = await document_service.upload_document(
        workspace_id=workspace_id,
        file_id=file_id,
        name=filename,
        file_type=file_type,
        content=content,
        created_by=current_user["id"],
    )
    return _to_response(doc)


@ws_router.get("", response_model=DocumentListResponse)
async def list_documents(
    workspace_id: UUID,
    status: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    docs = await document_service.list_documents(workspace_id, status=status)
    return DocumentListResponse(documents=[_to_response(d) for d in docs])


@ws_router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    workspace_id: UUID, doc_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    doc = await document_service.get_document(doc_id)
    if not doc or doc.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return _to_response(doc)


@ws_router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    workspace_id: UUID,
    req: DocumentSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """Search across all ready documents in this workspace via RAGFlow."""
    await _check_member(workspace_id, current_user["id"])
    chunks = await document_service.search_documents(
        workspace_id, req.query, limit=req.limit,
    )
    return DocumentSearchResponse(
        chunks=[SearchChunk(**c) for c in chunks],
    )


@ws_router.delete("/{doc_id}", status_code=204)
async def delete_document(
    workspace_id: UUID, doc_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    doc = await document_service.get_document(doc_id)
    if not doc or doc.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Document not found")
    await document_service.delete_document(doc_id)
