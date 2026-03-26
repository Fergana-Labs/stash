"""Webhook router: per-workspace webhooks with event filtering."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import WebhookCreateRequest, WebhookResponse, WebhookUpdateRequest
from ..services import webhook_service, workspace_service

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    workspace_id: UUID, req: WebhookCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    wh = await webhook_service.create_webhook(
        workspace_id=workspace_id, user_id=current_user["id"],
        url=req.url, secret=req.secret, event_filter=req.event_filter,
    )
    return WebhookResponse(**wh)


@router.get("", response_model=WebhookResponse)
async def get_webhook(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    wh = await webhook_service.get_webhook(workspace_id, current_user["id"])
    if not wh:
        raise HTTPException(status_code=404, detail="No webhook configured")
    return WebhookResponse(**wh)


@router.patch("", response_model=WebhookResponse)
async def update_webhook(
    workspace_id: UUID, req: WebhookUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    wh = await webhook_service.update_webhook(
        workspace_id=workspace_id, user_id=current_user["id"],
        url=req.url, secret=req.secret,
        event_filter=req.event_filter, is_active=req.is_active,
    )
    if not wh:
        raise HTTPException(status_code=404, detail="No webhook configured")
    return WebhookResponse(**wh)


@router.delete("", status_code=204)
async def delete_webhook(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    deleted = await webhook_service.delete_webhook(workspace_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="No webhook configured")
