"""PostgREST/supabase-js-compatible data API over stash tables.

A dashboard (or any vibe-coded UI) reads and writes tables through
`/rest/v1/{table}` using `supabase-js` or plain fetch — the grammar agents
already know. Callers authenticate one of two ways:

- **User token** (`mc_` or a short-lived read-only dashboard token) — sees the
  owner's own data. Workspace comes from a dashboard token's binding or the
  `X-Stash-Workspace` header for `mc_` callers.
- **Publishable key** (`pk_`, in the `apikey` or Authorization header) — the
  public/shared path. Workspace comes from the key; access is whatever explicit
  table policies grant (read-only unless a write policy exists).

Translation of the query grammar lives in `services/postgrest.py`; this router
does auth, table resolution, and the DB calls, and fails loud (501) on real
PostgREST features stash doesn't implement.
"""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .. import auth
from ..services import permission_service, postgrest, realtime, table_service, workspace_service

router = APIRouter(prefix="/rest/v1", tags=["data-api"])

_HEARTBEAT_S = 25


def _token(request: Request) -> str:
    """supabase-js sends the key in both `apikey` and `Authorization: Bearer`."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[len("bearer ") :].strip()
    apikey = request.headers.get("apikey")
    if apikey:
        return apikey
    raise HTTPException(status_code=401, detail="Missing credentials")


async def _principal_from_token(token: str) -> dict:
    if token.startswith(auth.PUBLISHABLE_KEY_PREFIX):
        info = await auth.resolve_publishable_key(token)
        return {"kind": "api_key", **info}
    return {"kind": "user", "user": await auth.resolve_user_token(token)}


async def data_principal(request: Request) -> dict:
    """Resolve the caller to a user principal or an anon (publishable-key) principal."""
    return await _principal_from_token(_token(request))


async def _user_workspace(request: Request, user: dict) -> UUID:
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


async def _load_table(
    request: Request, principal: dict, table: str, *, require: str
) -> tuple[dict, UUID]:
    """Resolve the table by name, authorize the principal, and return (table, writer_id)."""
    if principal["kind"] == "api_key":
        workspace_id = principal["workspace_id"]
        row = await table_service.get_table_by_name(workspace_id, table)
        if not row:
            raise HTTPException(status_code=404, detail=f"No table named '{table}'")
        allowed = await permission_service.check_anon_access(
            "table", row["id"], principal["key_id"], require
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Not allowed")
        return row, principal["created_by"]

    user = principal["user"]
    workspace_id = await _user_workspace(request, user)
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
    return row, user["id"]


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, postgrest.UnsupportedQuery):
        return HTTPException(status_code=501, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _require_row_id(request: Request) -> UUID:
    """PATCH/DELETE target a single row via `?id=eq.<uuid>` (the only supported filter)."""
    items = [
        (k, v) for k, v in request.query_params.multi_items() if k not in postgrest.RESERVED_PARAMS
    ]
    if len(items) != 1 or items[0][0] != "id" or not items[0][1].startswith("eq."):
        raise HTTPException(status_code=400, detail="Mutations require exactly id=eq.<row id>")
    try:
        return UUID(items[0][1][len("eq.") :])
    except ValueError:
        raise HTTPException(status_code=400, detail="id=eq.<row id> must be a UUID")


@router.get("/{table}")
async def list_rows(
    table: str,
    request: Request,
    response: Response,
    principal: dict = Depends(data_principal),
):
    row, _writer = await _load_table(request, principal, table, require="read")
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
        row["id"],
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    out = [postgrest.row_to_named(r, columns, project) for r in rows]
    response.headers["Content-Range"] = postgrest.content_range(offset, len(out), total)
    return out


@router.get("/{table}/subscribe")
async def subscribe(table: str, request: Request):
    """SSE stream of row-change nudges for the table. Browsers consume this with
    `EventSource`, which can't set headers — so the token rides as `?access_token=`
    (the short-lived read-only dashboard token, or a publishable key)."""
    token = request.query_params.get("access_token") or request.query_params.get("apikey")
    if not token:
        raise HTTPException(status_code=401, detail="Missing access_token")
    principal = await _principal_from_token(token)
    row, _writer = await _load_table(request, principal, table, require="read")
    key = realtime.table_key(row["id"])

    async def event_stream():
        queue = realtime.subscribe(key)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_S)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            realtime.unsubscribe(key, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{table}", status_code=201)
async def insert_rows(
    table: str,
    request: Request,
    principal: dict = Depends(data_principal),
):
    row, writer = await _load_table(request, principal, table, require="write")
    body = await request.json()
    columns = row["columns"]
    # RowValidationError (422) is handled globally in main.py.
    if isinstance(body, list):
        created = await table_service.create_rows_batch(row["id"], body, writer)
        return [postgrest.row_to_named(r, columns, None) for r in created]
    created = await table_service.create_row(row["id"], body, writer)
    return postgrest.row_to_named(created, columns, None)


@router.patch("/{table}")
async def update_rows(
    table: str,
    request: Request,
    principal: dict = Depends(data_principal),
):
    row, writer = await _load_table(request, principal, table, require="write")
    row_id = _require_row_id(request)
    body = await request.json()
    # RowValidationError (422) is handled globally in main.py.
    updated = await table_service.update_row(row_id, body, writer, table_id=row["id"])
    if not updated:
        raise HTTPException(status_code=404, detail="Row not found")
    return postgrest.row_to_named(updated, row["columns"], None)


@router.delete("/{table}", status_code=204)
async def delete_rows(
    table: str,
    request: Request,
    principal: dict = Depends(data_principal),
):
    row, _writer = await _load_table(request, principal, table, require="write")
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
