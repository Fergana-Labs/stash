"""Sharing endpoints: grant/revoke/list access to an object.

Primary path: share a folder/file/session with a person by email. Adding an object
to a cartridge (the cartridge-principal share) is handled on the cartridge router.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import get_current_user
from ..services import share_service

router = APIRouter(prefix="/api/v1/share", tags=["shares"])


class ShareRequest(BaseModel):
    object_type: str
    object_id: UUID
    email: str
    permission: str = "read"
    expires_at: datetime | None = None


class UnshareRequest(BaseModel):
    object_type: str
    object_id: UUID
    principal_type: str
    principal_id: UUID


@router.post("")
async def create_share(req: ShareRequest, current_user: dict = Depends(get_current_user)):
    return await share_service.share_with_user_by_email(
        object_type=req.object_type,
        object_id=req.object_id,
        email=req.email,
        permission=req.permission,
        owner_id=current_user["id"],
        expires_at=req.expires_at,
    )


@router.delete("")
async def delete_share(req: UnshareRequest, current_user: dict = Depends(get_current_user)):
    await share_service.unshare(
        object_type=req.object_type,
        object_id=req.object_id,
        principal_type=req.principal_type,
        principal_id=req.principal_id,
        owner_id=current_user["id"],
    )
    return {"ok": True}


@router.get("/with-me")
async def list_shared_with_me(current_user: dict = Depends(get_current_user)):
    """Everything shared with the current user, across workspaces."""
    return {"items": await share_service.list_shared_with_user(current_user["id"])}


@router.get("/session-folders/{folder_id}/sessions")
async def list_shared_session_folder_sessions(
    folder_id: UUID, current_user: dict = Depends(get_current_user)
):
    """Sessions inside a session-folder shared with the current user."""
    return {
        "sessions": await share_service.list_shared_session_folder_sessions(
            folder_id, current_user["id"]
        )
    }


@router.get("")
async def list_shares(
    object_type: str,
    object_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    return {
        "shares": await share_service.list_object_shares(object_type, object_id, current_user["id"])
    }
