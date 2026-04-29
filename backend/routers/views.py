"""Views router — curated, publishable subsets of a workspace."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import (
    ViewCreateRequest,
    ViewForkRequest,
    ViewListResponse,
    ViewPublicResponse,
    ViewResponse,
    ViewUpdateRequest,
    WorkspaceResponse,
)
from ..services import view_service, workspace_service

ws_router = APIRouter(prefix="/api/v1/workspaces", tags=["views"])
public_router = APIRouter(prefix="/api/v1/views", tags=["views"])


@ws_router.post("/{workspace_id}/views", response_model=ViewResponse, status_code=201)
async def create_view(
    workspace_id: UUID,
    req: ViewCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    view = await view_service.create_view(
        workspace_id=workspace_id,
        owner_id=current_user["id"],
        title=req.title,
        description=req.description,
        is_public=req.is_public,
        cover_image_url=req.cover_image_url,
        items=req.items,
    )
    return ViewResponse(**view)


@ws_router.get("/{workspace_id}/views", response_model=ViewListResponse)
async def list_views(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    views = await view_service.list_workspace_views(workspace_id)
    return ViewListResponse(views=[ViewResponse(**v) for v in views])


@public_router.patch("/{view_id}", response_model=ViewResponse)
async def update_view(
    view_id: UUID,
    req: ViewUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await view_service.user_can_manage(view_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to manage this view")
    view = await view_service.update_view(
        view_id,
        current_user["id"],
        title=req.title,
        description=req.description,
        is_public=req.is_public,
        cover_image_url=req.cover_image_url,
        items=req.items,
    )
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    return ViewResponse(**view)


@public_router.delete("/{view_id}", status_code=204)
async def delete_view(
    view_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await view_service.user_can_manage(view_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to manage this view")
    deleted = await view_service.delete_view(view_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="View not found")


@public_router.get("/{slug}", response_model=ViewPublicResponse)
async def get_public_view(slug: str):
    view = await view_service.get_public_view(slug)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    items = await view_service.inline_items(view)
    workspace_name = view.pop("_workspace_name", "")
    workspace_is_public = view.pop("_workspace_is_public", False)
    return ViewPublicResponse(
        view=ViewResponse(**view),
        workspace_name=workspace_name,
        workspace_is_public=workspace_is_public,
        items=items,
    )


@public_router.post("/{slug}/fork", response_model=WorkspaceResponse, status_code=201)
async def fork_view(
    slug: str,
    req: ViewForkRequest,
    current_user: dict = Depends(get_current_user),
):
    new_ws = await view_service.fork_view(slug, current_user["id"], req.name)
    if not new_ws:
        raise HTTPException(status_code=404, detail="View not found")
    return WorkspaceResponse(**new_ws)
