"""Financial invariants: consent, exact overages, durable retries, and account isolation."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
import stripe
from fastapi import HTTPException

from backend.config import settings
from backend.services import billing_service, curation_service, workspace_service
from backend.services import transcript_usage_service as usage
from backend.tasks.transcript_billing import _report_usage

from .test_billing import _auth, _register
from .test_curation_allowance_regressions import _events


@pytest.fixture
async def paid(client, pool, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_TOKEN_PRICE_ID", "price_tokens")
    monkeypatch.setattr(usage, "PRO_TOKENS", 1)
    key, owner = await _register(client)
    await pool.execute(
        "INSERT INTO user_subscriptions(user_id,stripe_customer_id,stripe_subscription_id,status) "
        "VALUES ($1,'cus_usage','sub_usage','active')",
        owner,
    )
    return key, owner


async def _consume(pool, owner, events):
    async with pool.acquire() as conn, conn.transaction():
        await usage.record(conn, owner, events, datetime.now(UTC))


@pytest.mark.asyncio
async def test_meter_only_tokens_above_included_usage_once(paid, client, pool):
    key, owner = paid
    await pool.execute(
        "UPDATE user_subscriptions SET overage_limit_cents=1,usage_item_id='si_usage' WHERE user_id=$1",
        owner,
    )
    await _events(client, key, ["hello world"])
    events, _ = await curation_service._feed_events(owner, None, datetime.now(UTC), 500)
    await asyncio.gather(_consume(pool, owner, events), _consume(pool, owner, events))
    budget = await usage.allowance(owner, datetime.now(UTC))
    assert budget["used"] == 2
    assert budget["overage_tokens"] == 1
    assert budget["remaining"] == 999
    assert budget["overage_cents"] == 0.001
    assert await pool.fetchval("SELECT count(*) FROM transcript_meter_events") == 1
    await pool.execute(
        "UPDATE user_subscriptions SET overage_limit_cents=0 WHERE user_id=$1", owner
    )
    budget = await usage.allowance(owner, datetime.now(UTC))
    assert budget["remaining"] == 0
    assert budget["overage_tokens"] == 1


@pytest.mark.asyncio
async def test_overages_need_both_consent_and_active_meter(paid, pool):
    _, owner = paid
    for cap, item, status in [
        (0, "si", "active"),
        (20, None, "active"),
        (20, "si", "past_due"),
        (20, "si", "trialing"),
    ]:
        await pool.execute(
            "UPDATE user_subscriptions SET overage_limit_cents=$2,usage_item_id=$3,status=$4 WHERE user_id=$1",
            owner,
            cap,
            item,
            status,
        )
        assert (await usage.allowance(owner, datetime.now(UTC)))["overages_enabled"] is False


def _stripe_configuration(monkeypatch, mode="classic", amount="0.001"):
    price = {
        "currency": "usd",
        "billing_scheme": "per_unit",
        "unit_amount_decimal": amount,
        "transform_quantity": None,
        "recurring": {
            "interval": "month",
            "interval_count": 1,
            "usage_type": "metered",
            "meter": "mtr_tokens",
        },
    }
    meter = {
        "event_name": usage.METER_EVENT_NAME,
        "status": "active",
        "event_time_window": None,
        "default_aggregation": {"formula": "sum"},
        "customer_mapping": {"event_payload_key": "stripe_customer_id"},
        "value_settings": {"event_payload_key": "value"},
    }
    live = {
        "id": "sub_usage",
        "status": "active",
        "created": 123,
        "billing_mode": {"type": mode},
        "items": {"data": [{"id": "si_base", "price": {"id": "price_annual"}}]},
    }
    monkeypatch.setattr(stripe.Price, "retrieve", Mock(return_value=price))
    monkeypatch.setattr(stripe.billing.Meter, "retrieve", Mock(return_value=meter))
    monkeypatch.setattr(stripe.Subscription, "retrieve", Mock(return_value=live))
    migrate = Mock(return_value=live)
    modified = {
        **live,
        "items": {
            "data": live["items"]["data"] + [{"id": "si_usage", "price": {"id": "price_tokens"}}]
        },
    }
    modify = Mock(return_value=modified)
    monkeypatch.setattr(stripe.Subscription, "migrate", migrate)
    monkeypatch.setattr(stripe.Subscription, "modify", modify)
    return migrate, modify, live


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["classic", "flexible"])
async def test_annual_subscriber_opts_into_monthly_usage(paid, client, pool, monkeypatch, mode):
    key, owner = paid
    migrate, modify, _ = _stripe_configuration(monkeypatch, mode)
    response = await client.put(
        "/api/v1/billing/overage-limit", json={"limit_cents": 2000}, headers=_auth(key)
    )
    assert response.status_code == 200, response.text
    assert response.json()["overages_enabled"] is True
    assert response.json()["overage_limit_cents"] == 2000
    assert migrate.call_count == (1 if mode == "classic" else 0)
    assert modify.call_args.kwargs["items"] == [{"price": "price_tokens"}]
    assert modify.call_args.kwargs["proration_behavior"] == "none"
    assert (
        await pool.fetchval("SELECT usage_item_id FROM user_subscriptions WHERE user_id=$1", owner)
        == "si_usage"
    )


@pytest.mark.asyncio
async def test_wrong_stripe_rate_cannot_enable_spending(paid, pool, monkeypatch):
    _, owner = paid
    _, modify, _ = _stripe_configuration(monkeypatch, amount="1")
    with pytest.raises(HTTPException, match="published rate"):
        await billing_service.set_overage_limit(owner, 2000)
    modify.assert_not_called()
    assert (
        await pool.fetchval(
            "SELECT overage_limit_cents FROM user_subscriptions WHERE user_id=$1", owner
        )
        == 0
    )


@pytest.mark.asyncio
async def test_disabling_overages_does_not_remove_unbilled_usage_item(
    paid, client, pool, monkeypatch
):
    key, owner = paid
    await pool.execute(
        "UPDATE user_subscriptions SET overage_limit_cents=2000,usage_item_id='si_usage' WHERE user_id=$1",
        owner,
    )
    modify = Mock()
    monkeypatch.setattr(stripe.Subscription, "modify", modify)
    response = await client.put(
        "/api/v1/billing/overage-limit", json={"limit_cents": 0}, headers=_auth(key)
    )
    assert response.status_code == 200
    assert response.json()["overages_enabled"] is False
    assert (
        await pool.fetchval("SELECT usage_item_id FROM user_subscriptions WHERE user_id=$1", owner)
        == "si_usage"
    )
    modify.assert_not_called()


@pytest.mark.asyncio
async def test_workspace_view_cannot_change_personal_billing(paid, client, monkeypatch):
    key, owner = paid
    workspace = await workspace_service.create_workspace(
        "Usage test", domain=None, created_by=owner
    )
    call = Mock()
    monkeypatch.setattr(stripe.Subscription, "retrieve", call)
    response = await client.put(
        "/api/v1/billing/overage-limit",
        json={"limit_cents": 2000},
        headers={**_auth(key), "X-Stash-Scope": str(workspace["scope_user_id"])},
    )
    assert response.status_code == 403
    call.assert_not_called()


@pytest.mark.asyncio
async def test_reporter_retries_same_event_then_stops_after_success(paid, pool, monkeypatch):
    _, owner = paid
    event = await pool.fetchrow(
        "INSERT INTO transcript_meter_events(owner_user_id,customer_id,tokens) VALUES ($1,'cus_usage',345) RETURNING *",
        owner,
    )
    send = Mock(
        side_effect=[stripe.APIConnectionError("lost response"), {"identifier": str(event["id"])}]
    )
    monkeypatch.setattr(stripe.billing.MeterEvent, "create", send)
    with pytest.raises(stripe.APIConnectionError, match="lost response"):
        await _report_usage()
    assert await pool.fetchval("SELECT error FROM transcript_meter_events WHERE id=$1", event["id"])
    await pool.execute(
        "UPDATE transcript_meter_events SET last_attempt_at=now()-interval '6 minutes'"
    )
    assert sum(await asyncio.gather(_report_usage(), _report_usage())) == 1
    assert await _report_usage() == 0
    assert send.call_args_list[0] == send.call_args_list[1]
    assert send.call_args.kwargs["identifier"] == str(event["id"])
    assert send.call_args.kwargs["payload"] == {"stripe_customer_id": "cus_usage", "value": "345"}


@pytest.mark.asyncio
async def test_uncertain_delivery_older_than_dedup_window_requires_reconciliation(
    paid, pool, monkeypatch
):
    _, owner = paid
    await pool.execute(
        "INSERT INTO transcript_meter_events(owner_user_id,customer_id,tokens,first_attempt_at) VALUES ($1,'cus_usage',345,now()-interval '24 hours')",
        owner,
    )
    send = Mock()
    monkeypatch.setattr(stripe.billing.MeterEvent, "create", send)
    with pytest.raises(RuntimeError, match="manual Stripe reconciliation"):
        await _report_usage()
    send.assert_not_called()


@pytest.mark.asyncio
async def test_stale_webhook_cannot_restore_canceled_subscription(paid, pool, monkeypatch):
    _, owner = paid
    _, _, live = _stripe_configuration(monkeypatch)
    live["status"] = "canceled"
    await billing_service.apply_webhook_event(
        {
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_usage", "customer": "cus_usage", "status": "active"}},
        }
    )
    assert (
        await pool.fetchval("SELECT status FROM user_subscriptions WHERE user_id=$1", owner)
        == "canceled"
    )


@pytest.mark.asyncio
async def test_old_subscription_webhook_cannot_replace_new_subscription(paid, pool, monkeypatch):
    _, owner = paid
    _stripe_configuration(monkeypatch)
    await pool.execute(
        "UPDATE user_subscriptions SET stripe_subscription_id='sub_new',stripe_subscription_created=456 WHERE user_id=$1",
        owner,
    )
    await billing_service.apply_webhook_event(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_usage", "customer": "cus_usage"}},
        }
    )
    assert (
        await pool.fetchval(
            "SELECT stripe_subscription_id FROM user_subscriptions WHERE user_id=$1", owner
        )
        == "sub_new"
    )
