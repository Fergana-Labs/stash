"""Cartridges: publishable subsets of a workspace."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..models import (
    AddExternalCartridgeRequest,
    CartridgeCreateRequest,
    CartridgePublicResponse,
    CartridgeResponse,
    CartridgeUpdateRequest,
    PageCreateRequest,
    PageResponse,
)
from ..services import cartridge_service, permission_service, workspace_service

ws_router = APIRouter(prefix="/api/v1/workspaces", tags=["cartridges"])
public_router = APIRouter(prefix="/api/v1/cartridges", tags=["cartridges"])

_STASH_ITEM_TYPES = {"folder", "page", "table", "file", "session"}


async def _require_can_share_item(workspace_id: UUID, item, user_id: UUID) -> None:
    item_workspace_id = await permission_service.resolve_workspace_id(
        item.object_type, item.object_id
    )
    if item_workspace_id != workspace_id:
        raise HTTPException(status_code=400, detail="Stash items must be in the workspace")

    can_read = await permission_service.check_access(
        item.object_type,
        item.object_id,
        user_id,
        workspace_id=workspace_id,
    )
    if not can_read:
        raise HTTPException(status_code=403, detail="Not allowed to share one or more items")


@ws_router.post("/{workspace_id}/cartridges", response_model=CartridgeResponse, status_code=201)
async def create_cartridge(
    workspace_id: UUID,
    req: CartridgeCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if req.discoverable and req.public_permission == "none":
        raise HTTPException(status_code=400, detail="Discover Cartridges must be public")
    for item in req.items:
        await _require_can_share_item(workspace_id, item, current_user["id"])
    try:
        stash = await cartridge_service.create_cartridge(
            workspace_id=workspace_id,
            owner_id=current_user["id"],
            title=req.title,
            description=req.description,
            workspace_permission=req.workspace_permission,
            public_permission=req.public_permission,
            discoverable=req.discoverable,
            cover_image_url=req.cover_image_url,
            icon_url=req.icon_url,
            items=req.items,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CartridgeResponse(**stash)


@ws_router.post("/{workspace_id}/cartridges/publish", status_code=201)
async def publish_cartridge(
    workspace_id: UUID,
    req: CartridgeCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a public Stash and return its shareable URL."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not req.items:
        raise HTTPException(status_code=400, detail="A shared bundle needs at least one item")
    if req.public_permission == "none":
        raise HTTPException(status_code=400, detail="Published Cartridges must be public")

    for item in req.items:
        await _require_can_share_item(workspace_id, item, current_user["id"])

    try:
        stash = await cartridge_service.create_cartridge(
            workspace_id=workspace_id,
            owner_id=current_user["id"],
            title=req.title,
            description=req.description,
            workspace_permission=req.workspace_permission,
            public_permission=req.public_permission,
            discoverable=req.discoverable,
            cover_image_url=req.cover_image_url,
            icon_url=req.icon_url,
            items=req.items,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    base = settings.PUBLIC_URL.rstrip("/")
    return {
        "cartridge": CartridgeResponse(**stash),
        "url": f"{base}/cartridges/{stash['slug']}",
        "cartridge_id": stash["id"],
        "cartridge_slug": stash["slug"],
    }


@ws_router.get("/{workspace_id}/cartridges")
async def list_stashes(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    cartridges = await cartridge_service.list_workspace_stashes(workspace_id, current_user["id"])
    return {"cartridges": [CartridgeResponse(**stash) for stash in cartridges]}


@ws_router.delete("/{workspace_id}/external-cartridges/{cartridge_id}", status_code=204)
async def remove_external_cartridge(
    workspace_id: UUID,
    cartridge_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    deleted = await cartridge_service.remove_external_cartridge(
        workspace_id,
        cartridge_id,
        current_user["id"],
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Forked Stash not found")


class SnapshotSourceRequest(BaseModel):
    source_id: UUID
    path: str


@ws_router.post(
    "/{workspace_id}/cartridges/{cartridge_id}/snapshot-source",
    response_model=PageResponse,
    status_code=201,
)
async def snapshot_source(
    workspace_id: UUID,
    cartridge_id: UUID,
    req: SnapshotSourceRequest,
    current_user: dict = Depends(get_current_user),
):
    """Copy a point-in-time snapshot of one connected-source document into the
    cartridge as a page, so the bundle stays self-contained and curl-able."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    try:
        page = await cartridge_service.snapshot_source_into_cartridge(
            cartridge_id, current_user["id"], source_id=req.source_id, path=req.path
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not allowed to edit this cartridge")
    if page is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return PageResponse(**page)


@ws_router.get("/{workspace_id}/cartridges/objects/{object_type}/{object_id}")
async def list_object_stashes(
    workspace_id: UUID,
    object_type: str,
    object_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if object_type not in {"folder", "page", "table", "file", "session"}:
        raise HTTPException(status_code=400, detail="Unsupported Stash item type")
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    item_workspace_id = await permission_service.resolve_workspace_id(object_type, object_id)
    if item_workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Object not found")
    cartridges = await cartridge_service.list_object_stashes(
        workspace_id,
        object_type,
        object_id,
        current_user["id"],
    )
    return {"cartridges": [CartridgeResponse(**stash) for stash in cartridges]}


@public_router.patch("/{cartridge_id}", response_model=CartridgeResponse)
async def update_cartridge(
    cartridge_id: UUID,
    req: CartridgeUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await cartridge_service.user_can_manage(cartridge_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to manage this cartridge")
    try:
        stash = await cartridge_service.update_cartridge(
            cartridge_id,
            current_user["id"],
            req.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    return CartridgeResponse(**stash)


@public_router.delete("/{cartridge_id}", status_code=204)
async def delete_cartridge(
    cartridge_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await cartridge_service.user_can_manage(cartridge_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to manage this cartridge")
    deleted = await cartridge_service.delete_cartridge(cartridge_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Stash not found")


@public_router.post("/{cartridge_id}/shared-pages", response_model=PageResponse, status_code=201)
async def create_shared_cartridge_page(
    cartridge_id: UUID,
    req: PageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        page = await cartridge_service.create_shared_page(
            cartridge_id,
            current_user["id"],
            name=req.name,
            content=req.content,
            content_type=req.content_type,
            content_html=req.content_html,
            html_layout=req.html_layout,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not page:
        raise HTTPException(status_code=404, detail="Stash not found")
    return PageResponse(**page)


@public_router.get("/{slug}")
async def get_public_cartridge(
    slug: str,
    format: str = Query(None, alias="format"),
    current_user: dict | None = Depends(get_current_user_optional),
):
    viewer_id = current_user["id"] if current_user else None
    stash = await cartridge_service.get_public_cartridge(slug, viewer_id=viewer_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    items = await cartridge_service.inline_items(stash, viewer_id=viewer_id)

    if format == "text":
        return PlainTextResponse(
            cartridge_service.stash_to_text(
                stash,
                stash.get("_workspace_name", ""),
                items,
                settings.PUBLIC_URL.rstrip(),
            ),
            media_type="text/markdown",
        )

    workspace_name = stash.pop("_workspace_name", "")
    can_write = bool(
        current_user and await cartridge_service.user_can_write(stash["id"], current_user["id"])
    )
    return CartridgePublicResponse(
        cartridge=CartridgeResponse(**stash),
        workspace_name=workspace_name,
        items=items,
        can_write=can_write,
    )


@public_router.get("/{slug}/items/{object_type}/{object_id}")
async def get_public_cartridge_item(
    slug: str,
    object_type: str,
    object_id: UUID,
    format: str = Query(None, alias="format"),
    current_user: dict | None = Depends(get_current_user_optional),
):
    if object_type not in _STASH_ITEM_TYPES:
        raise HTTPException(status_code=404, detail="Stash item not found")

    viewer_id = current_user["id"] if current_user else None
    stash = await cartridge_service.get_public_cartridge(slug, viewer_id=viewer_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    items = await cartridge_service.inline_items(stash, viewer_id=viewer_id)
    item = next(
        (
            candidate
            for candidate in items
            if candidate["object_type"] == object_type
            and str(candidate["object_id"]) == str(object_id)
        ),
        None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Stash item not found")

    if format == "text":
        return PlainTextResponse(
            cartridge_service.item_to_text(stash, item, settings.PUBLIC_URL.rstrip()),
            media_type="text/markdown",
        )

    workspace_name = stash.pop("_workspace_name", "")
    can_write = bool(
        current_user and await cartridge_service.user_can_write(stash["id"], current_user["id"])
    )
    return {
        "cartridge": CartridgeResponse(**stash),
        "workspace_name": workspace_name,
        "item": item,
        "can_write": can_write,
    }


@public_router.post("/{slug}/add-to-workspace", response_model=CartridgeResponse, status_code=201)
async def add_cartridge_to_workspace(
    slug: str,
    req: AddExternalCartridgeRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(req.workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    stash = await cartridge_service.add_external_cartridge(
        req.workspace_id, slug, current_user["id"]
    )
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    return CartridgeResponse(**stash)
