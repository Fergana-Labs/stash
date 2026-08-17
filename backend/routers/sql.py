"""SQL router: read-only queries over the scope's tables via stash sql,
plus the scope's external Postgres mounts."""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import get_current_user, get_scope
from ..middleware import limiter
from ..models import PgMountCreate, PgMountInfo, SqlQueryRequest, SqlQueryResponse
from ..services import pg_mount_service, security_audit_service, sql_service, user_scope_service

router = APIRouter(prefix="/api/v1/me", tags=["sql"])

# Every call materializes the scope's whole table set into a fresh DuckDB, so
# this is the most expensive endpoint in the app — capped like the other heavy
# ones (marketing chat) rather than left open.
_SQL_LIMIT = "30/minute"


@router.post("/sql", response_model=SqlQueryResponse)
@limiter.limit(_SQL_LIMIT)
async def run_sql(
    request: Request,
    req: SqlQueryRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    owner_user_id = scope_user_id
    if not await user_scope_service.can_read(owner_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not the scope owner")
    try:
        result = await sql_service.run_query(owner_user_id, current_user["id"], req.query)
    except sql_service.SqlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await security_audit_service.record_entries_listed(
        target_type="tables",
        actor_user_id=current_user["id"],
        owner_user_id=owner_user_id,
        metadata={"via": "sql", "result_rows": result["row_count"]},
    )
    return SqlQueryResponse(**result)


@router.get("/sql/mounts", response_model=list[PgMountInfo])
async def list_pg_mounts(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    if not await user_scope_service.can_read(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not the scope owner")
    return await pg_mount_service.list_mounts(scope_user_id)


@router.post("/sql/mounts", response_model=PgMountInfo, status_code=201)
async def create_pg_mount(
    req: PgMountCreate,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    if not await user_scope_service.can_write(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not the scope owner")
    try:
        return await pg_mount_service.create_mount(
            scope_user_id, req.name, req.dsn, req.remote_schema
        )
    except pg_mount_service.PgMountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail=f"mount {req.name!r} already exists") from None


@router.delete("/sql/mounts/{name}", status_code=204)
async def delete_pg_mount(
    name: str,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    if not await user_scope_service.can_write(scope_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not the scope owner")
    if not await pg_mount_service.delete_mount(scope_user_id, name):
        raise HTTPException(status_code=404, detail=f"no mount named {name!r}")
