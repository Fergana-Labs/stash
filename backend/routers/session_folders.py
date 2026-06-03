"""Session-folder endpoints: create, list, and assign sessions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..services import permission_service, session_folder_service

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/session-folders", tags=["session-folders"]
)


async def _require_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await permission_service.is_workspace_member(workspace_id, user_id):
        raise HTTPException(status_code=404, detail="Workspace not found")


class CreateFolderRequest(BaseModel):
    name: str


class AssignRequest(BaseModel):
    session_row_id: UUID
    folder_id: UUID | None = None


@router.post("")
async def create_folder(
    workspace_id: UUID, body: CreateFolderRequest, current_user: dict = Depends(get_current_user)
):
    await _require_member(workspace_id, current_user["id"])
    return await session_folder_service.create_folder(workspace_id, current_user["id"], body.name)


@router.get("")
async def list_folders(workspace_id: UUID, current_user: dict = Depends(get_current_user)):
    return {"folders": await session_folder_service.list_folders(workspace_id, current_user["id"])}


@router.post("/assign")
async def assign_session(
    workspace_id: UUID, body: AssignRequest, current_user: dict = Depends(get_current_user)
):
    await _require_member(workspace_id, current_user["id"])
    await session_folder_service.assign_session(body.session_row_id, body.folder_id)
    return {"ok": True}
