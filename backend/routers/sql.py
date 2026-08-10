"""SQL router: read-only queries over the scope's tables via stash sql."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import get_current_user, get_scope
from ..middleware import limiter
from ..models import SqlQueryRequest, SqlQueryResponse
from ..services import security_audit_service, sql_service, user_scope_service

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
