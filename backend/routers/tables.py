"""Table router: per-scope structured data tables."""

import csv
import io
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from ..models import (
    ColumnAddRequest,
    ColumnReorderRequest,
    ColumnUpdateRequest,
    RowBatchCreateRequest,
    RowBatchUpdateRequest,
    RowCreateRequest,
    RowListResponse,
    RowResponse,
    RowUpdateRequest,
    TableCreateRequest,
    TableListResponse,
    TableResponse,
    TableUpdateRequest,
)
from ..services import permission_service, table_service, user_scope_service

me_router = APIRouter(prefix="/api/v1/me/tables", tags=["tables"])
router = APIRouter(prefix="/api/v1/tables", tags=["tables"])


# --- Shared auth helpers ---


async def _check_member(owner_user_id: UUID, user_id: UUID) -> None:
    """Write gate (now the default): owner or editor only.

    Most table endpoints mutate state, so the default is safe-by-default
    write. Read-only endpoints opt into `_check_read` instead."""
    if not await user_scope_service.can_write(owner_user_id, user_id):
        if not await user_scope_service.is_owner(owner_user_id, user_id):
            raise HTTPException(status_code=403, detail="Not a scope member")
        raise HTTPException(
            status_code=403,
            detail="Viewers can read but not modify tables",
        )


