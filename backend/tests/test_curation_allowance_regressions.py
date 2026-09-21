from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from backend.config import settings
from backend.services import agent_service, billing_service, curation_service, sprite_agent_service
from backend.tasks import agent_schedules

from .test_curator import _push_events, _register


@pytest.fixture(autouse=True)
def free_plan(monkeypatch):
    monkeypatch.setattr(billing_service, "plan_label", AsyncMock(return_value="free"))


async def _traces(client, key, times):
    await _push_events(
        client,
        key,
        [
            {
                "agent_name": "claude-code",
                "event_type": "assistant_message",
                "content": "Useful work",
                "session_id": f"trace-{i}",
                "created_at": time.isoformat(),
            }
            for i, time in enumerate(times)
        ],
    )


@pytest.mark.asyncio
async def test_success_does_not_charge_imported_history_outside_the_run(client, pool):
    key, uid = await _register(client)
    now = datetime.now(UTC)
    since = now - timedelta(days=1)
    await _traces(client, key, [since - timedelta(days=30), now - timedelta(seconds=1)])
    curator = await agent_service.get_or_create_curator(uid)
    await agent_service.mark_curated(UUID(curator["id"]), now, since=since)
    rows = await pool.fetch(
        "SELECT session_id, curated_at FROM sessions WHERE owner_user_id=$1", uid
    )
    charged = {r["session_id"] for r in rows if r["curated_at"] is not None}
    assert charged == {"trace-1"}


@pytest.mark.asyncio
async def test_timestamp_ties_read_and_charge_only_selected_traces(client, pool, monkeypatch):
    key, uid = await _register(client)
    now = datetime.now(UTC)
    boundary = now - timedelta(seconds=1)
    since = now - timedelta(days=1)
    await _traces(client, key, [boundary] * 3)
    curator = await agent_service.get_or_create_curator(uid)
    monkeypatch.setattr(settings, "FREE_CURATED_TRACES", 1)
    feed = await curation_service.changes_since(uid, uid, since, now)
    read_ids = {e["session_id"] for e in feed["history"]}
    assert len(read_ids) == 1
    await agent_service.mark_curated(UUID(curator["id"]), now, since=since)
    rows = await pool.fetch(
        "SELECT session_id, curated_at FROM sessions WHERE owner_user_id=$1", uid
    )
    assert {r["session_id"] for r in rows if r["curated_at"] is not None} == read_ids
    position = await pool.fetchval(
        "SELECT curated_through FROM agents WHERE id=$1", UUID(curator["id"])
    )
    assert position < boundary
    assert (await curation_service.curation_allowance(uid, now))["used"] == 1

    # More allowance can consume the deferred tie; advancing the timestamp
    # past that tie would strand it permanently.
    monkeypatch.setattr(settings, "FREE_CURATED_TRACES", 2)
    feed = await curation_service.changes_since(uid, uid, position, now)
    assert len({e["session_id"] for e in feed["history"]} - read_ids) == 1
    await agent_service.mark_curated(UUID(curator["id"]), now, since=position)
    assert (await curation_service.curation_allowance(uid, now))["used"] == 2
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM sessions WHERE owner_user_id=$1 AND curated_at IS NULL", uid
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["first_day", "manual_worker", "scheduled_worker"])
async def test_exhausted_allowance_never_dispatches_or_runs_inference(
    client, pool, monkeypatch, path
):
    _, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    monkeypatch.setattr(settings, "FREE_CURATED_TRACES", 0)
    run = AsyncMock()
    monkeypatch.setattr(sprite_agent_service, "run_scheduled", run)
    dispatch = []
    monkeypatch.setattr(
        agent_schedules.run_curator_now, "delay", lambda *a, **k: dispatch.append(a)
    )
    if path == "first_day":
        await agent_schedules._maybe_dispatch_first_day_run(uid, curator, datetime.now(UTC))
    elif path == "manual_worker":
        await agent_schedules._run_curator_now(UUID(curator["id"]), automatic=True)
    else:
        await agent_schedules._run_scheduled_agent(UUID(curator["id"]), "test")
    run.assert_not_awaited()
    assert dispatch == []
    row = await pool.fetchrow(
        "SELECT curated_through, last_run_outcome FROM agents WHERE id=$1", UUID(curator["id"])
    )
    assert row["curated_through"] == curator["curated_through"]
    assert row["last_run_outcome"] == "skipped_credits"
