"""Session-folder endpoints.

Folders are the shareable unit for sessions (same access model as skills).
`me_router` is the authenticated management surface; `public_router` serves a
folder by slug to anyone the access rules allow (including anonymous viewers of
a public folder), rendered by the same session viewer.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, get_current_user_optional
from ..services import session_folder_service, user_scope_service

me_router = APIRouter(
    prefix="/api/v1/me/session-folders", tags=["session-folders"]
)
public_router = APIRouter(prefix="/api/v1/session-folders", tags=["session-folders"])

GeneralPermission = str  # 'none' | 'read' | 'write' (validated in the service)


async def _require_member(owner_user_id: UUID, user_id: UUID) -> None:
    if not await user_scope_service.is_member(owner_user_id, user_id):
        raise HTTPException(status_code=404, detail="Scope not found")


async def _require_write(owner_user_id: UUID, user_id: UUID) -> None:
    if not await user_scope_service.can_write(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Viewers can read but not edit this scope")


class CreateFolderRequest(BaseModel):
    name: str
    public_permission: GeneralPermission = "none"
    discoverable: bool = False


async def _require_owner_for_folder_visibility(
    owner_user_id: UUID,
    user_id: UUID,
    body: CreateFolderRequest,
) -> None:
    """Scope-visible folders are the everyday default any editor may create;
    only publishing a folder beyond the scope is owner-gated."""
    is_public = body.public_permission != "none" or body.discoverable
    if is_public and not await user_scope_service.is_owner(owner_user_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="Only scope owners can create public session folders",
        )


class UpdateFolderRequest(BaseModel):
    name: str | None = None
    public_permission: GeneralPermission | None = None
    discoverable: bool | None = None
    cover_image_url: str | None = None


class AssignRequest(BaseModel):
    session_row_ids: list[UUID]
    folder_id: UUID | None = None


@me_router.post("")
async def create_folder(
    body: CreateFolderRequest, current_user: dict = Depends(get_current_user)
):
    owner_user_id = current_user["id"]
    await _require_member(owner_user_id, current_user["id"])
    await _require_write(owner_user_id, current_user["id"])
    await _require_owner_for_folder_visibility(owner_user_id, current_user["id"], body)
    try:
        return await session_folder_service.create_folder(
            owner_user_id,
            body.name,
            public_permission=body.public_permission,
            discoverable=body.discoverable,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@me_router.get("")
async def list_folders(current_user: dict = Depends(get_current_user)):
    owner_user_id = current_user["id"]
    # Non-members may still see folders shared with them, so this isn't gated on
    # membership. Members get a Default folder lazily ensured on first listing.
    if await user_scope_service.is_member(owner_user_id, current_user["id"]):
        await session_folder_service.ensure_default_folder(owner_user_id)
    return {"folders": await session_folder_service.list_folders(owner_user_id, current_user["id"])}


@me_router.patch("/{folder_id}")
async def update_folder(
    folder_id: UUID,
    body: UpdateFolderRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        folder = await session_folder_service.update_folder(
            folder_id, current_user["id"], body.model_dump(exclude_unset=True)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@me_router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: UUID, current_user: dict = Depends(get_current_user)
):
    deleted = await session_folder_service.delete_folder(folder_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found or can't be deleted")


@me_router.post("/assign")
async def assign_sessions(
    body: AssignRequest, current_user: dict = Depends(get_current_user)
):
    owner_user_id = current_user["id"]
    await _require_member(owner_user_id, current_user["id"])
    await _require_write(owner_user_id, current_user["id"])
    assigned = await session_folder_service.assign_sessions(
        owner_user_id,
        current_user["id"],
        body.session_row_ids,
        body.folder_id,
    )
    if not assigned:
        raise HTTPException(status_code=404, detail="Session or folder not found")
    return {"ok": True, "moved": len(body.session_row_ids)}


@public_router.get("/{slug}")
async def get_public_folder(
    slug: str, current_user: dict | None = Depends(get_current_user_optional)
):
    viewer_id = current_user["id"] if current_user else None
    folder = await session_folder_service.get_public_folder(slug, viewer_id=viewer_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    sessions = await session_folder_service.list_folder_sessions(UUID(folder["id"]))
    return {"folder": folder, "sessions": sessions}
