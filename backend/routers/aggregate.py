"""Aggregate router: cross-workspace views for the authenticated user."""

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..services import memory_service, notebook_service, table_service

router = APIRouter(prefix="/api/v1/me", tags=["aggregate"])


@router.get("/notebooks")
async def list_all_notebooks(current_user: dict = Depends(get_current_user)):
    """All notebooks from workspaces + personal."""
    notebooks = await notebook_service.list_all_user_notebooks(current_user["id"])
    return {"notebooks": notebooks}


@router.get("/history")
async def list_all_histories(current_user: dict = Depends(get_current_user)):
    """All historys from workspaces + personal."""
    stores = await memory_service.list_all_user_stores(current_user["id"])
    return {"stores": stores}


@router.get("/history-events")
async def list_all_history_events(
    agent_name: str | None = Query(None),
    event_type: str | None = Query(None),
    after: str | None = Query(None),
    before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Events across all accessible stores with filters."""
    events, has_more = await memory_service.query_all_user_events(
        current_user["id"],
        agent_name=agent_name,
        event_type=event_type,
        after=after,
        before=before,
        limit=limit,
    )
    return {"events": events, "has_more": has_more}


@router.get("/tables")
async def list_all_tables(current_user: dict = Depends(get_current_user)):
    """All tables from workspaces + personal."""
    tables = await table_service.list_all_user_tables(current_user["id"])
    return {"tables": tables}
