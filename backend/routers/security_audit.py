"""Security audit log endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..services import security_audit_service, user_scope_service

router = APIRouter(
    prefix="/api/v1/me/security-events",
    tags=["security-audit"],
)


@router.get("")
async def list_security_events(
    action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    if not await user_scope_service.is_owner(owner_user_id, current_user["id"]):
        # Match the sibling scope routers: never confirm a scope's
        # existence to non-members.
        raise HTTPException(status_code=404, detail="Scope not found")
    metadata = {
        "action_filter_hash": security_audit_service.hash_value(action),
        "limit": limit,
    }
    await security_audit_service.record_event(
        action="security_audit.read",
        actor_user_id=current_user["id"],
        owner_user_id=owner_user_id,
        target_type="security_audit_log",
        metadata=metadata,
    )
    events = await security_audit_service.list_events(
        owner_user_id=owner_user_id,
        action=action,
        limit=limit,
    )
    return {"events": events}
