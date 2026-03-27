"""Personal history router: workspace-less structured agent event storage."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..models import (
    HistoryEventBatchRequest,
    HistoryEventCreateRequest,
    HistoryEventListResponse,
    HistoryEventResponse,
    HistoryCreateRequest,
    HistoryListResponse,
    HistoryResponse,
)
from ..services import memory_service

router = APIRouter(prefix="/api/v1/memory", tags=["personal_memory"])


async def _check_store_owner(store_id: UUID, user_id: UUID) -> None:
    """Verify user owns this personal history."""
    store = await memory_service.get_personal_store(store_id, user_id)
    if not store:
        raise HTTPException(status_code=403, detail="Not the owner of this store")


# --- Store CRUD ---


@router.post("", response_model=HistoryResponse, status_code=201)
async def create_store(
    req: HistoryCreateRequest, current_user: dict = Depends(get_current_user),
):
    try:
        store = await memory_service.create_personal_store(
            req.name, req.description, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Store name already exists")
        raise
    return HistoryResponse(**store)


@router.get("", response_model=HistoryListResponse)
async def list_stores(current_user: dict = Depends(get_current_user)):
    stores = await memory_service.list_personal_stores(current_user["id"])
    return HistoryListResponse(stores=[HistoryResponse(**s) for s in stores])


@router.get("/{store_id}", response_model=HistoryResponse)
async def get_store(
    store_id: UUID, current_user: dict = Depends(get_current_user),
):
    store = await memory_service.get_personal_store(store_id, current_user["id"])
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return HistoryResponse(**store)


@router.delete("/{store_id}", status_code=204)
async def delete_store(
    store_id: UUID, current_user: dict = Depends(get_current_user),
):
    deleted = await memory_service.delete_personal_store(store_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Store not found")


# --- Events ---


@router.post("/{store_id}/events", response_model=HistoryEventResponse, status_code=201)
async def push_event(
    store_id: UUID, req: HistoryEventCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_store_owner(store_id, current_user["id"])
    event = await memory_service.push_event(
        store_id, agent_name=req.agent_name, event_type=req.event_type,
        content=req.content, session_id=req.session_id,
        tool_name=req.tool_name, metadata=req.metadata,
    )
    return HistoryEventResponse(**event)


@router.post("/{store_id}/events/batch", response_model=list[HistoryEventResponse], status_code=201)
async def push_events_batch(
    store_id: UUID, req: HistoryEventBatchRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_store_owner(store_id, current_user["id"])
    events_data = [e.model_dump() for e in req.events]
    events = await memory_service.push_events_batch(store_id, events_data)
    return [HistoryEventResponse(**e) for e in events]


@router.get("/{store_id}/events", response_model=HistoryEventListResponse)
async def query_events(
    store_id: UUID,
    agent_name: str | None = Query(None),
    session_id: str | None = Query(None),
    event_type: str | None = Query(None),
    after: str | None = Query(None),
    before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    await _check_store_owner(store_id, current_user["id"])
    events, has_more = await memory_service.query_events(
        store_id, agent_name=agent_name, session_id=session_id,
        event_type=event_type, after=after, before=before, limit=limit,
    )
    return HistoryEventListResponse(
        events=[HistoryEventResponse(**e) for e in events],
        has_more=has_more,
    )


@router.get("/{store_id}/events/search", response_model=HistoryEventListResponse)
async def search_events(
    store_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    await _check_store_owner(store_id, current_user["id"])
    events = await memory_service.search_events(store_id, q, limit=limit)
    return HistoryEventListResponse(
        events=[HistoryEventResponse(**e) for e in events],
        has_more=False,
    )


@router.get("/{store_id}/events/{event_id}", response_model=HistoryEventResponse)
async def get_event(
    store_id: UUID, event_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_store_owner(store_id, current_user["id"])
    event = await memory_service.get_event(event_id, store_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return HistoryEventResponse(**event)
