"""Regression tests for automatic annotation's failed/skipped work."""

# The labeler fixture is imported by name, so each use shadows the import.
# ruff: noqa: F811

import importlib
import json
from uuid import UUID

import asyncpg
import pytest

from backend.services.rm import workbench as legacy
from backend.services.rm import workbench_auto as auto

from .test_rm_workbench import BASE, account, model_and_queue_boundaries, upload  # noqa: F401
from .test_workbench_automatic import evaluate, get_eval, labeler  # noqa: F401


async def test_reconcile_combines_deployment_repair_and_removed_cap_recovery(
    client,
    pool,
    labeler,
):
    user, done, calls = await evaluate(client, pool, labeler)
    missing = await upload(client, user, "skipped-by-old-worker")
    stale = await upload(client, user, "stale-plan")
    exhausted = await upload(client, user, "three-failed-attempts")
    active = await upload(client, user, "running")
    waiting = await upload(client, user, "waiting")
    budget = await upload(client, user, "correction-extraction-deferral")
    former_cap = await upload(client, user, "removed-jev-cap")
    invalid = await upload(client, user, "malformed-provider-response")
    disabled_user = await account(client)
    disabled = await upload(client, disabled_user, "disabled")
    await pool.execute(
        "UPDATE users SET reward_models_enabled=false WHERE id=$1", disabled_user["uuid"]
    )
    for tid, status, error, attempts in [
        (missing, "completed", None, 1),
        (stale, "failed", auto.SCHEMA_CACHE_ERROR, 1),
        (exhausted, "failed", auto.SCHEMA_CACHE_ERROR, 3),
        (active, "running", None, 1),
        (waiting, "waiting", None, 1),
        (budget, "queued", None, 2),
        (former_cap, "queued", "Daily Jev evaluation budget reached; resumes tomorrow", 2),
        (invalid, "failed", "Jev returned an invalid grading response", 1),
        (disabled, "completed", None, 1),
    ]:
        await pool.execute(
            "UPDATE rm_wb_queue SET status=$2,error=$3,attempts=$4,started_at=now(),due_at=now()+interval '1 day' WHERE trace_id=$1",
            tid,
            status,
            error,
            attempts,
        )
    protected = [done, exhausted, active, waiting, budget, invalid, disabled]
    before = {
        t: dict(await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", t))
        for t in protected
    }
    await auto.recover()
    for t, original in before.items():
        assert (
            dict(await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", t)) == original
        )
    former = await pool.fetchrow(
        "SELECT status,error,due_at<=now() AS ready FROM rm_wb_queue WHERE trace_id=$1", former_cap
    )
    assert dict(former) == {"status": "queued", "error": None, "ready": True}
    for t in (missing, stale, former_cap):
        assert (
            await pool.fetchval("SELECT status FROM rm_wb_queue WHERE trace_id=$1", t) == "queued"
        )
        await auto.process_trace(t)
        assert (await get_eval(client, user, t))["current"]["status"] == "completed"
    count = len(calls)
    await auto.recover()
    await auto.process_trace(missing)
    await auto.process_trace(stale)
    await auto.process_trace(former_cap)
    assert len(calls) == count  # Repeated sweeps don't regrade finished work.


async def test_schema_failure_retries_without_an_operator_and_stops_after_three_attempts(
    client,
    pool,
    monkeypatch,
    labeler,
):
    user = await account(client)
    tid = await upload(client, user)
    read_trace = auto._read_trace
    reads = 0

    async def flaky(trace_id):
        nonlocal reads
        reads += 1
        if reads == 1:
            raise asyncpg.InvalidCachedStatementError(auto.SCHEMA_CACHE_ERROR)
        return await read_trace(trace_id)

    monkeypatch.setattr(auto, "_read_trace", flaky)
    await auto.process_trace(tid)
    assert await pool.fetchval("SELECT status FROM rm_wb_queue WHERE trace_id=$1", tid) == "queued"
    await auto.process_trace(tid)
    assert (await get_eval(client, user, tid))["current"]["status"] == "completed"

    broken = await upload(client, user, "persistent-schema-error")

    async def always_fails(trace_id):
        raise asyncpg.InvalidCachedStatementError(auto.SCHEMA_CACHE_ERROR)

    monkeypatch.setattr(auto, "_read_trace", always_fails)
    for _ in range(3):
        await auto.process_trace(broken)
    await auto.recover()
    row = await pool.fetchrow("SELECT status,attempts FROM rm_wb_queue WHERE trace_id=$1", broken)
    assert row["status"] == "failed" and row["attempts"] == 3


@pytest.mark.parametrize("evaluation_attached", [True, False])
async def test_missing_repository_keeps_feedback_interpretation_but_cannot_create_a_release(
    client,
    pool,
    monkeypatch,
    labeler,
    evaluation_attached,
):
    user, tid, _ = await evaluate(client, pool, labeler)
    e = (await get_eval(client, user, tid))["current"]
    await pool.execute("UPDATE rm_traces SET metadata=metadata-'cwd' WHERE id=$1", tid)
    response = await client.post(
        f"{BASE}/feedback",
        headers=user["headers"],
        json={
            "trace_id": str(tid),
            "target_step_id": e["actions"][0]["id"],
            **({"evaluation_id": e["id"]} if evaluation_attached else {}),
            "comment": "Verify tests before reporting success.",
            "change_kind": "both",
        },
    )
    assert response.status_code == 201, response.text
    fid = UUID(response.json()["id"])

    async def draft(**kwargs):
        data = json.loads(kwargs["prompt"])
        assert "no recorded repository" in data["instruction_draft_blocked_reason"]
        assert data["input"]
        return legacy.CorrectionDraft(
            change_kind="both",
            proposed_verdict=None,
            explanation="The success claim lacks test evidence.",
            title="Verify tests",
            grader_prompt="New rubric",
            instruction_text="Run tests before claiming success.",
        )

    monkeypatch.setattr(legacy.llm, "complete_structured", draft)
    # Exercise repair of feedback already stranded by the previous release.
    await pool.execute(
        "UPDATE rm_wb_feedback SET status='failed',error=$2 WHERE id=$1",
        fid,
        auto.MISSING_REPOSITORY,
    )
    await auto.recover()
    await legacy.prepare_feedback(fid)
    record = await legacy.feedback_detail(user["uuid"], fid)
    assert record["status"] == "completed" and record["error"] is None
    assert record["interpretation"]["explanation"] == "The success claim lacks test evidence."
    assert record["interpretation"]["instruction_draft_blocked_reason"]
    assert record["changes"] == []
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_graders") == 0
    accepted = await client.post(
        f"{BASE}/feedback/{fid}/review",
        headers=user["headers"],
        json={"decision": "accept", "change_kind": "both"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["review_status"] == "accepted"
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_instruction_releases") == 0


async def test_backfill_migration_preserves_running_lease(client, pool, monkeypatch):
    user = await account(client)
    active = await upload(client, user, "active")
    idle = await upload(client, user, "idle")
    await pool.execute(
        "UPDATE rm_wb_queue SET status='running',started_at=now()-interval '1 minute',attempts=2 WHERE trace_id=$1",
        active,
    )
    await pool.execute("UPDATE rm_wb_queue SET status='completed' WHERE trace_id=$1", idle)
    previous = dict(await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", active))
    # Run the real migration's backfill against real persisted queue rows.
    migration = importlib.import_module("backend.migrations.versions.0221_automatic_jev_evaluation")
    statements = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()
    backfill = next(sql for sql in statements if "INSERT INTO rm_wb_queue" in sql)
    await pool.execute(backfill)
    current = dict(await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", active))
    assert current["status"] == "running"
    assert current["started_at"] == previous["started_at"] and current["attempts"] == 2
    assert current["requested_at"] > previous["requested_at"]
    assert await pool.fetchval("SELECT status FROM rm_wb_queue WHERE trace_id=$1", idle) == "queued"


@pytest.mark.parametrize("fail", [False, True])
async def test_legacy_worker_cannot_finish_or_fail_a_replacement_lease(
    client, pool, monkeypatch, fail
):
    user = await account(client)
    tid = await upload(client, user)
    replacement = None

    async def changed_lease(*args):
        nonlocal replacement
        replacement = dict(
            await pool.fetchrow(
                "UPDATE rm_wb_queue SET started_at=now()+interval '1 second',status='running' WHERE trace_id=$1 RETURNING *",
                tid,
            )
        )
        if fail:
            raise ValueError("Old worker failed")
        return []

    monkeypatch.setattr(legacy, "list_graders", changed_lease)
    await legacy.process_trace(tid)
    assert (
        dict(await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", tid)) == replacement
    )


async def test_a_completed_annotation_resets_the_worker_failure_budget(
    client,
    pool,
    monkeypatch,
    labeler,
):
    user = await account(client)
    tid = await upload(client, user)
    await pool.execute("UPDATE rm_wb_queue SET attempts=12 WHERE trace_id=$1", tid)
    await auto.process_trace(tid)
    row = await pool.fetchrow("SELECT status,attempts FROM rm_wb_queue WHERE trace_id=$1", tid)
    assert row["status"] == "completed" and row["attempts"] == 0

    async def stale(trace_id):
        raise asyncpg.InvalidCachedStatementError(auto.SCHEMA_CACHE_ERROR)

    monkeypatch.setattr(auto, "_read_trace", stale)
    await pool.execute("UPDATE rm_wb_queue SET status='queued' WHERE trace_id=$1", tid)
    await auto.process_trace(tid)
    row = await pool.fetchrow("SELECT status,attempts FROM rm_wb_queue WHERE trace_id=$1", tid)
    assert row["status"] == "queued" and row["attempts"] == 1
