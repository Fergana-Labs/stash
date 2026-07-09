"""Plan entitlements: onboarding intent, admin grant, and the free-tier
sleep-time curator credit gate."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.services import agent_service

from .test_curator import _auth, _make_due, _register

ADMIN = {"X-Admin-Token": "test-admin-secret-token-at-least-32-chars-long"}


@pytest.mark.asyncio
async def test_plan_intent_persists_and_notifies_sales(client: AsyncClient, monkeypatch):
    """Picking the enterprise plan during onboarding is a sales lead: it must
    be stored on the user and fire the notify email — without granting the
    entitlement itself."""
    sent = []
    monkeypatch.setattr(
        "backend.routers.users.send_enterprise_lead_email",
        lambda name, email: sent.append((name, email)),
    )
    key, _uid = await _register(client)

    r = await client.patch(
        "/api/v1/users/me",
        json={"plan_intent": "Production agent — Enterprise"},
        headers=_auth(key),
    )

    assert r.status_code == 200
    assert r.json()["plan_intent"] == "Production agent — Enterprise"
    assert r.json()["plan"] == "free"  # intent is not entitlement
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_non_enterprise_intent_does_not_notify(client: AsyncClient, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "backend.routers.users.send_enterprise_lead_email",
        lambda name, email: sent.append((name, email)),
    )
    key, _uid = await _register(client)

    r = await client.patch(
        "/api/v1/users/me", json={"plan_intent": "Personal — Free"}, headers=_auth(key)
    )

    assert r.status_code == 200
    assert sent == []


@pytest.mark.asyncio
async def test_admin_grants_and_revokes_plan(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("backend.routers.admin.settings.ADMIN_PASSWORD", ADMIN["X-Admin-Token"])
    key, uid = await _register(client)

    granted = await client.post(
        f"/api/v1/admin/users/{uid}/plan", json={"plan": "enterprise"}, headers=ADMIN
    )
    assert granted.status_code == 200

    me = await client.get("/api/v1/users/me", headers=_auth(key))
    assert me.json()["plan"] == "enterprise"

    bad = await client.post(
        f"/api/v1/admin/users/{uid}/plan", json={"plan": "platinum"}, headers=ADMIN
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_mark_run_meters_per_calendar_month(client: AsyncClient, _db_pool):
    """The counter must reset when the month rolls over, or long-lived free
    accounts would permanently exhaust their allowance."""
    _key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)

    assert await agent_service.mark_run(UUID(curator["id"])) == 1
    assert await agent_service.mark_run(UUID(curator["id"])) == 2

    # Simulate the anchor pointing at last month → next run restarts at 1.
    await _db_pool.execute(
        "UPDATE agents SET month_run_anchor = (date_trunc('month', now()) - interval '1 month')::date "
        "WHERE id = $1",
        UUID(curator["id"]),
    )
    assert await agent_service.mark_run(UUID(curator["id"])) == 1


@pytest.mark.asyncio
async def test_free_curator_credits_exhausted_skips_run(
    client: AsyncClient, sprite_exec, _db_pool, monkeypatch
):
    """Free accounts get a monthly curator allowance; past it the beat must not
    wake the sprite. Enterprise is unlimited — same state runs after the grant."""
    from backend.tasks.agent_schedules import _run_due

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    # Real pending changes, so only the credit gate can be the reason to skip.
    await client.post(
        "/api/v1/me/pages/new", json={"name": "N", "content": "x"}, headers=_auth(key)
    )
    watermark = datetime.now(UTC) - timedelta(minutes=2)
    await _make_due(_db_pool, curator["id"], watermark)
    # Allowance already spent this month.
    await _db_pool.execute(
        "UPDATE agents SET month_run_count = $2, month_run_anchor = date_trunc('month', now())::date "
        "WHERE id = $1",
        UUID(curator["id"]),
        settings.FREE_CURATOR_RUNS_PER_MONTH,
    )

    ran = await _run_due()

    assert ran == 0
    assert sprite_exec.calls == []  # no sprite wake
    after = await _db_pool.fetchval(
        "SELECT curated_through FROM agents WHERE id = $1", UUID(curator["id"])
    )
    assert after == watermark  # skipped run never discards un-curated changes

    # Enterprise grant → the same overdue curator runs on the next beat.
    await _db_pool.execute("UPDATE users SET plan = 'enterprise' WHERE id = $1", uid)
    await _make_due(_db_pool, curator["id"], watermark)

    ran = await _run_due()

    assert ran == 1
    assert sprite_exec.calls != []


@pytest.mark.asyncio
async def test_on_demand_curator_run_refused_on_sse_route(client: AsyncClient, _db_pool):
    """The curator's "Run now" enqueues on the worker via /memory/recompute
    (metered there — see test_recompute_metered_like_the_scheduler). The SSE
    route refuses curators outright: a curation pass takes minutes, and an
    SSE run dies silently when the browser tab closes."""
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)

    r = await client.post(
        "/api/v1/me/agent-chat/run", json={"agent_id": curator["id"]}, headers=_auth(key)
    )
    assert r.status_code == 400
    assert "recompute" in r.json()["detail"]
