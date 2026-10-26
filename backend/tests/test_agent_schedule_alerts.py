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


@pytest.mark.asyncio
async def test_queued_curator_does_not_run_after_pause(client, pool, monkeypatch):
    from backend.services import sprite_agent_service

    user_id = await _register(client)
    agent = await agent_service.get_or_create_curator(user_id)
    await pool.execute("UPDATE agents SET run_mode='chat' WHERE id=$1", agent["id"])

    async def forbidden(*args):
        pytest.fail("A queued job must respect a subsequent pause")

    monkeypatch.setattr(sprite_agent_service, "run_scheduled", forbidden)
    await agent_schedules._run_scheduled_agent(agent["id"], "test")


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
async def test_successful_but_backlogged_curator_still_alerts(client, pool, monkeypatch):
    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    await agent_service.mark_run_succeeded(agent["id"])
    await memory_service.push_event(
        user_id, "test", "user_message", "pending", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)
    assert await agent_schedules._alert_stale_curators() == 1
    assert "backlog remains after a successful batch" in sent[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    ["progress", "caught_up", "drained", "no_progress", "paused", "exhausted", "failed", "free"],
)
async def test_scoped_curator_catchup_is_bounded_and_requires_progress(
    client, pool, monkeypatch, mode
):
    from backend.services import billing_service, scoped_curation_service

    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    agent = await agent_service.get_agent_by_id(agent["id"])
    started = datetime.now(UTC)
    before = agent["curated_through"]
    through = started if mode == "caught_up" else before + timedelta(hours=1)
    if mode == "no_progress":
        through = before
    # A batch that stopped at its input budget leaves a cursor; one that drained
    # everything up to its start leaves it empty.
    cursor = {} if mode in ("caught_up", "drained") else {"since": through.isoformat()}
    await pool.execute(
        "UPDATE agents SET curated_through=$2,run_mode=$3,last_run_outcome=$4,"
        "curation_cursor=$5 WHERE id=$1",
        agent["id"],
        through,
        "chat" if mode == "paused" else "scheduled",
        "failed" if mode == "failed" else "ran",
        cursor,
    )
    if mode == "no_progress":
        agent = {**agent, "curation_cursor": cursor}

    async def workspace(_):
        return {"id": uuid.uuid4()}

    async def entitled(_):
        return mode != "free"

    monkeypatch.setattr(billing_service, "is_pro", entitled)
    monkeypatch.setattr(scoped_curation_service, "workspace_for_agent", workspace)

    async def pending(*args):
        return mode != "caught_up"

    monkeypatch.setattr(agent_schedules, "_pending_input", pending)
    queued = []
    monkeypatch.setattr(
        agent_schedules.run_curator_now, "apply_async", lambda **kw: queued.append(kw)
    )
    await agent_schedules._queue_curator_catchup(agent, started, 0 if mode == "exhausted" else 2)
    if mode == "progress":
        assert queued == [
            {
                "args": [str(agent["id"])],
                "kwargs": {"metered": False, "catchup_remaining": 1, "catchup": True},
                "countdown": 15,
            }
        ]
    else:
        assert queued == []


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

    async def fake_resolve(user_id, prefer_provider=None):
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

    async def no_credential(user_id, prefer_provider=None):
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


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["manual", "scheduled"])
async def test_catchup_dispatch_failure_preserves_completed_batch_and_charge(
    client, pool, monkeypatch, trigger
):
    from backend.services import sprite_agent_service

    uid = await _register(client)
    agent = await _make_curator(uid, curated_hours_ago=72, last_run_error=None)

    async def completed(*args):
        return "Completed."

    async def unavailable(*args, **kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(sprite_agent_service, "run_scheduled", completed)
    monkeypatch.setattr(agent_schedules, "_queue_curator_catchup", unavailable)
    alerts = _capture_alerts(monkeypatch)
    if trigger == "manual":
        await agent_schedules._run_curator_now(agent["id"])
    else:
        await agent_service.mark_run(agent["id"])
        await agent_schedules._run_scheduled_agent(agent["id"], "dispatch-failure")
    current = await agent_service.get_agent_by_id(agent["id"])
    assert current["last_run_outcome"] == "ran"
    assert current["last_run_error"] is None
    assert current["month_run_count"] == 1
    assert current["curated_through"] > datetime.now(UTC) - timedelta(minutes=1)
    assert len(alerts) == 1 and "catch-up dispatch failed" in alerts[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["manual", "scheduled"])
async def test_busy_scoped_curator_refunds_only_skipped_run(
    client, pool, monkeypatch, trigger, sprite_exec
):
    from backend.services import scoped_curation_service, sprite_agent_service

    uid = await _register(client)
    agent = await _make_curator(uid, curated_hours_ago=72, last_run_error=None)
    before = (await agent_service.get_agent_by_id(agent["id"]))["curated_through"]
    await agent_service.mark_run(agent["id"])

    async def workspace(_):
        return {"id": uuid.uuid4()}

    async def busy(*args, **kwargs):
        raise sprite_agent_service.TurnInProgress

    monkeypatch.setattr(scoped_curation_service, "workspace_for_agent", workspace)
    monkeypatch.setattr(sprite_agent_service, "run_scheduled", busy)
    alerts = _capture_alerts(monkeypatch)
    if trigger == "manual":
        await agent_schedules._run_curator_now(agent["id"])
    else:
        await agent_service.mark_run(agent["id"])
        await agent_schedules._run_scheduled_agent(agent["id"], "busy")
    current = await agent_service.get_agent_by_id(agent["id"])
    assert current["month_run_count"] == 1
    assert current["last_run_outcome"] == "started"
    assert current["last_run_error"] is None
    assert current["curated_through"] == before
    assert alerts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["entitlement", "workspace", "input", "auth"])
