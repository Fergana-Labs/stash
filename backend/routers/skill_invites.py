"""Current-user Skill invite notifications."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import (
    SkillInviteListResponse,
    SkillInviteResponse,
)
from ..services import skill_invite_service

router = APIRouter(prefix="/api/v1/skill-invites", tags=["skill-invites"])


@router.get("", response_model=SkillInviteListResponse)
async def list_skill_invites(current_user: dict = Depends(get_current_user)):
    invites = await skill_invite_service.list_pending_invites(current_user["id"])
    return SkillInviteListResponse(invites=[SkillInviteResponse(**invite) for invite in invites])


@router.post("/{invite_id}/dismiss", status_code=204)
async def dismiss_skill_invite(
    invite_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    dismissed = await skill_invite_service.dismiss_invite(invite_id, current_user["id"])
    if not dismissed:
        raise HTTPException(status_code=404, detail="Skill invite not found")
