"""Token allowances must neither lose transcript prefixes nor charge repeated work."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import asyncpg
import pytest
from fastapi import HTTPException

from backend.services import agent_service, curation_service, sprite_agent_service
from backend.services import transcript_usage_service as usage
from backend.tasks import agent_schedules

from .test_curator import _push_events, _register


async def _events(client, key, contents, at=None):
    at = datetime.now(UTC) - timedelta(seconds=1) if at is None else at
    await _push_events(
        client,
        key,
        [
            {
                "agent_name": "codex",
                "event_type": "assistant_message",
                "content": content,
                "session_id": "one-session",
                "created_at": at.isoformat(),
            }
            for content in contents
        ],
    )


async def _finish(curator, since, until):
    async with curation_service.batch(curator["user_id"], since, until) as (
        events,
        through,
        batch_id,
    ):
        await agent_service.mark_curated(
            UUID(curator["id"]), through, events=events, batch_id=batch_id
        )


@pytest.mark.asyncio
async def test_retry_replacement_and_appended_content_charge_only_new_text(client, pool):
    key, owner = await _register(client)
    curator = await agent_service.get_or_create_curator(owner)
    await _events(client, key, ["hello world"])
    now = datetime.now(UTC)
    await _finish(curator, None, now)
    await _finish(curator, None, now)
    await pool.execute("DELETE FROM history_events WHERE owner_user_id=$1", owner)
    await _events(client, key, ["hello world", "More work"])
    await _finish(curator, None, datetime.now(UTC))
    assert (await usage.allowance(owner, datetime.now(UTC)))["used"] == 4
    assert (
        await pool.fetchval("SELECT count(*) FROM transcript_usage WHERE owner_user_id=$1", owner)
        == 2
    )


@pytest.mark.asyncio
async def test_success_does_not_charge_imported_history_outside_the_run(client, pool):
    key, owner = await _register(client)
    now = datetime.now(UTC)
    since = now - timedelta(days=1)
    await _events(client, key, ["Old history"], since - timedelta(days=30))
    await _events(client, key, ["New history"])
    curator = await agent_service.get_or_create_curator(owner)
    await _finish(curator, since, now)
    assert (await usage.allowance(owner, now))["used"] == 2
    # A concurrently imported older event remains pending, even before the run's window.
    position = await pool.fetchval(
        "SELECT curated_through FROM agents WHERE id=$1", UUID(curator["id"])
    )
    assert position < since - timedelta(days=30)


@pytest.mark.asyncio
async def test_timestamp_ties_drain_without_losing_or_double_charging(client, pool, monkeypatch):
    monkeypatch.setattr(usage, "FREE_TOKENS", 2)
    monkeypatch.setattr(curation_service, "_MAX_EVENTS", 1)
    key, owner = await _register(client)
    boundary = datetime.now(UTC) - timedelta(seconds=1)
    await _events(client, key, ["hello world", "More work", "Extra work"], boundary)
    curator = await agent_service.get_or_create_curator(owner)
    since = boundary - timedelta(days=1)
    seen = []
    for limit in (2, 4, 6):
        monkeypatch.setattr(usage, "FREE_TOKENS", limit)
        async with curation_service.batch(owner, since, datetime.now(UTC)) as (
            events,
            through,
            batch_id,
        ):
            assert len(events) == 1
            seen.append(events[0]["content"])
            await agent_service.mark_curated(
                UUID(curator["id"]), through, events=events, batch_id=batch_id
            )
        since = await pool.fetchval(
            "SELECT curated_through FROM agents WHERE id=$1", UUID(curator["id"])
        )
    assert len(set(seen)) == 3
    assert (await usage.allowance(owner, datetime.now(UTC)))["used"] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["first_day", "manual_worker", "scheduled_worker"])
async def test_exhausted_allowance_never_dispatches_or_runs_inference(
    client, pool, monkeypatch, path
):
    monkeypatch.setattr(usage, "FREE_TOKENS", 0)
    _, owner = await _register(client)
    curator = await agent_service.get_or_create_curator(owner)
    run = AsyncMock()
    monkeypatch.setattr(sprite_agent_service, "run_scheduled", run)
    dispatch = []
    monkeypatch.setattr(
        agent_schedules.run_curator_now, "delay", lambda *a, **k: dispatch.append(a)
    )
    if path == "first_day":
        await agent_schedules._maybe_dispatch_first_day_run(owner, curator, datetime.now(UTC))
    elif path == "manual_worker":
        await agent_schedules._run_curator_now(UUID(curator["id"]), automatic=True)
    else:
        await agent_schedules._run_scheduled_agent(UUID(curator["id"]), "test")
    run.assert_not_awaited()
    assert dispatch == []
    assert (
        await pool.fetchval("SELECT last_run_outcome FROM agents WHERE id=$1", UUID(curator["id"]))
        == "skipped_credits"
    )


@pytest.mark.asyncio
async def test_batch_freezes_input_and_rejects_concurrent_run(client, pool):
    key, owner = await _register(client)
    await _events(client, key, ["hello world"])
    curator = await agent_service.get_or_create_curator(owner)
    async with curation_service.batch(owner, None, datetime.now(UTC)) as (
        events,
        through,
        batch_id,
    ):
        await _events(client, key, ["Late arrival"])
        feed = await curation_service.changes_since(owner, owner, None)
        assert [e["content"] for e in feed["history"]] == ["hello world"]
        with pytest.raises(RuntimeError, match="already running"):
            async with curation_service.batch(owner, None, datetime.now(UTC)):
                pass
        await agent_service.mark_curated(
            UUID(curator["id"]), through, events=events, batch_id=batch_id
        )
    assert (await usage.allowance(owner, datetime.now(UTC)))["used"] == 2
    feed = await curation_service.changes_since(owner, owner, None)
    assert [e["content"] for e in feed["history"]] == ["Late arrival"]


@pytest.mark.asyncio
async def test_failed_run_charges_nothing_and_keeps_input_for_retry(client, pool, monkeypatch):
    key, owner = await _register(client)
    await _events(client, key, ["hello world"])
    curator = await agent_service.get_or_create_curator(owner)
    monkeypatch.setattr(
        sprite_agent_service,
        "run_scheduled",
        AsyncMock(side_effect=RuntimeError("provider failed")),
    )
    with pytest.raises(RuntimeError, match="provider failed"):
        await agent_schedules._run_curator_now(UUID(curator["id"]), full_history=True)
    assert (await usage.allowance(owner, datetime.now(UTC)))["used"] == 0
    assert await pool.fetchval("SELECT count(*) FROM curation_batches") == 0
    assert len((await curation_service.changes_since(owner, owner, None))["history"]) == 1


@pytest.mark.asyncio
async def test_changed_cap_rolls_back_both_usage_and_progress(client, pool, monkeypatch):
    key, owner = await _register(client)
    await _events(client, key, ["hello world"])
    curator = await agent_service.get_or_create_curator(owner)
    async with curation_service.batch(owner, None, datetime.now(UTC)) as (
        events,
        through,
        batch_id,
    ):
        monkeypatch.setattr(usage, "FREE_TOKENS", 1)
        with pytest.raises(HTTPException):
            await agent_service.mark_curated(
                UUID(curator["id"]), through, events=events, batch_id=batch_id
            )
    assert await pool.fetchval("SELECT count(*) FROM transcript_usage") == 0
    assert (
        await pool.fetchval("SELECT curated_through FROM agents WHERE id=$1", UUID(curator["id"]))
        == curator["curated_through"]
    )


@pytest.mark.asyncio
async def test_month_boundary_counts_processing_time_not_transcript_age(client, pool):
    key, owner = await _register(client)
    await _events(client, key, ["Old transcript"], datetime(2020, 1, 1, tzinfo=UTC))
    events, _ = await curation_service._feed_events(owner, None, datetime.now(UTC), 500)
    async with pool.acquire() as conn, conn.transaction():
        await usage.record(conn, owner, events, datetime(2026, 12, 31, 23, 59, tzinfo=UTC))
    assert (await usage.allowance(owner, datetime(2026, 12, 31, tzinfo=UTC)))["used"] == 2
    january = await usage.allowance(owner, datetime(2027, 1, 1, tzinfo=UTC))
    assert january["used"] == 0
    assert january["resets_at"] == "2027-02-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_oversized_entry_remains_pending(client, monkeypatch):
    monkeypatch.setattr(usage, "FREE_TOKENS", 1)
    key, owner = await _register(client)
    await _events(client, key, ["hello world"])
    feed = await curation_service.changes_since(owner, owner, None)
    assert feed["history"] == []
    assert feed["history_has_more"] is True
    assert (await usage.allowance(owner, datetime.now(UTC)))["used"] == 0


@pytest.mark.asyncio
async def test_completion_works_with_one_database_connection(client, pool, monkeypatch):
    from backend import database

    from .conftest import _TEST_DB_URL

    key, owner = await _register(client)
    await _events(client, key, ["hello world"])
    curator = await agent_service.get_or_create_curator(owner)
    async with curation_service.batch(owner, None, datetime.now(UTC)) as (
        events,
        through,
        batch_id,
    ):
        async with asyncpg.create_pool(_TEST_DB_URL, min_size=1, max_size=1) as single:
            monkeypatch.setattr(database, "pool", single)
            await asyncio.wait_for(
                agent_service.mark_curated(
                    UUID(curator["id"]), through, events=events, batch_id=batch_id
                ),
                timeout=3,
            )
        monkeypatch.setattr(database, "pool", pool)
    assert (await usage.allowance(owner, datetime.now(UTC)))["used"] == 2


def test_tokenizer_counts_arbitrary_transcript_text():
    assert usage.count_tokens("hello world") == 2
    assert usage.count_tokens("") == 0
    assert usage.count_tokens("<|endoftext|> 中文 🐙") > 0