async def test_queued_catchup_rechecks_execution_gates(
    client, pool, monkeypatch, changed, sprite_exec
):
    from backend.services import (
        agent_auth,
        billing_service,
        scoped_curation_service,
        sprite_agent_service,
    )

    uid = await _register(client)
    agent = await _make_curator(uid, curated_hours_ago=72, last_run_error=None)

    async def workspace(_):
        return None if changed == "workspace" else {"id": uuid.uuid4()}

    async def entitled(_):
        return changed != "entitlement"

    async def pending(*args):
        return changed != "input"

    async def auth(_, **kwargs):
        if changed == "auth":
            raise agent_auth.ProviderNotConfigured("revoked")

    async def forbidden(*args):
        pytest.fail("Catch-up must recheck its gates before starting a model run")

    monkeypatch.setattr(scoped_curation_service, "workspace_for_agent", workspace)
    monkeypatch.setattr(scoped_curation_service, "require_run_auth", auth)
    monkeypatch.setattr(billing_service, "is_pro", entitled)
    monkeypatch.setattr(agent_schedules, "_pending_input", pending)
    monkeypatch.setattr(sprite_agent_service, "run_scheduled", forbidden)
    if changed == "auth":
        with pytest.raises(agent_auth.ProviderNotConfigured):
            await agent_schedules._run_curator_now(agent["id"], metered=False, catchup=True)
    else:
        await agent_schedules._run_curator_now(agent["id"], metered=False, catchup=True)
    current = await agent_service.get_agent_by_id(agent["id"])
    assert current["last_run_outcome"] is None
    assert current["month_run_count"] == 0


@pytest.mark.asyncio
async def test_weekly_curator_is_not_stale_before_its_next_scheduled_run(client, pool, monkeypatch):
    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    previous = datetime.now(UTC) - timedelta(days=3)
    cron = f"0 0 * * {(previous.weekday() + 1) % 7}"
    await pool.execute(
        "UPDATE agents SET last_run_outcome='ran',schedule_cron=$2 WHERE id=$1", agent["id"], cron
    )
    await memory_service.push_event(
        user_id, "test", "user_message", "pending", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)
    assert await agent_schedules._alert_stale_curators() == 0
    assert sent == []


@pytest.mark.asyncio
async def test_partly_drained_weekly_curator_waits_for_its_next_run(client, pool, monkeypatch):
    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=5 * 24, last_run_error=None)
    await pool.execute(
        "UPDATE agents SET last_run_outcome='ran',schedule_cron='0 0 * * 0',"
        "last_run_at=now()-interval '1 day' WHERE id=$1",
        agent["id"],
    )
    await memory_service.push_event(
        user_id, "test", "user_message", "pending", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)
    assert await agent_schedules._alert_stale_curators() == 0
    await pool.execute(
        "UPDATE agents SET curated_through=now()-interval '9 days' WHERE id=$1", agent["id"]
    )
    assert await agent_schedules._alert_stale_curators() == 1
    assert "backlog remains after a successful batch" in sent[0]


