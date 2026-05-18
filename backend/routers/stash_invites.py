"""Current-user Stash invite notifications."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import (
    AcceptStashInviteRequest,
    StashInviteListResponse,
    StashInviteResponse,
    StashResponse,
)
from ..services import stash_invite_service

router = APIRouter(prefix="/api/v1/stash-invites", tags=["stash-invites"])


@router.get("", response_model=StashInviteListResponse)
async def list_stash_invites(current_user: dict = Depends(get_current_user)):
    invites = await stash_invite_service.list_pending_invites(current_user["id"])
    return StashInviteListResponse(invites=[StashInviteResponse(**invite) for invite in invites])


@router.post("/{invite_id}/accept", response_model=StashResponse)
async def accept_stash_invite(
    invite_id: UUID,
    req: AcceptStashInviteRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        stash = await stash_invite_service.accept_invite(
            invite_id,
            current_user["id"],
            req.workspace_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not stash:
        raise HTTPException(status_code=404, detail="Stash invite not found")
    return StashResponse(**stash)


@router.post("/{invite_id}/dismiss", status_code=204)
async def dismiss_stash_invite(
    invite_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    dismissed = await stash_invite_service.dismiss_invite(invite_id, current_user["id"])
    if not dismissed:
        raise HTTPException(status_code=404, detail="Stash invite not found")
