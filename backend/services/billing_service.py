"""Per-user Stripe billing: Free (1 connected source) vs Pro ($20/mo, unlimited).

Billing is switched on by STRIPE_SECRET_KEY being set (managed deployment).
Self-hosted instances leave it unset: billing endpoints 404 and the pay gate
is a no-op. Enforcement is connect-time only — existing sources keep syncing
even after a subscription lapses.

The user ↔ Stripe customer mapping row is created when checkout starts, so
every later webhook resolves by stripe_customer_id regardless of event order.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import stripe
from fastapi import HTTPException

from ..config import settings
from ..database import get_pool

# Stripe statuses that grant Pro. Everything else (past_due, canceled,
# unpaid, incomplete) means free-tier enforcement.
ACTIVE_STATUSES = {"active", "trialing"}
FREE_SOURCE_LIMIT = 1


def billing_enabled() -> bool:
    return settings.STRIPE_SECRET_KEY is not None


def require_billing_enabled() -> None:
    if not billing_enabled():
        raise HTTPException(status_code=404, detail="Billing is not enabled on this instance")


async def get_subscription(user_id: UUID) -> dict | None:
    row = await get_pool().fetchrow("SELECT * FROM user_subscriptions WHERE user_id = $1", user_id)
    return dict(row) if row else None


async def is_pro(user_id: UUID) -> bool:
    status = await get_pool().fetchval(
        "SELECT status FROM user_subscriptions WHERE user_id = $1", user_id
    )
    return status in ACTIVE_STATUSES


async def source_count(user_id: UUID) -> int:
    return await get_pool().fetchval(
        "SELECT count(*) FROM workspace_sources WHERE owner_user_id = $1", user_id
    )


async def ensure_can_add_source(
    user_id: UUID, workspace_id: UUID, source_type: str, external_ref: str
) -> None:
    """Connect-time pay gate. Counts the user's sources across all workspaces,
    excluding the natural key being added — create_source is an upsert, and a
    free user re-adding their one existing source must keep working."""
    if not billing_enabled():
        return
    if await is_pro(user_id):
        return
    others = await get_pool().fetchval(
        """
        SELECT count(*) FROM workspace_sources
        WHERE owner_user_id = $1
          AND NOT (workspace_id = $2 AND source_type = $3 AND external_ref = $4)
        """,
        user_id,
        workspace_id,
        source_type,
        external_ref,
    )
    if others >= FREE_SOURCE_LIMIT:
        raise HTTPException(
            status_code=402,
            detail="The free plan includes 1 connected source. Upgrade to Pro to connect more.",
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


async def create_checkout_session(user: dict) -> str:
    customer_id = await _get_or_create_customer_id(user)
    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        api_key=settings.STRIPE_SECRET_KEY,
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(user["id"]),
        line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
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


async def apply_webhook_event(event: dict) -> None:
    """Sync subscription state from Stripe. Events for unknown customers
    (e.g. manual dashboard actions) are ignored, not errors."""
    kind = event["type"]
    obj = event["data"]["object"]

    if kind == "checkout.session.completed":
        await get_pool().execute(
            """
            UPDATE user_subscriptions
            SET stripe_subscription_id = $1, status = 'active', updated_at = now()
            WHERE stripe_customer_id = $2
            """,
            obj.get("subscription"),
            obj.get("customer"),
        )
    elif kind == "customer.subscription.updated":
        await get_pool().execute(
            """
            UPDATE user_subscriptions
            SET stripe_subscription_id = $1, status = $2, updated_at = now()
            WHERE stripe_customer_id = $3
            """,
            obj.get("id"),
            obj.get("status"),
            obj.get("customer"),
        )
    elif kind == "customer.subscription.deleted":
        await get_pool().execute(
            """
            UPDATE user_subscriptions
            SET status = 'canceled', updated_at = now()
            WHERE stripe_customer_id = $1
            """,
            obj.get("customer"),
        )
