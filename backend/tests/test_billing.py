"""Billing: the connect-time pay gate and Stripe webhook state sync.

Why these tests matter: the free plan is enforced ONLY when adding a source —
a free user keeps one connected source, idempotent re-adds of that source must
not be blocked (create_source is an upsert), and an active subscription lifts
the cap. Billing is off entirely when STRIPE_SECRET_KEY is unset (self-host).
"""

import hashlib
import hmac
import json
import time
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings

from .conftest import unique_name


async def _register(client: AsyncClient, prefix: str = "bill") -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(prefix), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _create_workspace(client: AsyncClient, api_key: str) -> UUID:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": unique_name("bill_ws")},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


async def _add_repo(client: AsyncClient, api_key: str, ws: UUID, repo: str):
    return await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"source_type": "github_repo", "external_ref": repo},
        headers=_auth(api_key),
    )


def _stripe_signature(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


@pytest.fixture
def billing_on(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test_x")
    monkeypatch.setattr(settings, "STRIPE_MONTHLY_PRICE_ID", "price_test_month")
    monkeypatch.setattr(settings, "STRIPE_ANNUAL_PRICE_ID", "price_test_year")


@pytest.mark.asyncio
async def test_free_user_gated_at_second_source(client, pool, billing_on):
    api_key, user_id = await _register(client)
    ws = await _create_workspace(client, api_key)

    assert (await _add_repo(client, api_key, ws, "acme/one")).status_code == 200

    blocked = await _add_repo(client, api_key, ws, "acme/two")
    assert blocked.status_code == 402
    assert "Upgrade to Pro" in blocked.json()["detail"]

    # Re-adding the same source is an upsert, not a new source — must not 402.
    assert (await _add_repo(client, api_key, ws, "acme/one")).status_code == 200

    await pool.execute(
        "INSERT INTO user_subscriptions (user_id, stripe_customer_id, status) "
        "VALUES ($1, 'cus_gate', 'active')",
        user_id,
    )
    assert (await _add_repo(client, api_key, ws, "acme/two")).status_code == 200


@pytest.mark.asyncio
async def test_gate_counts_sources_across_workspaces(client, billing_on):
    api_key, _ = await _register(client)
    ws_a = await _create_workspace(client, api_key)
    ws_b = await _create_workspace(client, api_key)

    assert (await _add_repo(client, api_key, ws_a, "acme/one")).status_code == 200
    assert (await _add_repo(client, api_key, ws_b, "acme/two")).status_code == 402


@pytest.mark.asyncio
async def test_gate_off_when_billing_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    api_key, _ = await _register(client)
    ws = await _create_workspace(client, api_key)

    assert (await _add_repo(client, api_key, ws, "acme/one")).status_code == 200
    assert (await _add_repo(client, api_key, ws, "acme/two")).status_code == 200


@pytest.mark.asyncio
async def test_billing_me_reflects_plan(client, pool, billing_on):
    api_key, user_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    await _add_repo(client, api_key, ws, "acme/one")

    me = (await client.get("/api/v1/billing/me", headers=_auth(api_key))).json()
    assert me == {
        "billing_enabled": True,
        "plan": "free",
        "status": None,
        "source_count": 1,
        "source_limit": 1,
    }

    await pool.execute(
        "INSERT INTO user_subscriptions (user_id, stripe_customer_id, status) "
        "VALUES ($1, 'cus_me', 'active')",
        user_id,
    )
    me = (await client.get("/api/v1/billing/me", headers=_auth(api_key))).json()
    assert me["plan"] == "pro"
    assert me["status"] == "active"


@pytest.mark.asyncio
async def test_billing_me_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    api_key, _ = await _register(client)
    resp = await client.get("/api/v1/billing/me", headers=_auth(api_key))
    assert resp.json() == {"billing_enabled": False}


@pytest.mark.asyncio
async def test_webhook_subscription_deleted_downgrades(client, pool, billing_on):
    _, user_id = await _register(client)
    await pool.execute(
        "INSERT INTO user_subscriptions (user_id, stripe_customer_id, stripe_subscription_id, status) "
        "VALUES ($1, 'cus_hook', 'sub_1', 'active')",
        user_id,
    )

    payload = json.dumps(
        {
            "object": "event",
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_1", "customer": "cus_hook", "status": "canceled"}},
        }
    ).encode()
    resp = await client.post(
        "/api/v1/billing/webhook",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload, "whsec_test_x")},
    )
    assert resp.status_code == 200

    status = await pool.fetchval(
        "SELECT status FROM user_subscriptions WHERE user_id = $1", user_id
    )
    assert status == "canceled"


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(client, billing_on):
    payload = json.dumps(
        {"object": "event", "type": "customer.subscription.deleted", "data": {"object": {}}}
    ).encode()
    resp = await client.post(
        "/api/v1/billing/webhook",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload, "whsec_wrong")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_checkout_completed_activates(client, pool, billing_on):
    _, user_id = await _register(client)
    # The customer mapping row is created when checkout starts, before any webhook.
    await pool.execute(
        "INSERT INTO user_subscriptions (user_id, stripe_customer_id) VALUES ($1, 'cus_co')",
        user_id,
    )

    payload = json.dumps(
        {
            "object": "event",
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_co", "subscription": "sub_new"}},
        }
    ).encode()
    resp = await client.post(
        "/api/v1/billing/webhook",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload, "whsec_test_x")},
    )
    assert resp.status_code == 200

    row = await pool.fetchrow("SELECT * FROM user_subscriptions WHERE user_id = $1", user_id)
    assert row["status"] == "active"
    assert row["stripe_subscription_id"] == "sub_new"
