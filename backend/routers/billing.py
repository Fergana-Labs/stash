"""Billing endpoints: plan status, Stripe Checkout/Portal redirects, and the
Stripe webhook. The webhook is public (Stripe calls it) and verified by
signature, mirroring the Slack webhook pattern in webhooks.py."""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import get_current_user, get_scope
from ..config import settings
from ..services import billing_service, curation_service

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/me")
async def my_billing(
    scope_user_id: UUID = Depends(get_scope),
):
    subscription = await billing_service.get_subscription(scope_user_id)
    status = subscription["status"] if subscription else None
    return {
        "billing_enabled": billing_service.billing_enabled(),
        "plan": await billing_service.plan_label(scope_user_id),
        "status": status,
        "connection_count": await billing_service.connection_count(scope_user_id),
        "connection_limit": billing_service.FREE_CONNECTION_LIMIT,
        "curated_trace_count": await curation_service.account_curated_trace_count(scope_user_id),
        "free_curated_trace_limit": settings.FREE_CURATED_TRACES,
    }


class CheckoutRequest(BaseModel):
    interval: Literal["month", "year"] = "month"


@router.post("/checkout")
async def start_checkout(body: CheckoutRequest, current_user: dict = Depends(get_current_user)):
    billing_service.require_billing_enabled()
    return {"url": await billing_service.create_checkout_session(current_user, body.interval)}


@router.post("/portal")
async def open_portal(current_user: dict = Depends(get_current_user)):
    billing_service.require_billing_enabled()
    return {"url": await billing_service.create_portal_session(current_user["id"])}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    billing_service.require_billing_enabled()
    payload = await request.body()
    # construct_event verifies the signature; we then work with the plain
    # parsed JSON rather than stripe's object wrappers.
    try:
        stripe.Webhook.construct_event(
            payload,
            request.headers.get("stripe-signature", ""),
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="bad signature")
    await billing_service.apply_webhook_event(json.loads(payload))
    return {"ok": True}
