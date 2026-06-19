"""Scope router: CRUD for the user's single scope.

(Transitional: still mounted at /api/v1/workspaces and returning the
`workspaces` row; renamed in a later cleanup once the frontend follows.)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..models import (
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from ..services import security_audit_service, storage_service, workspace_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def _workspace_response(workspace: dict) -> WorkspaceResponse:
    data = dict(workspace)
    if settings.AUTH0_ENABLED:
        data["invite_code"] = ""
    return WorkspaceResponse(**data)


async def _serialize_workspace_for_viewer(
    workspace: dict, viewer_id: UUID | None
) -> WorkspaceResponse:
    is_owner = bool(viewer_id and await workspace_service.is_owner(workspace["id"], viewer_id))
    if not is_owner:
        raise HTTPException(status_code=404, detail="Not found")
    return _workspace_response(workspace)


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    req: WorkspaceCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.create_workspace(
        name=req.name,
        description=req.description,
        creator_id=current_user["id"],
    )
    return _workspace_response(ws)


@router.get("/mine", response_model=WorkspaceListResponse)
async def list_my_workspaces(current_user: dict = Depends(get_current_user)):
    workspaces = await workspace_service.list_user_workspaces(current_user["id"])
    return WorkspaceListResponse(workspaces=[_workspace_response(w) for w in workspaces])


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    current_user: dict | None = Depends(get_current_user_optional),
):
    ws = await workspace_service.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Not found")
    viewer_id = current_user["id"] if current_user else None
    return await _serialize_workspace_for_viewer(ws, viewer_id)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    req: WorkspaceUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_owner(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Only the owner can update")
    ws = await workspace_service.update_workspace(
        workspace_id,
        name=req.name,
        description=req.description,
        cover_image_url=req.cover_image_url,
        icon_url=req.icon_url,
        color_gradient=req.color_gradient,
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Not found")
    return _workspace_response(ws)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    storage_keys = await workspace_service.delete_workspace(workspace_id, current_user["id"])
    if storage_keys is None:
        raise HTTPException(status_code=403, detail="Only the owner can delete")

    for storage_key in storage_keys:
        await storage_service.delete_file(storage_key)

    await security_audit_service.record_event(
        action="content.scope_purged",
        actor_user_id=current_user["id"],
        target_type="scope",
        target_id=str(workspace_id),
        metadata={"storage_key_count": len(storage_keys)},
    )
