"""Session event router: workspace agent event storage.

Events belong directly to workspaces. No intermediate "store" abstraction.
Hierarchy: Workspace → Agent → Session → Events
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..config import settings
from ..models import (
    HistoryEventBatchRequest,
    HistoryEventCreateRequest,
    HistoryEventListResponse,
    HistoryEventResponse,
)
from ..services import cartridge_service, memory_service, workspace_service
from ..tasks.session_titles import generate_session_title

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/sessions", tags=["sessions"])

_TITLE_EVENT_TYPES = {"user_message", "user_prompt", "prompt", "assistant_message", "session_end"}


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
        agent_name=req.agent_name,
        event_type=req.event_type,
        content=req.content,
        created_by=current_user["id"],
        session_id=req.session_id,
        tool_name=req.tool_name,
        metadata=req.metadata,
        attachments=attachments,
        created_at=req.created_at,
    )
    if req.default_cartridge_id and req.session_id:
        try:
            await cartridge_service.add_sessions_to_cartridge(
                cartridge_id=req.default_cartridge_id,
                workspace_id=workspace_id,
                user_id=current_user["id"],
                session_ids=[req.session_id],
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if settings.ANTHROPIC_API_KEY and req.session_id and req.event_type in _TITLE_EVENT_TYPES:
        generate_session_title.delay(str(workspace_id), req.session_id)
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
    if req.default_cartridge_id:
        session_ids = sorted({event.session_id for event in req.events if event.session_id})
        try:
            await cartridge_service.add_sessions_to_cartridge(
                cartridge_id=req.default_cartridge_id,
                workspace_id=workspace_id,
                user_id=current_user["id"],
                session_ids=session_ids,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    title_session_ids = sorted(
        {
            event.session_id
            for event in req.events
            if event.session_id and event.event_type in _TITLE_EVENT_TYPES
        }
    )
    if settings.ANTHROPIC_API_KEY:
        for session_id in title_session_ids:
            generate_session_title.delay(str(workspace_id), session_id)
    return [HistoryEventResponse(**e) for e in events]


@ws_router.get("/events", response_model=HistoryEventListResponse)
async def query_ws_events(
    workspace_id: UUID,
    agent_name: str | None = Query(None),
    session_id: str | None = Query(None),
    event_type: str | None = Query(None),
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    events, has_more = await memory_service.query_workspace_events(
        workspace_id,
        current_user["id"],
        agent_name=agent_name,
        session_id=session_id,
        event_type=event_type,
        after=after,
        before=before,
        limit=limit,
        order=order,
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
    events = await memory_service.search_workspace_events(
        workspace_id,
        current_user["id"],
        q,
        limit=limit,
    )
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
    event = await memory_service.get_workspace_event(event_id, workspace_id, current_user["id"])
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return HistoryEventResponse(**event)


@ws_router.delete("/agents/{agent_name}", status_code=204)
async def delete_ws_agent(
    workspace_id: UUID,
    agent_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete all events for an agent in this workspace."""
    await _check_member(workspace_id, current_user["id"])
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Workspace admin required")
    await memory_service.delete_workspace_agent_events(agent_name, workspace_id)


@ws_router.get("/agent-names")
async def list_ws_agent_names(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """List distinct agent names in this workspace."""
    await _check_member(workspace_id, current_user["id"])
    from ..database import get_pool

    pool = get_pool()
    rows = await pool.fetch(
        "SELECT DISTINCT agent_name FROM history_events "
        "WHERE workspace_id = $1 "
        f"AND {memory_service.readable_session_event_condition('history_events', 2)} "
        "ORDER BY agent_name",
        workspace_id,
        current_user["id"],
    )
    return {"agent_names": [r["agent_name"] for r in rows]}