@pytest.mark.asyncio
async def test_failed_without_message_is_not_reported_as_stuck(client, pool, monkeypatch):
    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    await pool.execute("UPDATE agents SET last_run_outcome='failed' WHERE id=$1", agent["id"])
    await memory_service.push_event(
        user_id, "test", "user_message", "pending", user_id, f"sess-{uuid.uuid4()}"
    )
    sent = _capture_alerts(monkeypatch)
    assert await agent_schedules._alert_stale_curators() == 1
    assert "last run failed without an error message" in sent[0]
    assert "never resolved" not in sent[0]


@pytest.mark.asyncio
async def test_catchup_budget_is_atomic_shared_and_expires_after_24_hours(client, pool):
    import asyncio

    user_id = await _register(client)
    agent = await agent_service.get_or_create_curator(user_id)
    claims = await asyncio.gather(*(agent_service.claim_catchup(agent["id"], 7) for _ in range(20)))
    assert sum(claims) == 7
    # Starting other manual/scheduled/first-day runs cannot reset this allowance.
    await agent_service.mark_run(agent["id"])
    await agent_service.mark_run(agent["id"], metered=False)
    assert not await agent_service.claim_catchup(agent["id"], 7)
    await pool.execute(
        "UPDATE agents SET catchup_window_started=now()-interval '25 hours' WHERE id=$1",
        agent["id"],
    )
    assert await agent_service.claim_catchup(agent["id"], 7)
    assert await pool.fetchval("SELECT catchup_runs FROM agents WHERE id=$1", agent["id"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["manual", "beat"])
async def test_busy_attempt_does_not_erase_previous_status_or_consume_tick(
    client, pool, monkeypatch, sprite_exec, trigger
):
    from backend.services import scoped_curation_service, sprite_agent_service

    user_id = await _register(client)
    agent = await _make_curator(
        user_id, curated_hours_ago=72, last_run_error="Previous worker error"
    )
    await pool.execute(
        "UPDATE agents SET schedule_cron='* * * * *',last_run_at=now()-interval '5 minutes' WHERE id=$1",
        agent["id"],
    )

    async def workspace(_):
        return {"id": uuid.uuid4()}

    monkeypatch.setattr(scoped_curation_service, "workspace_for_agent", workspace)
    before = await agent_service.get_agent_by_id(agent["id"])
    async with sprite_agent_service._TurnLock(f"scoped-curator-{agent['id']}"):
        if trigger == "manual":
            await agent_schedules._run_curator_now(agent["id"])
        else:
            assert await agent_schedules._run_due() == 0
    after = await agent_service.get_agent_by_id(agent["id"])
    for key in (
        "last_run_at",
        "last_run_error",
        "last_run_outcome",
        "month_run_count",
        "month_run_anchor",
    ):
        assert before[key] == after[key]


@pytest.mark.asyncio
async def test_catchup_uses_pending_input_not_outer_task_start_time(client, pool, monkeypatch):
    from backend.services import billing_service

    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    agent = await agent_service.get_agent_by_id(agent["id"])
    started = datetime.now(UTC)
    through = started + timedelta(milliseconds=1)
    await pool.execute(
        "UPDATE agents SET curated_through=$2,last_run_outcome='ran',curation_cursor=$3 WHERE id=$1",
        agent["id"],
        through,
        {"since": through.isoformat()},
    )

    async def yes(*args):
        return True

    monkeypatch.setattr(billing_service, "is_pro", yes)
    monkeypatch.setattr(agent_schedules, "_pending_input", yes)
    queued = []
    monkeypatch.setattr(
        agent_schedules.run_curator_now, "apply_async", lambda **kw: queued.append(kw)
    )
    await agent_schedules._queue_curator_catchup(agent, started, 2, workspace={"id": uuid.uuid4()})
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_exhausted_shared_catchup_allowance_never_starts_model(
    client, pool, monkeypatch, sprite_exec
):
    from backend.services import billing_service, scoped_curation_service

    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error="Earlier error")
    await pool.execute(
        "UPDATE agents SET catchup_window_started=now(),catchup_runs=7 WHERE id=$1", agent["id"]
    )

    async def workspace(_):
        return {"id": uuid.uuid4()}

    async def yes(*args, **kwargs):
        return True

    async def forbidden(*args, **kwargs):
        pytest.fail("Exhausted catch-up budget must stop before execution")

    monkeypatch.setattr(scoped_curation_service, "workspace_for_agent", workspace)
    monkeypatch.setattr(scoped_curation_service, "require_run_auth", yes)
    monkeypatch.setattr(billing_service, "is_pro", yes)
    monkeypatch.setattr(agent_schedules, "_pending_input", yes)
    monkeypatch.setattr(agent_schedules, "_run_turn", forbidden)
    before = await agent_service.get_agent_by_id(agent["id"])
    await agent_schedules._run_curator_now(agent["id"], metered=False, catchup=True)
    after = await agent_service.get_agent_by_id(agent["id"])
    assert after == before


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["busy", "failure"])
async def test_refunds_do_not_change_an_old_month_counter(client, pool, reason):
    user_id = await _register(client)
    agent = await agent_service.get_or_create_curator(user_id)
    await pool.execute(
        "UPDATE agents SET month_run_anchor=(now()-interval '2 months')::date,month_run_count=3 WHERE id=$1",
        agent["id"],
    )
    if reason == "busy":
        await agent_schedules._skip_busy_curator(agent["id"], metered=True)
    else:
        await agent_service.mark_run_failed(agent["id"], "Failed")
    assert await pool.fetchval("SELECT month_run_count FROM agents WHERE id=$1", agent["id"]) == 3