async def _check_read(owner_user_id: UUID, user_id: UUID) -> None:
    """Read gate: any scope member (viewer/editor/owner)."""
    if not await user_scope_service.is_owner(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Not a scope member")


async def _check_ws_table(
    owner_user_id: UUID,
    table_id: UUID,
    *,
    with_row_count: bool = False,
) -> dict:
    """Verify table exists and belongs to the given scope."""
    if with_row_count:
        table = await table_service.get_table(table_id)
    else:
        table = await table_service.get_table_metadata(table_id)
    if not table or table.get("owner_user_id") != owner_user_id:
        raise HTTPException(status_code=404, detail="Table not found")
    return table


async def _check_table_access(
    owner_user_id: UUID,
    table_id: UUID,
    user_id: UUID,
    *,
    require_write: bool = False,
) -> None:
    allowed = await permission_service.check_access(
        "table",
        table_id,
        user_id,
        owner_user_id=owner_user_id,
        require="write" if require_write else "read",
    )
    if allowed:
        return
    raise HTTPException(status_code=404, detail="Table not found")


def _parse_row_ids(body: dict) -> list[UUID]:
    raw = body.get("row_ids", [])
    if not raw:
        raise HTTPException(status_code=400, detail="At least one row_id required")
    result = []
    for rid in raw:
        try:
            result.append(UUID(rid) if isinstance(rid, str) else rid)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Invalid UUID: {rid}")
    return result


# ===== Canonical table endpoint =====


@router.get("/{table_id}", response_model=TableResponse)
async def get_table_by_id(
    table_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Any failure is a 404: an unscoped lookup must not confirm that a
    table the caller can't read exists."""
    table = await table_service.get_table(table_id)
    if not table or not table.get("owner_user_id"):
        raise HTTPException(status_code=404, detail="Table not found")
    await _check_table_access(table["owner_user_id"], table_id, current_user["id"])
    return TableResponse(**table)


# ===== Scope table endpoints =====


@me_router.post("", response_model=TableResponse, status_code=201)
async def create_ws_table(
    req: TableCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    columns = [c.model_dump() for c in req.columns]
    try:
        table = await table_service.create_table(
            owner_user_id,
            req.name,
            req.description,
            columns,
            current_user["id"],
            folder_id=req.folder_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TableResponse(**table)


@me_router.get("", response_model=TableListResponse)
async def list_ws_tables(
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_read(owner_user_id, current_user["id"])
    tables = await table_service.list_tables(owner_user_id, current_user["id"])
    return TableListResponse(tables=[TableResponse(**t) for t in tables])


@me_router.get("/{table_id}", response_model=TableResponse)
async def get_ws_table(
    table_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_read(owner_user_id, current_user["id"])
    table = await _check_ws_table(owner_user_id, table_id, with_row_count=True)
    await _check_table_access(owner_user_id, table_id, current_user["id"])
    return TableResponse(**table)


@me_router.patch("/{table_id}", response_model=TableResponse)
async def update_ws_table(
    table_id: UUID,
    req: TableUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    table = await table_service.update_table(
        table_id,
        current_user["id"],
        name=req.name,
        description=req.description,
        folder_id=req.folder_id,
        move_to_root=req.move_to_root,
    )
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return TableResponse(**table)


@me_router.delete("/{table_id}", status_code=204)
async def delete_ws_table(
    table_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    if not await user_scope_service.is_owner(owner_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Editors and owners can delete tables")
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    deleted = await table_service.delete_table(table_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Table not found")


# --- Scope column endpoints ---


@me_router.post("/{table_id}/columns", response_model=TableResponse, status_code=201)
async def add_ws_column(
    table_id: UUID,
    req: ColumnAddRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    table = await table_service.add_column(table_id, req.model_dump(), current_user["id"])
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return TableResponse(**table)


@me_router.patch("/{table_id}/columns/{column_id}", response_model=TableResponse)
async def update_ws_column(
    table_id: UUID,
    column_id: str,
    req: ColumnUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    table = await table_service.update_column(
        table_id,
        column_id,
        req.model_dump(exclude_none=True),
        current_user["id"],
    )
    if not table:
        raise HTTPException(status_code=404, detail="Table or column not found")
    return TableResponse(**table)


@me_router.delete("/{table_id}/columns/{column_id}", response_model=TableResponse)
async def delete_ws_column(
    table_id: UUID,
    column_id: str,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    table = await table_service.delete_column(table_id, column_id, current_user["id"])
    if not table:
        raise HTTPException(status_code=404, detail="Table or column not found")
    return TableResponse(**table)


@me_router.put("/{table_id}/columns/reorder", response_model=TableResponse)
async def reorder_ws_columns(
    table_id: UUID,
    req: ColumnReorderRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    table = await table_service.reorder_columns(table_id, req.column_ids, current_user["id"])
    if not table:
        raise HTTPException(status_code=404, detail="Table not found or invalid column IDs")
    return TableResponse(**table)


# --- Scope row endpoints ---


@me_router.get("/{table_id}/rows", response_model=RowListResponse)
async def list_ws_rows(
    table_id: UUID,
    sort_by: str | None = Query(None),
    sort_order: str = Query("asc", pattern=r"^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    filters: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_read(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"])
    parsed_filters = json.loads(filters) if filters else None
    rows, total = await table_service.list_rows(
        table_id,
        filters=parsed_filters,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return RowListResponse(
        rows=[RowResponse(**r) for r in rows],
        total_count=total,
        has_more=offset + limit < total,
    )


@me_router.post("/{table_id}/rows", response_model=RowResponse, status_code=201)
async def create_ws_row(
    table_id: UUID,
    req: RowCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    row = await table_service.create_row(table_id, req.data, current_user["id"])
    return RowResponse(**row)


@me_router.post("/{table_id}/rows/batch", status_code=201)
async def create_ws_rows_batch(
    table_id: UUID,
    req: RowBatchCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    rows_data = [r.data for r in req.rows]
    rows = await table_service.create_rows_batch(table_id, rows_data, current_user["id"])
    return {"rows": [RowResponse(**r) for r in rows]}


@me_router.get("/{table_id}/rows/semantic-search")
async def semantic_search_ws_rows(
    table_id: UUID,
    q: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Semantic search on table rows using embeddings."""
    owner_user_id = current_user["id"]
    await _check_read(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"])
    from ..services import embeddings as embedding_service

    if not embedding_service.is_configured():
        raise HTTPException(status_code=503, detail="Embedding service not configured")
    query_embedding = await embedding_service.embed_text(q)
    if query_embedding is None:
        raise HTTPException(status_code=500, detail="Failed to embed query")
    rows = await table_service.search_rows_vector(table_id, query_embedding, limit)
    return {"rows": rows}


@me_router.patch("/{table_id}/rows/{row_id}", response_model=RowResponse)
async def update_ws_row(
    table_id: UUID,
    row_id: UUID,
    req: RowUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    row = await table_service.update_row(row_id, req.data, current_user["id"], table_id=table_id)
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")
    return RowResponse(**row)


@me_router.delete("/{table_id}/rows/{row_id}", status_code=204)
async def delete_ws_row(
    table_id: UUID,
    row_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    deleted = await table_service.delete_row(row_id, table_id=table_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Row not found")


@me_router.post("/{table_id}/rows/delete", status_code=200)
async def delete_ws_rows_batch(
    table_id: UUID,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    row_ids = _parse_row_ids(body)
    count = await table_service.delete_rows_batch(table_id, row_ids)
    return {"deleted": count}


@me_router.post("/{table_id}/rows/update", status_code=200)
async def update_ws_rows_batch(
    table_id: UUID,
    req: RowBatchUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    updates = [{"row_id": r.row_id, "data": r.data} for r in req.rows]
    rows = await table_service.update_rows_batch(table_id, updates, current_user["id"])
    return {"rows": [RowResponse(**r) for r in rows]}


@me_router.get("/{table_id}/rows/count")
async def count_ws_rows(
    table_id: UUID,
    filters: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_read(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"])
    parsed_filters = json.loads(filters) if filters else None
    count = await table_service.count_rows(table_id, filters=parsed_filters)
    return {"count": count}


@me_router.put("/{table_id}/embedding")
async def set_ws_embedding_config(
    table_id: UUID,
    config: dict,
    current_user: dict = Depends(get_current_user),
):
    """Configure which columns to embed for semantic search.

    Config: {"enabled": true, "columns": ["col_id1", "col_id2"]}
    """
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    result = await table_service.set_embedding_config(table_id, config, current_user["id"])
    if not result:
        raise HTTPException(status_code=404, detail="Table not found")
    return result


@me_router.post("/{table_id}/embedding/backfill")
async def backfill_ws_embeddings(
    table_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Re-embed all rows in the table based on current embedding config."""
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    return await table_service.backfill_embeddings(table_id)


@me_router.get("/{table_id}/export/csv")
async def export_ws_csv(
    table_id: UUID,
    filters: str | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str = Query("asc"),
    current_user: dict = Depends(get_current_user),
):
    """Export table as CSV. Streams all rows matching filters."""
    owner_user_id = current_user["id"]
    await _check_read(owner_user_id, current_user["id"])
    table = await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"])
    parsed_filters = json.loads(filters) if filters else None
    rows = await table_service.export_rows_all(
        table_id,
        filters=parsed_filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    cols = sorted(table["columns"], key=lambda c: c.get("order", 0))

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([c["name"] for c in cols])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for row in rows:
            writer.writerow([row["data"].get(c["id"], "") for c in cols])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f"{table['name'].replace(' ', '_')}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Scope search, summary, duplicate ---


@me_router.get("/{table_id}/rows/search")
async def search_ws_rows(
    table_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_read(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"])
    rows, total = await table_service.search_rows(table_id, q, limit=limit, offset=offset)
    return RowListResponse(
        rows=[RowResponse(**r) for r in rows],
        total_count=total,
        has_more=offset + limit < total,
    )


@me_router.get("/{table_id}/rows/summary")
async def summarize_ws_rows(
    table_id: UUID,
    filters: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_read(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"])
    parsed_filters = json.loads(filters) if filters else None
    return await table_service.summarize_rows(table_id, filters=parsed_filters)


@me_router.post("/{table_id}/rows/{row_id}/duplicate", response_model=RowResponse, status_code=201)
async def duplicate_ws_row(
    table_id: UUID,
    row_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    row = await table_service.duplicate_row(row_id, table_id, current_user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")
    return RowResponse(**row)


# --- Scope views ---


@me_router.post("/{table_id}/views", status_code=201)
async def save_ws_view(
    table_id: UUID,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    table = await table_service.save_view(table_id, body, current_user["id"])
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return table


@me_router.delete("/{table_id}/views/{view_id}")
async def delete_ws_view(
    table_id: UUID,
    view_id: str,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await _check_ws_table(owner_user_id, table_id)
    await _check_table_access(owner_user_id, table_id, current_user["id"], require_write=True)
    table = await table_service.delete_view(table_id, view_id, current_user["id"])
    if not table:
        raise HTTPException(status_code=404, detail="Table or view not found")
    return table
