"""Current-user Stash invite notifications."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import (
    CartridgeInviteListResponse,
    CartridgeInviteResponse,
)
from ..services import cartridge_invite_service

router = APIRouter(prefix="/api/v1/cartridge-invites", tags=["cartridge-invites"])


@router.get("", response_model=CartridgeInviteListResponse)
async def list_cartridge_invites(current_user: dict = Depends(get_current_user)):
    invites = await cartridge_invite_service.list_pending_invites(current_user["id"])
    return CartridgeInviteListResponse(
        invites=[CartridgeInviteResponse(**invite) for invite in invites]
    )


@router.post("/{invite_id}/dismiss", status_code=204)
async def dismiss_cartridge_invite(
    invite_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    dismissed = await cartridge_invite_service.dismiss_invite(invite_id, current_user["id"])
    if not dismissed:
        raise HTTPException(status_code=404, detail="Stash invite not found")
