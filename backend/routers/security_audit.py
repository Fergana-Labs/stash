"""Workspace security audit log endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..services import security_audit_service, workspace_service

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/security-events",
    tags=["security-audit"],
)


async def _require_workspace_admin(workspace_id: UUID, user_id: UUID) -> None:
    role = await workspace_service.get_member_role(workspace_id, user_id)
    if role not in workspace_service.ROLES_ADMIN:
        raise HTTPException(
            status_code=403, detail="Only workspace admins can read security events"
        )


@router.get("")
async def list_security_events(
    workspace_id: UUID,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    await _require_workspace_admin(workspace_id, current_user["id"])
    events = await security_audit_service.list_workspace_events(
        workspace_id=workspace_id,
        action=action,
        limit=limit,
    )
    return {"events": events}
