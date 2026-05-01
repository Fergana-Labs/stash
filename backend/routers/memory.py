"""History router: workspace and personal event storage.

Events belong directly to workspaces. No intermediate "store" abstraction.
Hierarchy: Workspace → Tag → Session → Events
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..models import (
    HistoryEventBatchRequest,
    HistoryEventCreateRequest,
    HistoryEventListResponse,
    HistoryEventResponse,
)
from ..services import memory_service, workspace_service

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/memory", tags=["memory"])


# --- Shared auth helpers ---


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


# ===== Workspace event endpoints =====


@ws_router.post("/events", response_model=HistoryEventResponse, status_code=201)
async def push_ws_event(
    workspace_id: UUID,
    req: HistoryEventCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    attachments = [a.model_dump(mode="json") for a in req.attachments] if req.attachments else None
    event = await memory_service.push_event(
        workspace_id,
        tag_name=req.tag_name,
        event_type=req.event_type,
        content=req.content,
        created_by=current_user["id"],
        session_id=req.session_id,
        tool_name=req.tool_name,
        metadata=req.metadata,
        attachments=attachments,
        created_at=req.created_at,
    )
    return HistoryEventResponse(**event)


@ws_router.post("/events/batch", response_model=list[HistoryEventResponse], status_code=201)
async def push_ws_events_batch(
    workspace_id: UUID,
    req: HistoryEventBatchRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    events_data = [e.model_dump() for e in req.events]
    events = await memory_service.push_events_batch(workspace_id, current_user["id"], events_data)
    return [HistoryEventResponse(**e) for e in events]


@ws_router.get("/events", response_model=HistoryEventListResponse)
async def query_ws_events(
    workspace_id: UUID,
    tag_name: str | None = Query(None),
    session_id: str | None = Query(None),
    event_type: str | None = Query(None),
    after: str | None = Query(None),
    before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    events, has_more = await memory_service.query_workspace_events(
        workspace_id,
        tag_name=tag_name,
        session_id=session_id,
        event_type=event_type,
        after=after,
        before=before,
        limit=limit,
    )
    return HistoryEventListResponse(
        events=[HistoryEventResponse(**e) for e in events],
        has_more=has_more,
    )


@ws_router.get("/events/search", response_model=HistoryEventListResponse)
async def search_ws_events(
    workspace_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    events = await memory_service.search_workspace_events(workspace_id, q, limit=limit)
    return HistoryEventListResponse(
        events=[HistoryEventResponse(**e) for e in events],
        has_more=False,
    )


@ws_router.get("/events/{event_id}", response_model=HistoryEventResponse)
async def get_ws_event(
    workspace_id: UUID,
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    event = await memory_service.get_workspace_event(event_id, workspace_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return HistoryEventResponse(**event)


@ws_router.delete("/tags/{tag_name}", status_code=204)
async def delete_ws_tag(
    workspace_id: UUID,
    tag_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete all events for a tag in this workspace."""
    await _check_member(workspace_id, current_user["id"])
    await memory_service.delete_workspace_tag_events(tag_name, workspace_id)


@ws_router.get("/tag-names")
async def list_ws_tag_names(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """List distinct tag names in this workspace."""
    await _check_member(workspace_id, current_user["id"])
    from ..database import get_pool

    pool = get_pool()
    rows = await pool.fetch(
        "SELECT DISTINCT tag_name FROM history_events "
        "WHERE workspace_id = $1 ORDER BY tag_name",
        workspace_id,
    )
    return {"tag_names": [r["tag_name"] for r in rows]}
