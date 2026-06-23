"""Billing: the connect-time pay gate and Stripe webhook state sync.

Why these tests matter: the free plan is enforced when CONNECTING an account —
a free user keeps one connected account (each account row counts, so a second
mailbox on the same provider also gates), and an active subscription lifts the
cap. Sources added under a connection are unlimited. Billing is off entirely
when STRIPE_SECRET_KEY is unset (self-host).
"""

import hashlib
import hmac
import json
import time
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from httpx import AsyncClient

from backend.config import settings
from backend.services import billing_service

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


async def _connect_account(pool, user_id: UUID, provider: str, account_key: str = "default"):
    """Simulate a completed connection by inserting the stored-token row."""
    await pool.execute(
        "INSERT INTO user_integrations "
        "(user_id, provider, access_token_encrypted, account_key) VALUES ($1, $2, $3, $4)",
        user_id,
        provider,
        b"\x00",
        account_key,
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


@pytest.fixture
def github_enabled(monkeypatch):
    monkeypatch.setattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "GITHUB_OAUTH_CLIENT_ID", "gh-client")
    monkeypatch.setattr(settings, "GITHUB_OAUTH_CLIENT_SECRET", "gh-secret")
    monkeypatch.setattr(settings, "GITHUB_OAUTH_REDIRECT_URI", "https://app.example.com/callback")


@pytest.mark.asyncio
async def test_free_user_gated_at_second_connection(client, pool, billing_on):
    _, user_id = await _register(client)

    # No connections yet — the first one is free.
    await billing_service.ensure_can_connect(user_id)

    await _connect_account(pool, user_id, "github")
    with pytest.raises(HTTPException) as exc:
        await billing_service.ensure_can_connect(user_id)
    assert exc.value.status_code == 402
    assert "Upgrade to Pro" in exc.value.detail

    # An active subscription lifts the cap.
    await pool.execute(
        "INSERT INTO user_subscriptions (user_id, stripe_customer_id, status) "
        "VALUES ($1, 'cus_gate', 'active')",
        user_id,
    )
    await billing_service.ensure_can_connect(user_id)


@pytest.mark.asyncio
async def test_each_account_counts(client, pool, billing_on):
    """A second mailbox on an already-connected provider is a second account,
    so it gates just like a brand-new provider would."""
    _, user_id = await _register(client)
    await _connect_account(pool, user_id, "gmail", account_key="a@x.com")

    assert await billing_service.connection_count(user_id) == 1
    with pytest.raises(HTTPException) as exc:
        await billing_service.ensure_can_connect(user_id)
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_internal_email_gets_pro_without_subscription(client, pool, billing_on):
    """Team accounts on an internal domain bypass the pay gate with no Stripe row."""
    api_key, user_id = await _register(client)
    await pool.execute("UPDATE users SET email = 'dev@joinstash.ai' WHERE id = $1", user_id)
    await _connect_account(pool, user_id, "github")

    # A free user would be gated here; the internal account is not.
    await billing_service.ensure_can_connect(user_id)

    me = (await client.get("/api/v1/billing/me", headers=_auth(api_key))).json()
    assert me["plan"] == "pro"
    assert me["status"] is None


@pytest.mark.asyncio
async def test_internal_bypass_can_be_disabled(client, pool, billing_on, monkeypatch):
    """Flipping INTERNAL_DOMAINS_FREE_PRO off makes internal accounts hit the
    real pay gate — for testing the paywall."""
    monkeypatch.setattr(settings, "INTERNAL_DOMAINS_FREE_PRO", False)
    _, user_id = await _register(client)
    await pool.execute("UPDATE users SET email = 'dev@joinstash.ai' WHERE id = $1", user_id)
    await _connect_account(pool, user_id, "github")

    with pytest.raises(HTTPException) as exc:
        await billing_service.ensure_can_connect(user_id)
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_gate_off_when_billing_disabled(client, pool, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    _, user_id = await _register(client)
    await _connect_account(pool, user_id, "github")

    # Self-hosted: no cap even with an existing connection.
    await billing_service.ensure_can_connect(user_id)


@pytest.mark.asyncio
async def test_connect_endpoint_gates_second_connection(client, pool, billing_on, github_enabled):
    api_key, user_id = await _register(client)

    first = await client.get("/api/v1/integrations/github/connect", headers=_auth(api_key))
    assert first.status_code == 200
    assert "github.com/login/oauth/authorize" in first.json()["authorize_url"]

    await _connect_account(pool, user_id, "github")

    blocked = await client.get("/api/v1/integrations/github/connect", headers=_auth(api_key))
    assert blocked.status_code == 402
    assert "Upgrade to Pro" in blocked.json()["detail"]


@pytest.mark.asyncio
async def test_billing_me_reflects_plan(client, pool, billing_on):
    api_key, user_id = await _register(client)
    await _connect_account(pool, user_id, "github")

    me = (await client.get("/api/v1/billing/me", headers=_auth(api_key))).json()
    assert me == {
        "billing_enabled": True,
        "plan": "free",
        "status": None,
        "connection_count": 1,
        "connection_limit": 1,
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
