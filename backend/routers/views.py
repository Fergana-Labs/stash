"""Views router — curated, publishable subsets of a workspace."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..models import (
    ViewCreateRequest,
    ViewForkRequest,
    ViewListResponse,
    ViewPublicResponse,
    ViewResponse,
    ViewUpdateRequest,
    WorkspaceResponse,
)
from ..services import permission_service, view_service, workspace_service

ws_router = APIRouter(prefix="/api/v1/workspaces", tags=["views"])
public_router = APIRouter(prefix="/api/v1/views", tags=["views"])

_VISIBILITY_RANK = {"private": 0, "inherit": 0, "link": 1, "public": 2}


async def _require_can_share_item(workspace_id: UUID, item, user_id: UUID) -> None:
    item_workspace_id = await permission_service.resolve_workspace_id(
        item.object_type, item.object_id
    )
    if item_workspace_id != workspace_id:
        raise HTTPException(status_code=400, detail="View items must be in the workspace")

    can_read = await permission_service.check_access(
        item.object_type,
        item.object_id,
        user_id,
        workspace_id=workspace_id,
        require_write=False,
    )
    if not can_read:
        raise HTTPException(status_code=403, detail="Not allowed to share one or more items")


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


@ws_router.post("/{workspace_id}/views/share-bundle", status_code=201)
async def create_shared_view(
    workspace_id: UUID,
    req: ViewCreateRequest,
    ensure: str = Query("link", pattern=r"^(link|public)$"),
    current_user: dict = Depends(get_current_user),
):
    """Create a View and make every underlying item readable at the requested level.

    Views are presentation-only for reader access, so bundle sharing must
    mutate the underlying items rather than the View object's ACL.
    """
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not req.items:
        raise HTTPException(status_code=400, detail="A shared bundle needs at least one item")

    for item in req.items:
        await _require_can_share_item(workspace_id, item, current_user["id"])

    for item in req.items:
        current_vis = await permission_service.get_visibility(item.object_type, item.object_id)
        if _VISIBILITY_RANK.get(current_vis, 0) < _VISIBILITY_RANK[ensure]:
            await permission_service.set_visibility(item.object_type, item.object_id, ensure)

    view = await view_service.create_view(
        workspace_id=workspace_id,
        owner_id=current_user["id"],
        title=req.title,
        description=req.description,
        is_public=ensure == "public",
        cover_image_url=req.cover_image_url,
        items=req.items,
    )
    base = settings.PUBLIC_URL.rstrip("/")
    return {
        "view": ViewResponse(**view),
        "url": f"{base}/v/{view['slug']}",
        "view_id": view["id"],
        "view_slug": view["slug"],
    }


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


@public_router.get("/{slug}")
async def get_public_view(
    slug: str,
    format: str = Query(None, alias="format"),
    current_user: dict | None = Depends(get_current_user_optional),
):
    viewer_id = current_user["id"] if current_user else None
    view = await view_service.get_public_view(slug, viewer_id=viewer_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    items = await view_service.inline_items(view, viewer_id=viewer_id)

    if format == "text":
        return PlainTextResponse(
            view_service.items_to_text(view["title"], items),
            media_type="text/markdown",
        )

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
