"""Session event router: agent event storage scoped to a user.

Events belong directly to a scope. No intermediate "store" abstraction.
Hierarchy: Scope → Agent → Session → Events
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
from ..services import memory_service, user_scope_service
from ..tasks.session_titles import generate_session_title

me_router = APIRouter(prefix="/api/v1/me/sessions", tags=["sessions"])

_TITLE_EVENT_TYPES = {"user_message", "user_prompt", "prompt", "assistant_message", "session_end"}


# --- Shared auth helpers ---


async def _check_member(owner_user_id: UUID, user_id: UUID) -> None:
    if not await user_scope_service.is_owner(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Not the scope owner")


async def _check_write(owner_user_id: UUID, user_id: UUID) -> None:
    if not await user_scope_service.can_write(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Only the owner can write sessions")


# ===== Scope event endpoints =====


@me_router.post("/events", response_model=HistoryEventResponse, status_code=201)
async def push_event(
    req: HistoryEventCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_write(owner_user_id, current_user["id"])
    attachments = [a.model_dump(mode="json") for a in req.attachments] if req.attachments else None
    event = await memory_service.push_event(
        owner_user_id,
        agent_name=req.agent_name,
        event_type=req.event_type,
        content=req.content,
        created_by=current_user["id"],
        session_id=req.session_id,
        session_folder_id=req.session_folder_id,
        tool_name=req.tool_name,
        metadata=req.metadata,
        attachments=attachments,
        created_at=req.created_at,
    )
    if settings.ANTHROPIC_API_KEY and req.session_id and req.event_type in _TITLE_EVENT_TYPES:
        generate_session_title.delay(str(owner_user_id), req.session_id)
    return HistoryEventResponse(**event)


@me_router.post("/events/batch", response_model=list[HistoryEventResponse], status_code=201)
async def push_events_batch(
    req: HistoryEventBatchRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_write(owner_user_id, current_user["id"])
    events_data = [e.model_dump() for e in req.events]
    events = await memory_service.push_events_batch(owner_user_id, current_user["id"], events_data)
    title_session_ids = sorted(
        {
            event.session_id
            for event in req.events
            if event.session_id and event.event_type in _TITLE_EVENT_TYPES
        }
    )
    if settings.ANTHROPIC_API_KEY:
        for session_id in title_session_ids:
            generate_session_title.delay(str(owner_user_id), session_id)
    return [HistoryEventResponse(**e) for e in events]


@me_router.get("/events", response_model=HistoryEventListResponse)
async def query_events(
    agent_name: str | None = Query(None),
    session_id: str | None = Query(None),
    event_type: str | None = Query(None),
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    events, has_more = await memory_service.query_scope_events(
        owner_user_id,
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


@me_router.get("/events/search", response_model=HistoryEventListResponse)
async def search_events(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    events = await memory_service.search_scope_events(
        owner_user_id,
        current_user["id"],
        q,
        limit=limit,
    )
    return HistoryEventListResponse(
        events=[HistoryEventResponse(**e) for e in events],
        has_more=False,
    )


@me_router.get("/events/{event_id}", response_model=HistoryEventResponse)
async def get_event(
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    event = await memory_service.get_scope_event(event_id, owner_user_id, current_user["id"])
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return HistoryEventResponse(**event)


@me_router.delete("/agents/{agent_name}", status_code=204)
async def delete_agent(
    agent_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete all events for an agent in this scope."""
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    await memory_service.delete_scope_agent_events(agent_name, owner_user_id)


@me_router.get("/agent-names")
async def list_agent_names(
    current_user: dict = Depends(get_current_user),
):
    """List distinct agent names in this scope."""
    owner_user_id = current_user["id"]
    await _check_member(owner_user_id, current_user["id"])
    from ..database import get_pool

    pool = get_pool()
    rows = await pool.fetch(
        "SELECT DISTINCT agent_name FROM history_events "
        "WHERE owner_user_id = $1 "
        f"AND {memory_service.readable_session_event_condition('history_events', 2)} "
        "ORDER BY agent_name",
        owner_user_id,
        current_user["id"],
    )
    return {"agent_names": [r["agent_name"] for r in rows]}
