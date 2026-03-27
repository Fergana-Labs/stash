"""History router: structured agent event storage."""

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
    PermissionResponse,
    SetVisibilityRequest,
    ShareRequest,
    ShareResponse,
)
from ..services import memory_service, permission_service, workspace_service, webhook_service

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/memory", tags=["memory"])


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _check_store_access(workspace_id: UUID, store_id: UUID, user_id: UUID) -> None:
    has_access = await permission_service.check_access(
        "history", store_id, user_id, workspace_id=workspace_id,
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="No access to this history")


# --- Store CRUD ---


@router.post("", response_model=HistoryResponse, status_code=201)
async def create_store(
    workspace_id: UUID, req: HistoryCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    try:
        store = await memory_service.create_store(
            workspace_id, req.name, req.description, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Store name already exists in workspace")
        raise
    return HistoryResponse(**store)


@router.get("", response_model=HistoryListResponse)
async def list_stores(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    stores = await memory_service.list_stores(workspace_id)
    return HistoryListResponse(stores=[HistoryResponse(**s) for s in stores])


@router.get("/{store_id}", response_model=HistoryResponse)
async def get_store(
    workspace_id: UUID, store_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_store_access(workspace_id, store_id, current_user["id"])
    store = await memory_service.get_store(store_id, workspace_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return HistoryResponse(**store)


@router.delete("/{store_id}", status_code=204)
async def delete_store(
    workspace_id: UUID, store_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can delete stores")
    deleted = await memory_service.delete_store(store_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Store not found")


# --- Events ---


@router.post("/{store_id}/events", response_model=HistoryEventResponse, status_code=201)
async def push_event(
    workspace_id: UUID, store_id: UUID, req: HistoryEventCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_store_access(workspace_id, store_id, current_user["id"])
    event = await memory_service.push_event(
        store_id, agent_name=req.agent_name, event_type=req.event_type,
        content=req.content, session_id=req.session_id,
        tool_name=req.tool_name, metadata=req.metadata,
    )
    # Dispatch webhooks
    import asyncio
    asyncio.create_task(
        webhook_service.dispatch_webhooks(
            workspace_id, "memory.event", event, sender_id=current_user["id"],
        )
    )
    return HistoryEventResponse(**event)


@router.post("/{store_id}/events/batch", response_model=list[HistoryEventResponse], status_code=201)
async def push_events_batch(
    workspace_id: UUID, store_id: UUID, req: HistoryEventBatchRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_store_access(workspace_id, store_id, current_user["id"])
    events_data = [e.model_dump() for e in req.events]
    events = await memory_service.push_events_batch(store_id, events_data)
    return [HistoryEventResponse(**e) for e in events]


@router.get("/{store_id}/events", response_model=HistoryEventListResponse)
async def query_events(
    workspace_id: UUID, store_id: UUID,
    agent_name: str | None = Query(None),
    session_id: str | None = Query(None),
    event_type: str | None = Query(None),
    after: str | None = Query(None),
    before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    await _check_store_access(workspace_id, store_id, current_user["id"])
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
    workspace_id: UUID, store_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    await _check_store_access(workspace_id, store_id, current_user["id"])
    events = await memory_service.search_events(store_id, q, limit=limit)
    return HistoryEventListResponse(
        events=[HistoryEventResponse(**e) for e in events],
        has_more=False,
    )


@router.get("/{store_id}/events/{event_id}", response_model=HistoryEventResponse)
async def get_event(
    workspace_id: UUID, store_id: UUID, event_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_store_access(workspace_id, store_id, current_user["id"])
    event = await memory_service.get_event(event_id, store_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return HistoryEventResponse(**event)


# --- Permissions ---


@router.get("/{store_id}/permissions", response_model=PermissionResponse)
async def get_permissions(
    workspace_id: UUID, store_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    perms = await permission_service.get_permissions("history", store_id)
    return PermissionResponse(**perms)


@router.patch("/{store_id}/permissions")
async def set_visibility(
    workspace_id: UUID, store_id: UUID, req: SetVisibilityRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can change visibility")
    await permission_service.set_visibility("history", store_id, req.visibility)
    return {"status": "ok", "visibility": req.visibility}


@router.post("/{store_id}/permissions/share", response_model=ShareResponse)
async def add_share(
    workspace_id: UUID, store_id: UUID, req: ShareRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can share")
    share = await permission_service.add_share(
        "history", store_id, req.user_id, req.permission, current_user["id"],
    )
    from ..database import get_pool
    pool = get_pool()
    user = await pool.fetchrow("SELECT name FROM users WHERE id = $1", req.user_id)
    return ShareResponse(
        user_id=share["user_id"], user_name=user["name"] if user else "",
        permission=share["permission"], granted_by=share["granted_by"],
        created_at=share["created_at"],
    )


@router.delete("/{store_id}/permissions/share/{user_id}", status_code=204)
async def remove_share(
    workspace_id: UUID, store_id: UUID, user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can remove shares")
    await permission_service.remove_share("history", store_id, user_id)
