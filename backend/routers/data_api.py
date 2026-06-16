"""PostgREST/supabase-js-compatible data API over stash tables.

A dashboard (or any vibe-coded UI) reads and writes the owner's tables through
`/rest/v1/{table}` using `supabase-js` or plain fetch — the grammar agents
already know. Auth is the caller's stash identity (an `mc_` token or a
short-lived read-only dashboard token); the workspace comes from a dashboard
token's binding or the `X-Stash-Workspace` header for `mc_` callers.

Translation of the query grammar lives in `services/postgrest.py`; this router
does auth, table resolution, and the DB calls, and fails loud (501) on real
PostgREST features stash doesn't implement.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth import get_current_user
from ..services import permission_service, postgrest, table_service, workspace_service

router = APIRouter(prefix="/rest/v1", tags=["data-api"])


async def _resolve_workspace(request: Request, user: dict) -> UUID:
    """A dashboard token is workspace-bound; an mc_ caller names it via header."""
    bound = user.get("dashboard_workspace_id")
    if bound:
        return UUID(bound)
    header = request.headers.get("x-stash-workspace")
    if not header:
        raise HTTPException(status_code=400, detail="Missing X-Stash-Workspace header")
    workspace_id = UUID(header)
    if not await workspace_service.is_member(workspace_id, user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    return workspace_id


async def _load_table(request: Request, table: str, user: dict, *, require: str) -> dict:
    workspace_id = await _resolve_workspace(request, user)
    row = await table_service.get_table_by_name(workspace_id, table)
    if not row:
        raise HTTPException(status_code=404, detail=f"No table named '{table}'")
    if require != "read" and user.get("read_only"):
        raise HTTPException(status_code=403, detail="This token is read-only")
    allowed = await permission_service.check_access(
        "table", row["id"], user["id"], workspace_id=workspace_id, require=require
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Not allowed")
    return row


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, postgrest.UnsupportedQuery):
        return HTTPException(status_code=501, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _require_row_id(request: Request) -> UUID:
    """PATCH/DELETE target a single row via `?id=eq.<uuid>` (the only supported filter)."""
    items = [(k, v) for k, v in request.query_params.multi_items() if k not in postgrest.RESERVED_PARAMS]
    if len(items) != 1 or items[0][0] != "id" or not items[0][1].startswith("eq."):
        raise HTTPException(status_code=400, detail="Mutations require exactly id=eq.<row id>")
    try:
        return UUID(items[0][1][len("eq."):])
    except ValueError:
        raise HTTPException(status_code=400, detail="id=eq.<row id> must be a UUID")


@router.get("/{table}")
async def list_rows(
    table: str,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    row = await _load_table(request, table, current_user, require="read")
    columns = row["columns"]
    params = list(request.query_params.multi_items())
    try:
        filters = postgrest.parse_filters(params, columns)
        project = postgrest.parse_select(request.query_params.get("select"), columns)
        sort_by, sort_order = postgrest.parse_order(request.query_params.get("order"), columns)
    except (postgrest.UnsupportedQuery, postgrest.BadQuery) as exc:
        raise _translate(exc)

    limit = _int_param(request, "limit", 100)
    offset = _int_param(request, "offset", 0)
    rows, total = await table_service.list_rows(
        row["id"], filters=filters, sort_by=sort_by, sort_order=sort_order, limit=limit, offset=offset
    )
    out = [postgrest.row_to_named(r, columns, project) for r in rows]
    response.headers["Content-Range"] = postgrest.content_range(offset, len(out), total)
    return out


@router.post("/{table}", status_code=201)
async def insert_rows(
    table: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    row = await _load_table(request, table, current_user, require="write")
    body = await request.json()
    columns = row["columns"]
    # RowValidationError (422) is handled globally in main.py.
    if isinstance(body, list):
        created = await table_service.create_rows_batch(row["id"], body, current_user["id"])
        return [postgrest.row_to_named(r, columns, None) for r in created]
    created = await table_service.create_row(row["id"], body, current_user["id"])
    return postgrest.row_to_named(created, columns, None)


@router.patch("/{table}")
async def update_rows(
    table: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    row = await _load_table(request, table, current_user, require="write")
    row_id = _require_row_id(request)
    body = await request.json()
    # RowValidationError (422) is handled globally in main.py.
    updated = await table_service.update_row(row_id, body, current_user["id"], table_id=row["id"])
    if not updated:
        raise HTTPException(status_code=404, detail="Row not found")
    return postgrest.row_to_named(updated, row["columns"], None)


@router.delete("/{table}", status_code=204)
async def delete_rows(
    table: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    row = await _load_table(request, table, current_user, require="write")
    row_id = _require_row_id(request)
    deleted = await table_service.delete_row(row_id, table_id=row["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Row not found")
    return Response(status_code=204)


def _int_param(request: Request, name: str, default: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name} must be an integer")
