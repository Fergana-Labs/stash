"""Stashes: publishable subsets of a workspace."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..database import get_pool
from ..models import (
    AddExternalStashRequest,
    PageCreateRequest,
    PageResponse,
    StashCreateRequest,
    StashMemberRequest,
    StashMemberResponse,
    StashMembersResponse,
    StashPublicResponse,
    StashResponse,
    StashUpdateRequest,
)
from ..services import permission_service, stash_service, workspace_service

ws_router = APIRouter(prefix="/api/v1/workspaces", tags=["stashes"])
public_router = APIRouter(prefix="/api/v1/stashes", tags=["stashes"])

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
        require_write=False,
    )
    if not can_read:
        raise HTTPException(status_code=403, detail="Not allowed to share one or more items")


@ws_router.post("/{workspace_id}/stashes", response_model=StashResponse, status_code=201)
async def create_stash(
    workspace_id: UUID,
    req: StashCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if req.discoverable and req.public_permission == "none":
        raise HTTPException(status_code=400, detail="Discover Stashes must be public")
    for item in req.items:
        await _require_can_share_item(workspace_id, item, current_user["id"])
    try:
        stash = await stash_service.create_stash(
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
    return StashResponse(**stash)


@ws_router.post("/{workspace_id}/stashes/publish", status_code=201)
async def publish_stash(
    workspace_id: UUID,
    req: StashCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a public Stash and return its shareable URL."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not req.items:
        raise HTTPException(status_code=400, detail="A shared bundle needs at least one item")
    if req.public_permission == "none":
        raise HTTPException(status_code=400, detail="Published Stashes must be public")

    for item in req.items:
        await _require_can_share_item(workspace_id, item, current_user["id"])

    try:
        stash = await stash_service.create_stash(
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
        "stash": StashResponse(**stash),
        "url": f"{base}/stashes/{stash['slug']}",
        "stash_id": stash["id"],
        "stash_slug": stash["slug"],
    }


@ws_router.get("/{workspace_id}/stashes")
async def list_stashes(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    stashes = await stash_service.list_workspace_stashes(workspace_id, current_user["id"])
    return {"stashes": [StashResponse(**stash) for stash in stashes]}


@ws_router.delete("/{workspace_id}/external-stashes/{stash_id}", status_code=204)
async def remove_external_stash(
    workspace_id: UUID,
    stash_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    deleted = await stash_service.remove_external_stash(
        workspace_id,
        stash_id,
        current_user["id"],
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Forked Stash not found")


@ws_router.get("/{workspace_id}/stashes/objects/{object_type}/{object_id}")
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
    stashes = await stash_service.list_object_stashes(
        workspace_id,
        object_type,
        object_id,
        current_user["id"],
    )
    return {"stashes": [StashResponse(**stash) for stash in stashes]}


@public_router.patch("/{stash_id}", response_model=StashResponse)
async def update_stash(
    stash_id: UUID,
    req: StashUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await stash_service.user_can_manage(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to manage this stash")
    try:
        stash = await stash_service.update_stash(
            stash_id,
            current_user["id"],
            req.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    return StashResponse(**stash)


@public_router.delete("/{stash_id}", status_code=204)
async def delete_stash(
    stash_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await stash_service.user_can_manage(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to manage this stash")
    deleted = await stash_service.delete_stash(stash_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Stash not found")


async def _require_can_manage_stash(stash_id: UUID, user_id: UUID) -> None:
    stash = await stash_service.get_stash(stash_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    if not await stash_service.user_can_admin(stash_id, user_id):
        raise HTTPException(status_code=403, detail="Not allowed to manage this stash")


@public_router.get("/{stash_id}/members", response_model=StashMembersResponse)
async def list_stash_members(
    stash_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _require_can_manage_stash(stash_id, current_user["id"])
    members = await stash_service.list_members(stash_id)
    return StashMembersResponse(members=[StashMemberResponse(**member) for member in members])


@public_router.post("/{stash_id}/members", response_model=StashMemberResponse, status_code=201)
async def add_stash_member(
    stash_id: UUID,
    req: StashMemberRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_can_manage_stash(stash_id, current_user["id"])

    pool = get_pool()
    user = await pool.fetchrow("SELECT id FROM users WHERE id = $1", req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        member = await stash_service.add_member(
            stash_id,
            req.user_id,
            req.permission,
            current_user["id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not member:
        raise HTTPException(status_code=404, detail="Stash not found")
    return StashMemberResponse(**member)


@public_router.delete("/{stash_id}/members/{user_id}", status_code=204)
async def remove_stash_member(
    stash_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _require_can_manage_stash(stash_id, current_user["id"])
    await stash_service.remove_member(stash_id, user_id)


@public_router.post("/{stash_id}/shared-pages", response_model=PageResponse, status_code=201)
async def create_shared_stash_page(
    stash_id: UUID,
    req: PageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        page = await stash_service.create_shared_page(
            stash_id,
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
async def get_public_stash(
    slug: str,
    format: str = Query(None, alias="format"),
    current_user: dict | None = Depends(get_current_user_optional),
):
    viewer_id = current_user["id"] if current_user else None
    stash = await stash_service.get_public_stash(slug, viewer_id=viewer_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    items = await stash_service.inline_items(stash, viewer_id=viewer_id)

    if format == "text":
        return PlainTextResponse(
            stash_service.stash_to_text(
                stash,
                stash.get("_workspace_name", ""),
                items,
                settings.PUBLIC_URL.rstrip(),
            ),
            media_type="text/markdown",
        )

    workspace_name = stash.pop("_workspace_name", "")
    can_write = bool(
        current_user and await stash_service.user_can_write(stash["id"], current_user["id"])
    )
    return StashPublicResponse(
        stash=StashResponse(**stash),
        workspace_name=workspace_name,
        items=items,
        can_write=can_write,
    )


@public_router.get("/{slug}/items/{object_type}/{object_id}")
async def get_public_stash_item(
    slug: str,
    object_type: str,
    object_id: UUID,
    format: str = Query(None, alias="format"),
    current_user: dict | None = Depends(get_current_user_optional),
):
    if object_type not in _STASH_ITEM_TYPES:
        raise HTTPException(status_code=404, detail="Stash item not found")

    viewer_id = current_user["id"] if current_user else None
    stash = await stash_service.get_public_stash(slug, viewer_id=viewer_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    items = await stash_service.inline_items(stash, viewer_id=viewer_id)
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
            stash_service.item_to_text(stash, item, settings.PUBLIC_URL.rstrip()),
            media_type="text/markdown",
        )

    workspace_name = stash.pop("_workspace_name", "")
    can_write = bool(
        current_user and await stash_service.user_can_write(stash["id"], current_user["id"])
    )
    return {
        "stash": StashResponse(**stash),
        "workspace_name": workspace_name,
        "item": item,
        "can_write": can_write,
    }


@public_router.post("/{slug}/add-to-workspace", response_model=StashResponse, status_code=201)
async def add_stash_to_workspace(
    slug: str,
    req: AddExternalStashRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(req.workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    stash = await stash_service.add_external_stash(req.workspace_id, slug, current_user["id"])
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    return StashResponse(**stash)
