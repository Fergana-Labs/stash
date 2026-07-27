"""Scheduled-agent failures must page an operator, not just log.

The Memory curator failed silently for four days in July 2026 (the managed
harness broke; the only trace was an ERROR line in celery logs nobody reads).
These tests pin the two alert paths that prevent a repeat: per-run failure
alerts, and the daily stale-watermark watchdog.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from backend.database import get_pool
from backend.services import agent_service, alert_service, memory_service
from backend.tasks import agent_schedules

from .conftest import unique_name


async def _register(client: AsyncClient) -> uuid.UUID:
    name = unique_name("alerts")
    response = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1", "email": f"{name}@example.com"},
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


def _capture_alerts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent: list[str] = []

    async def fake_send_alert(text: str) -> None:
        sent.append(text)

    monkeypatch.setattr(alert_service, "send_alert", fake_send_alert)
    return sent


async def _make_curator(
    user_id: uuid.UUID, *, curated_hours_ago: int, last_run_error: str | None
) -> dict:
    agent = await agent_service.get_or_create_curator(user_id)
    await get_pool().execute(
        "UPDATE agents SET curated_through = $2, last_run_error = $3 WHERE id = $1",
        agent["id"],
        datetime.now(UTC) - timedelta(hours=curated_hours_ago),
        last_run_error,
    )
    return agent


@pytest.mark.asyncio
async def test_stale_failing_curator_alerts(client: AsyncClient, monkeypatch):
    user_id = await _register(client)
    await _make_curator(user_id, curated_hours_ago=72, last_run_error="opencode error")
    # A pending change — staleness only matters when there is work to curate.
    await memory_service.push_event(
        user_id, "test", "user_message", "hello", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)

    assert await agent_schedules._alert_stale_curators() == 1
    assert len(sent) == 1
    assert "stale" in sent[0] and "opencode error" in sent[0]


@pytest.mark.asyncio
async def test_skipped_by_design_curator_stays_quiet(client: AsyncClient, monkeypatch):
    # Curators skipped on purpose (credit allowance, no credential) never run,
    # so their error stays NULL — a stalled watermark there is not a failure.
    user_id = await _register(client)
    await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    await memory_service.push_event(
        user_id, "test", "user_message", "hello", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)

    assert await agent_schedules._alert_stale_curators() == 0
    assert sent == []


@pytest.mark.asyncio
async def test_stale_curator_without_pending_changes_stays_quiet(client: AsyncClient, monkeypatch):
    # An idle user's curator legitimately never advances — nothing to curate.
    user_id = await _register(client)
    await _make_curator(user_id, curated_hours_ago=72, last_run_error="opencode error")
    sent = _capture_alerts(monkeypatch)

    assert await agent_schedules._alert_stale_curators() == 0
    assert sent == []


@pytest.mark.asyncio
async def test_fresh_curator_stays_quiet(client: AsyncClient, monkeypatch):
    # One bad night must not page — the watchdog only fires past the 48h bar.
    user_id = await _register(client)
    await _make_curator(user_id, curated_hours_ago=1, last_run_error="opencode error")
    await memory_service.push_event(
        user_id, "test", "user_message", "hello", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)

    assert await agent_schedules._alert_stale_curators() == 0
    assert sent == []


@pytest.mark.asyncio
async def test_run_due_failure_sends_alert(client: AsyncClient, monkeypatch):
    from backend.services import agent_auth, sprite_agent_service

    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    # Make the curator due on the next tick and eligible to run.
    await get_pool().execute(
        "UPDATE agents SET schedule_cron = '* * * * *', last_run_at = $2 WHERE id = $1",
        agent["id"],
        datetime.now(UTC) - timedelta(minutes=5),
    )
    await memory_service.push_event(
        user_id, "test", "user_message", "hello", user_id, f"sess-{uuid.uuid4()}"
    )

    async def fake_resolve(user_id, prefer_provider=None):
        return None

    async def fake_run_scheduled(agent, stamp):
        raise RuntimeError("agent turn failed: opencode error")

    monkeypatch.setattr(agent_auth, "resolve", fake_resolve)
    monkeypatch.setattr(sprite_agent_service, "run_scheduled", fake_run_scheduled)
    sent = _capture_alerts(monkeypatch)

    assert await agent_schedules._run_due() == 0
    assert len(sent) == 1
    assert "Scheduled agent run failed" in sent[0] and "opencode error" in sent[0]
    # The failure is also stored on the agent, which is what the stale-curator
    # watchdog keys off — the two alert paths must stay connected.
    error = await get_pool().fetchval(
        "SELECT last_run_error FROM agents WHERE id = $1", agent["id"]
    )
    assert error is not None and "opencode error" in error
