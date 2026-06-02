"""Sharing endpoints: grant/revoke/list access to an object.

Primary path: share a folder/file/session with a person by email. Adding an object
to a cartridge (the cartridge-principal share) is handled on the cartridge router.
"""

from __future__ import annotations

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


@router.get("")
async def list_shares(
    object_type: str,
    object_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    return {"shares": await share_service.list_object_shares(object_type, object_id, current_user["id"])}
