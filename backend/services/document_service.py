"""Document service: manages documents for RAGFlow-based retrieval.

Upload flow: store file via storage_service → forward to RAGFlow → track status.
Search flow: query RAGFlow → return ranked chunks.
"""

import asyncio
import logging
from uuid import UUID

from ..database import get_pool
from . import ragflow_client, storage_service

logger = logging.getLogger(__name__)


async def _ensure_dataset(workspace_id: UUID) -> str:
    """Get or create the RAGFlow dataset for a workspace."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT ragflow_dataset_id FROM workspaces WHERE id = $1", workspace_id,
    )
    if row and row["ragflow_dataset_id"]:
        return row["ragflow_dataset_id"]

    # Fetch workspace name for the dataset
    ws = await pool.fetchrow("SELECT name FROM workspaces WHERE id = $1", workspace_id)
    ws_name = ws["name"] if ws else str(workspace_id)

    dataset_id = await ragflow_client.create_dataset(
        name=f"octopus-{ws_name}",
        description=f"Octopus workspace: {ws_name}",
    )
    await pool.execute(
        "UPDATE workspaces SET ragflow_dataset_id = $1 WHERE id = $2",
        dataset_id, workspace_id,
    )
    return dataset_id


async def upload_document(
    workspace_id: UUID,
    file_id: UUID | None,
    name: str,
    file_type: str,
    content: bytes,
    created_by: UUID,
) -> dict:
    """Upload a document for RAGFlow processing."""
    if not ragflow_client.is_configured():
        raise RuntimeError("RAGFlow is not configured")

    pool = get_pool()
    dataset_id = await _ensure_dataset(workspace_id)

    # Upload to RAGFlow
    ragflow_doc_id = await ragflow_client.upload_document(dataset_id, name, content)

    # Store document record
    row = await pool.fetchrow(
        "INSERT INTO documents "
        "(workspace_id, file_id, name, file_type, ragflow_dataset_id, ragflow_doc_id, status, created_by) "
        "VALUES ($1, $2, $3, $4, $5, $6, 'processing', $7) "
        "RETURNING id, workspace_id, file_id, name, file_type, ragflow_dataset_id, "
        "ragflow_doc_id, status, metadata, created_by, created_at, updated_at",
        workspace_id, file_id, name, file_type, dataset_id, ragflow_doc_id, created_by,
    )
    doc = dict(row)

    # Trigger parsing (fire-and-forget)
    asyncio.create_task(_start_parsing(dataset_id, ragflow_doc_id, doc["id"]))

    return doc


async def _start_parsing(dataset_id: str, ragflow_doc_id: str, doc_id: UUID) -> None:
    """Start RAGFlow parsing and poll for completion."""
    try:
        await ragflow_client.start_parsing(dataset_id, [ragflow_doc_id])
    except Exception:
        logger.warning("Failed to start parsing for doc %s", doc_id, exc_info=True)
        pool = get_pool()
        await pool.execute(
            "UPDATE documents SET status = 'error', updated_at = now() WHERE id = $1", doc_id,
        )
        return

    # Poll for completion (max 10 minutes)
    pool = get_pool()
    for _ in range(60):
        await asyncio.sleep(10)
        try:
            status = await ragflow_client.get_document_status(dataset_id, ragflow_doc_id)
            run = status.get("run", "UNSTART")
            if run == "DONE":
                await pool.execute(
                    "UPDATE documents SET status = 'ready', "
                    "metadata = metadata || $1, updated_at = now() WHERE id = $2",
                    {"chunk_count": status.get("chunk_count", 0)}, doc_id,
                )
                return
            if run == "FAIL":
                await pool.execute(
                    "UPDATE documents SET status = 'error', "
                    "metadata = metadata || $1, updated_at = now() WHERE id = $2",
                    {"error": status.get("progress_msg", "parsing failed")}, doc_id,
                )
                return
        except Exception:
            logger.debug("Status poll error for doc %s", doc_id, exc_info=True)

    # Timeout
    await pool.execute(
        "UPDATE documents SET status = 'error', "
        "metadata = metadata || '{\"error\": \"parsing timeout\"}'::jsonb, "
        "updated_at = now() WHERE id = $1",
        doc_id,
    )


async def get_document(doc_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, file_id, name, file_type, ragflow_dataset_id, "
        "ragflow_doc_id, status, metadata, created_by, created_at, updated_at "
        "FROM documents WHERE id = $1",
        doc_id,
    )
    return dict(row) if row else None


async def list_documents(workspace_id: UUID, status: str | None = None) -> list[dict]:
    pool = get_pool()
    if status:
        rows = await pool.fetch(
            "SELECT id, workspace_id, file_id, name, file_type, ragflow_dataset_id, "
            "ragflow_doc_id, status, metadata, created_by, created_at, updated_at "
            "FROM documents WHERE workspace_id = $1 AND status = $2 "
            "ORDER BY created_at DESC",
            workspace_id, status,
        )
    else:
        rows = await pool.fetch(
            "SELECT id, workspace_id, file_id, name, file_type, ragflow_dataset_id, "
            "ragflow_doc_id, status, metadata, created_by, created_at, updated_at "
            "FROM documents WHERE workspace_id = $1 ORDER BY created_at DESC",
            workspace_id,
        )
    return [dict(r) for r in rows]


async def search_documents(workspace_id: UUID, query: str, limit: int = 20) -> list[dict]:
    """Search across all ready documents in a workspace via RAGFlow."""
    if not ragflow_client.is_configured():
        return []

    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT ragflow_dataset_id FROM workspaces WHERE id = $1", workspace_id,
    )
    if not row or not row["ragflow_dataset_id"]:
        return []

    return await ragflow_client.search(
        dataset_ids=[row["ragflow_dataset_id"]],
        query=query,
        limit=limit,
    )


async def delete_document(doc_id: UUID) -> bool:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT ragflow_dataset_id, ragflow_doc_id, file_id FROM documents WHERE id = $1",
        doc_id,
    )
    if not row:
        return False

    # Delete from RAGFlow (best-effort)
    if row["ragflow_dataset_id"] and row["ragflow_doc_id"]:
        try:
            await ragflow_client.delete_document(row["ragflow_dataset_id"], row["ragflow_doc_id"])
        except Exception:
            logger.warning("Failed to delete doc from RAGFlow: %s", doc_id, exc_info=True)

    # Delete S3 file if linked (best-effort)
    if row["file_id"]:
        file_row = await pool.fetchrow(
            "SELECT storage_key FROM files WHERE id = $1", row["file_id"],
        )
        if file_row:
            try:
                await storage_service.delete_file(file_row["storage_key"])
            except Exception:
                pass
            await pool.execute("DELETE FROM files WHERE id = $1", row["file_id"])

    await pool.execute("DELETE FROM documents WHERE id = $1", doc_id)
    return True
