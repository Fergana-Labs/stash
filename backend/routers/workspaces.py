"""Workspace router: CRUD, membership, invite codes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user, get_current_user_optional
from ..models import (
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceMember,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from ..services import workspace_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


async def _serialize_workspace_for_viewer(workspace: dict, viewer_id: UUID | None) -> WorkspaceResponse:
    is_member = bool(viewer_id and await workspace_service.is_member(workspace["id"], viewer_id))
    is_public = bool(workspace.get("is_public"))
    if not is_public and not is_member:
        raise HTTPException(status_code=404, detail="Workspace not found")

    data = dict(workspace)
    if not is_member:
        data["invite_code"] = ""
    return WorkspaceResponse(**data)


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    req: WorkspaceCreateRequest, current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.create_workspace(
        name=req.name, description=req.description,
        creator_id=current_user["id"], is_public=req.is_public,
    )
    return WorkspaceResponse(**ws)


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(current_user: dict | None = Depends(get_current_user_optional)):
    workspaces = await workspace_service.list_public_workspaces()
    viewer_id = current_user["id"] if current_user else None
    serialized = [
        await _serialize_workspace_for_viewer(w, viewer_id)
        for w in workspaces
    ]
    return WorkspaceListResponse(workspaces=serialized)


@router.get("/mine", response_model=WorkspaceListResponse)
async def list_my_workspaces(current_user: dict = Depends(get_current_user)):
    workspaces = await workspace_service.list_user_workspaces(current_user["id"])
    return WorkspaceListResponse(workspaces=[WorkspaceResponse(**w) for w in workspaces])


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID, current_user: dict | None = Depends(get_current_user_optional),
):
    ws = await workspace_service.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    viewer_id = current_user["id"] if current_user else None
    return await _serialize_workspace_for_viewer(ws, viewer_id)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID, req: WorkspaceUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can update workspace")
    ws = await workspace_service.update_workspace(
        workspace_id, name=req.name, description=req.description,
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse(**ws)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    deleted = await workspace_service.delete_workspace(workspace_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=403, detail="Only workspace owner can delete")


@router.post("/join/{invite_code}", response_model=WorkspaceResponse)
async def join_workspace(
    invite_code: str, current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.join_by_invite(invite_code, current_user["id"])
    if not ws:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    return WorkspaceResponse(**ws)


@router.post("/{workspace_id}/leave", status_code=204)
async def leave_workspace(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    left = await workspace_service.leave_workspace(workspace_id, current_user["id"])
    if not left:
        raise HTTPException(status_code=400, detail="Cannot leave (owner cannot leave)")


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMember])
async def get_members(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    members = await workspace_service.get_members(workspace_id)
    return [WorkspaceMember(**m) for m in members]


@router.post("/{workspace_id}/kick/{user_id}", status_code=204)
async def kick_member(
    workspace_id: UUID, user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    kicked = await workspace_service.kick_member(workspace_id, user_id, current_user["id"])
    if not kicked:
        raise HTTPException(status_code=403, detail="Cannot kick this member")
