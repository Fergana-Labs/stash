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
    last_run_outcome = "failed" if last_run_error is not None else None
    await get_pool().execute(
        "UPDATE agents SET curated_through = $2, last_run_error = $3, "
        "last_run_outcome = $4 WHERE id = $1",
        agent["id"],
        datetime.now(UTC) - timedelta(hours=curated_hours_ago),
        last_run_error,
        last_run_outcome,
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
    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    await get_pool().execute(
        "UPDATE agents SET last_run_outcome = 'skipped_no_changes' WHERE id = $1", agent["id"]
    )
    await memory_service.push_event(
        user_id, "test", "user_message", "hello", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)

    assert await agent_schedules._alert_stale_curators() == 0
    assert sent == []


@pytest.mark.asyncio
async def test_stale_curator_with_unresolved_run_alerts(client: AsyncClient, monkeypatch):
    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    await get_pool().execute(
        "UPDATE agents SET last_run_outcome = 'started' WHERE id = $1", agent["id"]
    )
    await memory_service.push_event(
        user_id, "test", "user_message", "hello", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)

    assert await agent_schedules._alert_stale_curators() == 1
    assert len(sent) == 1 and "never resolved" in sent[0]


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

    async def fake_resolve(user_id, prefer_provider=None, curator_run=False):
        return None

    async def fake_run_scheduled(agent, stamp):
        raise RuntimeError("agent turn failed: opencode error")

    monkeypatch.setattr(agent_auth, "resolve", fake_resolve)
    monkeypatch.setattr(sprite_agent_service, "run_scheduled", fake_run_scheduled)
    sent = _capture_alerts(monkeypatch)

    dispatched = []
    monkeypatch.setattr(
        agent_schedules.run_scheduled_agent, "delay", lambda *args: dispatched.append(args)
    )
    assert await agent_schedules._run_due() == 1
    await agent_schedules._run_scheduled_agent(uuid.UUID(dispatched[0][0]), dispatched[0][1])
    assert len(sent) == 1
    assert "Scheduled agent run failed" in sent[0] and "opencode error" in sent[0]
    # The failure is also stored on the agent, which is what the stale-curator
    # watchdog keys off — the two alert paths must stay connected.
    row = await get_pool().fetchrow(
        "SELECT last_run_error, last_run_outcome FROM agents WHERE id = $1", agent["id"]
    )
    assert row["last_run_error"] is not None and "opencode error" in row["last_run_error"]
    assert row["last_run_outcome"] == "failed"


@pytest.mark.asyncio
async def test_run_bookkeeping_failure_sends_alert(client: AsyncClient, monkeypatch):
    """A run whose post-turn bookkeeping fails must record last_run_error and
    alert, exactly like a failed turn — otherwise the watermark silently stops
    advancing with no trace on the agent row."""
    from backend.services import curation_service, sprite_agent_service

    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)

    async def fake_run_scheduled(agent, stamp):
        return ""

    async def boom(user_id, curated_through, now):
        raise RuntimeError("watermark write failed")

    monkeypatch.setattr(sprite_agent_service, "run_scheduled", fake_run_scheduled)
    monkeypatch.setattr(curation_service, "complete_through", boom)
    sent = _capture_alerts(monkeypatch)

    await agent_schedules._run_scheduled_agent(uuid.UUID(agent["id"]), "202608091200")

    assert len(sent) == 1 and "watermark write failed" in sent[0]
    row = await get_pool().fetchrow(
        "SELECT last_run_error, last_run_outcome FROM agents WHERE id = $1", agent["id"]
    )
    assert row["last_run_error"] is not None and "watermark write failed" in row["last_run_error"]
    assert row["last_run_outcome"] == "failed"


@pytest.mark.asyncio
async def test_run_due_records_no_changes_skip(client: AsyncClient, monkeypatch):
    from backend.services import agent_auth, curation_service

    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=1, last_run_error=None)
    await get_pool().execute(
        "UPDATE agents SET schedule_cron = '* * * * *', last_run_at = $2 WHERE id = $1",
        agent["id"],
        datetime.now(UTC) - timedelta(minutes=5),
    )

    async def fake_resolve(user_id, prefer_provider=None, curator_run=False):
        return None

    async def no_changes(owner_user_id, user_id, since):
        return False

    monkeypatch.setattr(agent_auth, "resolve", fake_resolve)
    monkeypatch.setattr(curation_service, "has_changes_since", no_changes)

    assert await agent_schedules._run_due() == 0
    outcome = await get_pool().fetchval(
        "SELECT last_run_outcome FROM agents WHERE id = $1", agent["id"]
    )
    assert outcome == "skipped_no_changes"


@pytest.mark.asyncio
async def test_run_due_records_missing_credential_skip(client: AsyncClient, monkeypatch):
    from backend.services import agent_auth

    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=1, last_run_error=None)
    await get_pool().execute(
        "UPDATE agents SET schedule_cron = '* * * * *', last_run_at = $2 WHERE id = $1",
        agent["id"],
        datetime.now(UTC) - timedelta(minutes=5),
    )

    async def no_credential(user_id, prefer_provider=None, curator_run=False):
        raise agent_auth.NeedsAuth

    monkeypatch.setattr(agent_auth, "resolve", no_credential)

    assert await agent_schedules._run_due() == 0
    outcome = await get_pool().fetchval(
        "SELECT last_run_outcome FROM agents WHERE id = $1", agent["id"]
    )
    assert outcome == "skipped_no_credential"


@pytest.mark.asyncio
async def test_deleted_agent_run_is_a_quiet_no_op(client: AsyncClient, monkeypatch):
    """An agent deleted between the beat tick and its dispatched run has
    nothing to run and no row left to record a failure on — the task must
    return quietly instead of dying as a bare task error."""
    sent = _capture_alerts(monkeypatch)
    await agent_schedules._run_scheduled_agent(uuid.uuid4(), "202608091200")
    assert sent == []
