"""Per-user Stripe subscriptions and opt-in transcript-token overages.

Billing is switched on by STRIPE_SECRET_KEY being set (managed deployment).
Self-hosted instances leave it unset: billing endpoints 404 and the source
pay gate is a no-op. Source limits apply at connect time; existing connections
keep syncing after a subscription lapses. Transcript usage is recorded after
successful curation, with paid overages enabled only by explicit subscriber consent.

The user ↔ Stripe customer mapping row is created when checkout starts, so
every later webhook resolves by stripe_customer_id regardless of event order.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

import stripe
from fastapi import HTTPException

from ..config import settings
from ..database import get_pool

# Stripe statuses that grant Pro. Everything else (past_due, canceled,
# unpaid, incomplete) means free-tier enforcement.
ACTIVE_STATUSES = {"active", "trialing"}
FREE_CONNECTION_LIMIT = 2

# Internal team accounts get Pro without a subscription — no card, no Stripe row.
INTERNAL_EMAIL_DOMAINS = {"ferganalabs.com", "joinstash.ai"}


def is_internal_email(email: str | None) -> bool:
    if not settings.INTERNAL_DOMAINS_FREE_PRO:
        return False
    return bool(email) and email.rsplit("@", 1)[-1].lower() in INTERNAL_EMAIL_DOMAINS


def billing_enabled() -> bool:
    return settings.STRIPE_SECRET_KEY is not None


def require_billing_enabled() -> None:
    if not billing_enabled():
        raise HTTPException(status_code=404, detail="Billing is not enabled on this instance")


async def get_subscription(user_id: UUID) -> dict | None:
    row = await get_pool().fetchrow("SELECT * FROM user_subscriptions WHERE user_id = $1", user_id)
    return dict(row) if row else None


def plan_from_account(account) -> str:
    if account["plan"] == "enterprise":
        return "enterprise"
    if is_internal_email(account["email"]) or account["status"] in ACTIVE_STATUSES:
        return "pro"
    return "free"


async def plan_label(user_id: UUID) -> str:
    """The plan the UI names: 'enterprise' (granted by an admin or a redeemed
    code — no Stripe row), 'pro' (paid or internal), else 'free'. Gates use
    `is_pro`; this exists so a granted account isn't rendered as a $20
    subscription it doesn't have."""
    row = await get_pool().fetchrow(
        "SELECT u.email, u.plan, s.status FROM users u "
        "LEFT JOIN user_subscriptions s ON s.user_id = u.id "
        "WHERE u.id = $1",
        user_id,
    )
    if row is None:
        return "free"
    return plan_from_account(row)


async def is_pro(user_id: UUID) -> bool:
    return await plan_label(user_id) in {"pro", "enterprise"}


# Providers that don't count against the free limit. X is a social-saves
# source (like Instagram, which has no OAuth row at all) — connecting it is
# part of the commonplace-book feature, not a "data integration" seat.
UNMETERED_PROVIDERS = ("x",)


async def connection_count(user_id: UUID) -> int:
    """How many metered integration accounts the user has connected. Each
    account row counts on its own, so two Gmail mailboxes are two connections;
    UNMETERED_PROVIDERS (X) are excluded."""
    return await get_pool().fetchval(
        "SELECT count(*) FROM user_integrations WHERE user_id = $1 AND provider != ALL($2)",
        user_id,
        list(UNMETERED_PROVIDERS),
    )


async def ensure_can_connect(user_id: UUID) -> None:
    """Connect-time pay gate. The free plan includes a handful of connected
    accounts (FREE_CONNECTION_LIMIT); beyond that requires Pro. Sources added
    under a connection are unlimited, and extension-fed sources (X, Instagram)
    aren't accounts so they never count against this."""
    if not billing_enabled():
        return
    if await is_pro(user_id):
        return
    if await connection_count(user_id) >= FREE_CONNECTION_LIMIT:
        raise HTTPException(
            status_code=402,
            detail=(
                f"The free plan includes {FREE_CONNECTION_LIMIT} connected accounts. "
                "Upgrade to Pro to connect more."
            ),
        )


async def _get_or_create_customer_id(user: dict) -> str:
    existing = await get_pool().fetchval(
        "SELECT stripe_customer_id FROM user_subscriptions WHERE user_id = $1", user["id"]
    )
    if existing:
        return existing

    kwargs: dict = {"metadata": {"user_id": str(user["id"])}}
    if user.get("email"):
        kwargs["email"] = user["email"]
    customer = await asyncio.to_thread(
        stripe.Customer.create, api_key=settings.STRIPE_SECRET_KEY, **kwargs
    )
    await get_pool().execute(
        "INSERT INTO user_subscriptions (user_id, stripe_customer_id) VALUES ($1, $2)",
        user["id"],
        customer.id,
    )
    return customer.id


async def create_checkout_session(user: dict, interval: str) -> str:
    customer_id = await _get_or_create_customer_id(user)
    price_id = (
        settings.STRIPE_MONTHLY_PRICE_ID if interval == "month" else settings.STRIPE_ANNUAL_PRICE_ID
    )
    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        api_key=settings.STRIPE_SECRET_KEY,
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(user["id"]),
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.PUBLIC_URL}/settings?billing=success",
        cancel_url=f"{settings.PUBLIC_URL}/settings",
    )
    return session.url


async def create_portal_session(user_id: UUID) -> str:
    customer_id = await get_pool().fetchval(
        "SELECT stripe_customer_id FROM user_subscriptions WHERE user_id = $1", user_id
    )
    if not customer_id:
        raise HTTPException(status_code=400, detail="No subscription to manage")
    session = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        api_key=settings.STRIPE_SECRET_KEY,
        customer=customer_id,
        return_url=f"{settings.PUBLIC_URL}/settings",
    )
    return session.url


