"""Private evidence of developer reads, persisted before returning the payload.

This table has no customer API, VFS mount, search index, or curator input.
Response bodies must never be copied into history_events or security-event
metadata: both are readable product surfaces. A record proves the server
prepared a response, not that the remote client or a human received it.
"""

import hashlib
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..database import get_pool
from . import end_user_service


def correlation_header(request: Request, name: str) -> str | None:
    value = request.headers.get(name)
    if value is not None and (not value.strip() or len(value) > 128):
        raise HTTPException(status_code=400, detail=f"{name} must contain 1–128 characters")
    return value


async def record_response(
    request: Request,
    *,
    owner_user_id: UUID,
    actor_user_id: UUID,
    external_user_id: str | None,
    request_data: dict,
    content: object,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response = JSONResponse(jsonable_encoder(content), status_code=status_code, headers=headers)
    workspace = await end_user_service.workspace_for_scope(owner_user_id)
    if workspace is None or workspace["external_wiki_folder_id"] is None:
        return response

    session_id = correlation_header(request, "X-Stash-Session-Id")
    workflow_run_id = correlation_header(request, "X-Stash-Workflow-Run-Id")
    request_id = uuid4()
    # Await the insert: a failed audit write must not release an unrecorded
    # customer payload. bytea preserves the exact JSON bytes, including NULs.
    try:
        await get_pool().execute(
            "INSERT INTO read_response_audits "
            "(id,workspace_id,actor_user_id,external_user_id,session_id,workflow_run_id,"
            "method,path,request_data,status_code,response_body,response_sha256) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12)",
            request_id,
            workspace["id"],
            actor_user_id,
            external_user_id,
            session_id,
            workflow_run_id,
            request.method,
            request.url.path,
            request_data,
            status_code,
            response.body,
            hashlib.sha256(response.body).hexdigest(),
        )
    except Exception:
        # Do not log the exception with SQL arguments or the response body.
        raise HTTPException(
            status_code=503, detail="Response audit unavailable; retry later"
        ) from None
    response.headers["X-Stash-Request-Id"] = str(request_id)
    return response
