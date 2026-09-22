"""Billing endpoints: plan status, Stripe Checkout/Portal redirects, and the
Stripe webhook. The webhook is public (Stripe calls it) and verified by
signature, mirroring the Slack webhook pattern in webhooks.py."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth import get_current_user, get_scope
from ..config import settings
from ..services import billing_service, transcript_usage_service

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/me")
async def my_billing(
    scope_user_id: UUID = Depends(get_scope),
):
    subscription = await billing_service.get_subscription(scope_user_id)
    status = subscription["status"] if subscription else None
    allowance = await transcript_usage_service.allowance(scope_user_id, datetime.now(UTC))
    return {
        "billing_enabled": billing_service.billing_enabled(),
        "plan": await billing_service.plan_label(scope_user_id),
        "status": status,
        "connection_count": await billing_service.connection_count(scope_user_id),
        "connection_limit": billing_service.FREE_CONNECTION_LIMIT,
        "transcript_tokens": allowance["used"],
        "included_tokens": allowance["included"],
        "remaining_tokens": allowance["remaining"],
        "resets_at": allowance["resets_at"],
        "overage_cents": allowance["overage_cents"],
        "overage_limit_cents": allowance["overage_limit_cents"],
        "overages_enabled": allowance["overages_enabled"],
        "overage_cents_per_million": transcript_usage_service.OVERAGE_CENTS_PER_MILLION,
        "free_included_tokens": transcript_usage_service.FREE_TOKENS,
        "pro_included_tokens": transcript_usage_service.PRO_TOKENS,
    }


class OverageLimitRequest(BaseModel):
    limit_cents: int = Field(ge=0, le=100_000, strict=True)


@router.put("/overage-limit")
async def set_overage_limit(
    body: OverageLimitRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    if scope_user_id != current_user["id"]:
        raise HTTPException(403, "Manage usage billing from your personal account.")
    await billing_service.set_overage_limit(current_user["id"], body.limit_cents)
    return await my_billing(scope_user_id)


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