async def set_overage_limit(user_id: UUID, cents: int) -> None:
    """Consent is local and explicit; attaching a meter never enables spending by itself."""
    from .transcript_usage_service import METER_EVENT_NAME, OVERAGE_CENTS_PER_MILLION

    require_billing_enabled()
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.fetchval("SELECT id FROM users WHERE id=$1 FOR UPDATE", user_id)
        sub = await conn.fetchrow("SELECT * FROM user_subscriptions WHERE user_id=$1", user_id)
        if sub is None or sub["status"] != "active" or not sub["stripe_subscription_id"]:
            raise HTTPException(400, "An active paid Pro subscription is required for overages.")
        item_id = sub["usage_item_id"]
        if cents > 0:
            if settings.STRIPE_TOKEN_PRICE_ID is None:
                raise HTTPException(503, "Transcript usage billing has not been configured.")
            price = await asyncio.to_thread(
                stripe.Price.retrieve,
                settings.STRIPE_TOKEN_PRICE_ID,
                api_key=settings.STRIPE_SECRET_KEY,
            )
            recurring = price["recurring"]
            if (
                price["currency"] != "usd"
                or price["billing_scheme"] != "per_unit"
                or Decimal(price["unit_amount_decimal"])
                != Decimal(OVERAGE_CENTS_PER_MILLION) / 1_000_000
                or recurring["interval"] != "month"
                or recurring["interval_count"] != 1
                or recurring["usage_type"] != "metered"
                or price["transform_quantity"] is not None
            ):
                raise HTTPException(
                    503, "The Stripe transcript price does not match the published rate."
                )
            meter = await asyncio.to_thread(
                stripe.billing.Meter.retrieve,
                recurring["meter"],
                api_key=settings.STRIPE_SECRET_KEY,
            )
            if (
                meter["event_name"] != METER_EVENT_NAME
                or meter["status"] != "active"
                or meter["event_time_window"] is not None
                or meter["default_aggregation"]["formula"] != "sum"
                or meter["customer_mapping"]["event_payload_key"] != "stripe_customer_id"
                or meter["value_settings"]["event_payload_key"] != "value"
            ):
                raise HTTPException(503, "The Stripe transcript meter is misconfigured.")
            live = await asyncio.to_thread(
                stripe.Subscription.retrieve,
                sub["stripe_subscription_id"],
                api_key=settings.STRIPE_SECRET_KEY,
            )
            if live["status"] != "active":
                raise HTTPException(400, "The subscription is no longer active.")
            items = [
                i
                for i in live["items"]["data"]
                if i["price"]["id"] == settings.STRIPE_TOKEN_PRICE_ID
            ]
            if len(items) > 1:
                raise HTTPException(503, "Subscription has duplicate transcript meters.")
            if items:
                item_id = items[0]["id"]
            else:
                if live["billing_mode"]["type"] != "flexible":
                    await asyncio.to_thread(
                        stripe.Subscription.migrate,
                        sub["stripe_subscription_id"],
                        billing_mode={"type": "flexible"},
                        api_key=settings.STRIPE_SECRET_KEY,
                    )
                live = await asyncio.to_thread(
                    stripe.Subscription.modify,
                    sub["stripe_subscription_id"],
                    items=[{"price": settings.STRIPE_TOKEN_PRICE_ID}],
                    proration_behavior="none",
                    idempotency_key=f"transcript-meter-{sub['stripe_subscription_id']}",
                    api_key=settings.STRIPE_SECRET_KEY,
                )
                item_id = next(
                    i["id"]
                    for i in live["items"]["data"]
                    if i["price"]["id"] == settings.STRIPE_TOKEN_PRICE_ID
                )
        await conn.execute(
            "UPDATE user_subscriptions SET overage_limit_cents=$2,usage_item_id=$3,updated_at=now() WHERE user_id=$1",
            user_id,
            cents,
            item_id,
        )


async def apply_webhook_event(event: dict) -> None:
    """Sync subscription state from Stripe. Events for unknown customers
    (e.g. manual dashboard actions) are ignored, not errors."""
    kind = event["type"]
    obj = event["data"]["object"]

    if kind not in {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        return
    customer = obj["customer"]
    owner = await get_pool().fetchval(
        "SELECT user_id FROM user_subscriptions WHERE stripe_customer_id=$1", customer
    )
    if owner is None:
        return
    subscription_id = obj["subscription"] if kind == "checkout.session.completed" else obj["id"]
    # Read current state under the account lock; webhook deliveries can be reordered.
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.fetchval("SELECT id FROM users WHERE id=$1 FOR UPDATE", owner)
        live = await asyncio.to_thread(
            stripe.Subscription.retrieve, subscription_id, api_key=settings.STRIPE_SECRET_KEY
        )
        current_created = await conn.fetchval(
            "SELECT stripe_subscription_created FROM user_subscriptions WHERE user_id=$1", owner
        )
        if live["created"] < current_created:
            return
        items = [
            item
            for item in live["items"]["data"]
            if item["price"]["id"] == settings.STRIPE_TOKEN_PRICE_ID
        ]
        if len(items) > 1:
            raise ValueError("Subscription has duplicate transcript meters")
        item_id = items[0]["id"] if items else None
        await conn.execute(
            "UPDATE user_subscriptions SET stripe_subscription_id=$2,status=$3,usage_item_id=$4,"
            "stripe_subscription_created=$5,overage_limit_cents=CASE WHEN $3='active' AND $4::text IS NOT NULL "
            "THEN overage_limit_cents ELSE 0 END,updated_at=now() WHERE user_id=$1",
            owner,
            live["id"],
            live["status"],
            item_id,
            live["created"],
        )
