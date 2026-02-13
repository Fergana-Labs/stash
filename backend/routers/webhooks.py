from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import WebhookCreateRequest, WebhookResponse, WebhookUpdateRequest
from ..services import webhook_service

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    req: WebhookCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    wh = await webhook_service.create_webhook(
        user_id=current_user["id"], url=req.url, secret=req.secret
    )
    return WebhookResponse(**wh)


@router.get("", response_model=WebhookResponse)
async def get_webhook(current_user: dict = Depends(get_current_user)):
    wh = await webhook_service.get_webhook(current_user["id"])
    if not wh:
        raise HTTPException(status_code=404, detail="No webhook configured")
    return WebhookResponse(**wh)


@router.patch("", response_model=WebhookResponse)
async def update_webhook(
    req: WebhookUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    wh = await webhook_service.update_webhook(
        user_id=current_user["id"],
        url=req.url,
        secret=req.secret,
        is_active=req.is_active,
    )
    if not wh:
        raise HTTPException(status_code=404, detail="No webhook configured")
    return WebhookResponse(**wh)


@router.delete("")
async def delete_webhook(current_user: dict = Depends(get_current_user)):
    deleted = await webhook_service.delete_webhook(current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="No webhook configured")
    return {"ok": True}
