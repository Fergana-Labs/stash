"""Files router: workspace file upload/serve/delete.

Text extraction runs out-of-band: uploads insert the file row with
`extraction_status='pending'` and the dispatcher in backend/workers spawns a
short-lived child per file to run pypdf under RLIMIT, keeping extraction
off the request path.
"""

import csv
import io
import logging
import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth import get_current_user
from ..database import get_pool
from ..models import FileListResponse, FileResponse, TableResponse
from ..services import storage_service, table_service, workspace_service

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
        linked_table_id=row.get("linked_table_id"),
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
        "SELECT id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, created_at, linked_table_id "
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
        "SELECT id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, created_at, linked_table_id "
        "FROM files WHERE id = $1 AND workspace_id = $2",
        file_id,
        workspace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return await _file_to_response(dict(row))


@ws_router.get("/{file_id}/download")
async def download_ws_file(
    workspace_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Permanent, shareable URL → 302s to a freshly-signed S3 GET.

    Signed S3 URLs expire after an hour, so we can't embed them in page
    markdown. This endpoint's URL is stable, and wiki pages can link to
    it; each click re-signs and redirects.
    """
    await _check_member(workspace_id, current_user["id"])
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT storage_key FROM files WHERE id = $1 AND workspace_id = $2",
        file_id,
        workspace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    url = await storage_service.get_file_url(row["storage_key"])
    return RedirectResponse(url=url, status_code=302)


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


class FileUpdateRequest(BaseModel):
    public_in_share: bool | None = None


@ws_router.patch("/{file_id}", response_model=FileResponse)
async def patch_ws_file(
    workspace_id: UUID,
    file_id: UUID,
    req: FileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    pool = get_pool()
    sets, args, idx = [], [], 1
    if req.public_in_share is not None:
        sets.append(f"public_in_share = ${idx}")
        args.append(req.public_in_share)
        idx += 1
    if not sets:
        row = await pool.fetchrow(
            "SELECT id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, created_at, linked_table_id "
            "FROM files WHERE id = $1 AND workspace_id = $2",
            file_id,
            workspace_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        return await _file_to_response(dict(row))
    args.append(file_id)
    args.append(workspace_id)
    row = await pool.fetchrow(
        f"UPDATE files SET {', '.join(sets)} WHERE id = ${idx} AND workspace_id = ${idx + 1} "
        "RETURNING id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, created_at, linked_table_id",
        *args,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return await _file_to_response(dict(row))


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


# ===== CSV → Table ingest =====


_NUMERIC_RE = re.compile(r"^-?\$?[\d,]+(\.\d+)?%?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)?$")
_BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "0", "1"}


def _infer_column_type(samples: list[str]) -> str:
    """Pick the narrowest fit across the sampled values.

    Promotes upward on any miss: bool → number → date → text. Empty strings
    don't contribute to the decision.
    """
    nonempty = [s for s in samples if s != ""]
    if not nonempty:
        return "text"

    def matches(pred) -> bool:
        return all(pred(s) for s in nonempty)

    if matches(lambda s: s.lower() in _BOOL_VALUES):
        return "boolean"
    if matches(lambda s: bool(_NUMERIC_RE.match(s))):
        return "number"
    if matches(lambda s: bool(_DATE_RE.match(s))):
        # 'YYYY-MM-DD' or full ISO — use 'date' for the former, 'datetime' for the latter.
        if all("T" in s for s in nonempty):
            return "datetime"
        return "date"
    return "text"


def _coerce_value(raw: str, col_type: str):
    if raw == "":
        return None
    if col_type == "boolean":
        return raw.lower() in ("true", "yes", "y", "1")
    if col_type == "number":
        cleaned = raw.replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            v = float(cleaned)
            return int(v) if v.is_integer() else v
        except ValueError:
            return raw
    if col_type in ("date", "datetime"):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return raw
    return raw


@ws_router.post("/{file_id}/ingest-csv", response_model=TableResponse)
async def ingest_csv_file(
    workspace_id: UUID,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Parse a CSV file into a real Table and link them.

    Idempotent: if the file is already linked, returns the existing table.
    """
    await _check_member(workspace_id, current_user["id"])
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, name, content_type, storage_key, linked_table_id "
        "FROM files WHERE id = $1 AND workspace_id = $2",
        file_id,
        workspace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if "csv" not in (row["content_type"] or ""):
        raise HTTPException(status_code=400, detail="File is not a CSV")
    if row["linked_table_id"]:
        existing = await table_service.get_table(row["linked_table_id"])
        if existing:
            return TableResponse(**existing)

    try:
        content = await storage_service.download_file(row["storage_key"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"S3 download failed: {e}")

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
        col_type = _infer_column_type(samples)
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
        workspace_id=workspace_id,
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
            rec[col["id"]] = _coerce_value(raw, col["type"])
        payload.append(rec)
    if payload:
        await table_service.create_rows_batch(
            table_id=table["id"], rows_data=payload, created_by=current_user["id"]
        )

    await pool.execute("UPDATE files SET linked_table_id = $1 WHERE id = $2", table["id"], file_id)

    refreshed = await table_service.get_table(table["id"])
    return TableResponse(**(refreshed or table))


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", s.strip().lower())
    return re.sub(r"_+", "_", s).strip("_")