@pytest.mark.asyncio
async def test_due_scoped_run_is_queued_after_the_scheduler_releases_its_lock(
    client, pool, monkeypatch
):
    from backend.services import scoped_curation_service, sprite_agent_service

    user_id = await _register(client)
    agent = await _make_curator(user_id, curated_hours_ago=72, last_run_error=None)
    await pool.execute(
        "UPDATE agents SET schedule_cron='* * * * *',last_run_at=now()-interval '5 minutes' WHERE id=$1",
        agent["id"],
    )

    async def workspace(_):
        return {"id": uuid.uuid4()}

    async def yes(*args, **kwargs):
        return True

    async def authorized(*args, **kwargs):
        return None

    monkeypatch.setattr(scoped_curation_service, "workspace_for_agent", workspace)
    monkeypatch.setattr(scoped_curation_service, "require_run_auth", authorized)
    monkeypatch.setattr(agent_schedules, "_pending_input", yes)
    events = []
    release = sprite_agent_service._TurnLock.__aexit__

    async def tracked_release(self, *exc):
        await release(self, *exc)
        events.append("released")

    monkeypatch.setattr(sprite_agent_service._TurnLock, "__aexit__", tracked_release)
    monkeypatch.setattr(
        agent_schedules.run_scheduled_agent, "delay", lambda *args: events.append("queued")
    )
    assert await agent_schedules._run_due() == 1
    # The worker takes the same lock, so it must be free once the task is queued.
    assert events == ["released", "queued"]


@pytest.mark.asyncio
async def test_scheduler_lock_outlives_the_run_timeout(client, monkeypatch):
    from backend.config import settings
    from backend.services import sprite_agent_service

    user_id = await _register(client)
    agent = await agent_service.get_or_create_curator(user_id)
    lock = agent_schedules._run_lock(agent, {"id": uuid.uuid4()})
    async with lock:
        ttl = await sprite_agent_service._get_redis().ttl(
            f"agent-turn:scoped-curator-{agent['id']}"
        )
    assert ttl > settings.AGENT_TURN_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_personal_curator_turn_conflict_is_not_reported_as_busy(client, monkeypatch):
    from backend.services import sprite_agent_service

    user_id = await _register(client)
    agent = await agent_service.get_or_create_curator(user_id)

    async def conflict(*args, **kwargs):
        raise sprite_agent_service.TurnInProgress

    monkeypatch.setattr(sprite_agent_service, "run_scheduled", conflict)
    with pytest.raises(sprite_agent_service.TurnInProgress):
        await agent_schedules._run_curator_now(agent["id"])
    current = await agent_service.get_agent_by_id(agent["id"])
    assert current["last_run_outcome"] == "failed"
