"""Aggregate router: cross-workspace views for the authenticated user."""

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..services import analytics_service, memory_service, notebook_service, table_service

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


@router.get("/activity-timeline")
async def activity_timeline(
    days: int = Query(30, ge=1, le=90),
    bucket: str = Query("day"),
    current_user: dict = Depends(get_current_user),
):
    """Agent activity bucketed by time for the dashboard timeline."""
    return await analytics_service.get_activity_timeline(
        current_user["id"], days=days, bucket=bucket,
    )


@router.get("/knowledge-density")
async def knowledge_density(
    max_clusters: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Topic clusters for the knowledge density heatmap."""
    return await analytics_service.get_knowledge_density(
        current_user["id"], max_clusters=max_clusters,
    )


@router.get("/embedding-projection")
async def embedding_projection(
    max_points: int = Query(500, ge=1, le=2000),
    source: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """2D UMAP projection of embeddings for the space explorer."""
    return await analytics_service.get_embedding_projection(
        current_user["id"], max_points=max_points, source=source,
    )
