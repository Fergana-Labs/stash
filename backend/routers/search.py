"""Search router: universal cross-resource search endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services import universal_search_service, workspace_service

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/search", tags=["search"])
personal_router = APIRouter(prefix="/api/v1/me/search", tags=["personal_search"])


class SearchRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    resource_types: list[str] | None = None  # ["history", "notebook", "table", "document"]


class SearchResponse(BaseModel):
    answer: str
    sources_used: list[str]


@ws_router.post("", response_model=SearchResponse)
async def search_workspace(
    workspace_id: UUID,
    req: SearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """Search across all resources in a workspace: history, notebooks, tables, documents."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    result = await universal_search_service.universal_search(
        question=req.question,
        user_id=current_user["id"],
        workspace_id=workspace_id,
        resource_types=req.resource_types,
    )
    return SearchResponse(**result)


@personal_router.post("", response_model=SearchResponse)
async def search_personal(
    req: SearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """Search across all personal resources: history, notebooks, tables."""
    result = await universal_search_service.universal_search(
        question=req.question,
        user_id=current_user["id"],
        resource_types=req.resource_types,
    )
    return SearchResponse(**result)
