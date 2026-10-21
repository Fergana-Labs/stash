"""Private scoring dispatch/progress/recovery with real DB and no ML execution."""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from backend.database import get_pool
from backend.services.rm import customer_heads as heads
from backend.services.rm import evaluator, jobs, scoring_progress
from backend.tasks import reward_models as tasks
from rm_worker.progress import PREFIX

from .test_rm_api import REFUND_TRACE, _import
from .test_rm_customer_heads import setup
from .test_rm_scoring_progress import event

pytestmark = pytest.mark.usefixtures("rm_title_generator")


async def private_run(client, monkeypatch):
    auth, _, owner, model_id, _ = await setup(client)
    head = await heads.fit(owner, model_id, "zero-label customer", [])
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    monkeypatch.setattr(tasks.compute_customer_score, "delay", Mock())
    monkeypatch.setattr(tasks.score_trace, "delay", Mock())
    response = await client.post(
        f"/api/v1/rm/traces/{trace_id}/score",
        headers=auth,
        json={"reward_model_id": str(model_id), "customer_head_id": str(head["id"])},
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["id"])
    assert await get_pool().fetchval("SELECT id FROM rm_customer_scoring_runs WHERE id=$1", run_id)
    return auth, owner, model_id, trace_id, run_id


async def test_private_claim_is_atomic_and_duplicate_deliveries_do_not_execute_twice(
    client, monkeypatch
):
    _, _, _, _, run_id = await private_run(client, monkeypatch)
    calls = []

    async def worker(identifier):
        calls.append(identifier)
        assert (
            await get_pool().fetchval(
                "SELECT status FROM rm_customer_scoring_runs WHERE id=$1", identifier
            )
            == "running"
        )
        await asyncio.sleep(0)
        await get_pool().execute(
            "UPDATE rm_customer_scoring_runs SET status='succeeded',finished_at=now() WHERE id=$1",
            identifier,
        )

    monkeypatch.setattr(jobs, "run_customer_scoring", worker)
    await asyncio.gather(
        tasks.compute_customer_score_async(run_id), tasks.compute_customer_score_async(run_id)
    )
    await tasks.compute_customer_score_async(run_id)
    assert calls == [run_id]
    assert await get_pool().fetchval("SELECT count(*) FROM rm_scoring_runs") == 0
    assert await get_pool().fetchval("SELECT count(*) FROM rm_action_scores") == 0


async def test_legacy_global_task_cannot_claim_private_run(client, monkeypatch):
    _, _, _, _, run_id = await private_run(client, monkeypatch)
    global_job, private_job = AsyncMock(), AsyncMock()
    monkeypatch.setattr(jobs, "run_scoring", global_job)
    monkeypatch.setattr(jobs, "run_customer_scoring", private_job)
    await tasks.score_trace_async(run_id)
    await tasks.score_trace_async(run_id)
    global_job.assert_not_awaited()
    private_job.assert_not_awaited()
    assert (
        await get_pool().fetchval("SELECT status FROM rm_customer_scoring_runs WHERE id=$1", run_id)
        == "queued"
    )


async def test_private_task_does_not_claim_or_fail_a_default_run(client, monkeypatch):
    auth, _, model_id, trace_id, private_id = await private_run(client, monkeypatch)
    response = await client.post(
        f"/api/v1/rm/traces/{trace_id}/score",
        headers=auth,
        json={"reward_model_id": str(model_id)},
    )
    assert response.status_code == 202, response.text
    default_id = UUID(response.json()["id"])
    private_job = AsyncMock(side_effect=ValueError("private inference failed"))
    monkeypatch.setattr(jobs, "run_customer_scoring", private_job)
    await tasks.compute_customer_score_async(default_id)
    private_job.assert_not_awaited()
    with pytest.raises(ValueError, match="private inference failed"):
        await tasks.compute_customer_score_async(private_id)
    private = await get_pool().fetchrow(
        "SELECT status,error FROM rm_customer_scoring_runs WHERE id=$1", private_id
    )
    assert private["status"] == "failed" and "private inference failed" in private["error"]
    assert (
        await get_pool().fetchval("SELECT status FROM rm_scoring_runs WHERE id=$1", default_id)
        == "queued"
    )
    assert await get_pool().fetchval("SELECT count(*) FROM rm_action_scores") == 0
    assert await get_pool().fetchval("SELECT count(*) FROM rm_trace_scores") == 0


async def test_private_worker_log_routes_to_private_progress_saver(tmp_path, monkeypatch):
    run_id = uuid4()
    directory = tmp_path / str(run_id)
    directory.mkdir()
    (directory / "job.json").write_text(
        json.dumps({"kind": "score", "customer_head": {"head_id": str(uuid4())}})
    )
    value = event()
    # This trusted tiny subprocess emits telemetry only, never generated code.
    (tmp_path / "fake_private_score.py").write_text(
        "print(" + repr(PREFIX + json.dumps(value)) + ", flush=True)"
    )
    private_save, global_save = AsyncMock(), AsyncMock()
    monkeypatch.setattr(scoring_progress, "save_customer", private_save)
    monkeypatch.setattr(scoring_progress, "save", global_save)
    monkeypatch.setattr(jobs, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("RM_WORKER_PYTHON", sys.executable)
    await jobs.run_worker("fake_private_score", directory)
    private_save.assert_awaited_once_with(run_id, value)
    global_save.assert_not_awaited()


@pytest.mark.parametrize("terminal", ["succeeded", "failed"])
async def test_private_progress_does_not_update_terminal_runs_or_global_rows(
    client, monkeypatch, terminal
):
    _, _, _, _, run_id = await private_run(client, monkeypatch)
    pool = get_pool()
    await pool.execute(
        "UPDATE rm_customer_scoring_runs SET status='running',started_at=now() WHERE id=$1", run_id
    )
    value = event()
    await scoring_progress.save_customer(run_id, value)
    assert (
        await pool.fetchval("SELECT progress FROM rm_customer_scoring_runs WHERE id=$1", run_id)
        == value
    )
    await pool.execute(
        "UPDATE rm_customer_scoring_runs SET status=$2 WHERE id=$1", run_id, terminal
    )
    await scoring_progress.stage(run_id, "saving", customer=True)
    assert (
        await pool.fetchval("SELECT progress FROM rm_customer_scoring_runs WHERE id=$1", run_id)
        == value
    )
    assert await pool.fetchval("SELECT count(*) FROM rm_scoring_runs") == 0


async def test_private_queued_lease_survives_unknown_old_worker_and_redispatches(
    client, monkeypatch
):
    _, _, _, _, run_id = await private_run(client, monkeypatch)
    delay = Mock()
    monkeypatch.setattr(tasks.compute_customer_score, "delay", delay)
    assert await evaluator.reconcile_customer_scores() == 1
    delay.assert_called_once_with(str(run_id))
    assert await evaluator.reconcile_customer_scores() == 0
    # An old worker can discard an unknown task name without changing this
    # private durable row. Once its lease expires, a new worker gets delivery.
    await get_pool().execute(
        "UPDATE rm_customer_scoring_runs SET dispatched_at=now()-interval '2 minutes' WHERE id=$1",
        run_id,
    )
    assert await evaluator.reconcile_customer_scores() == 1
    assert delay.call_count == 2
    assert (
        await get_pool().fetchval("SELECT status FROM rm_customer_scoring_runs WHERE id=$1", run_id)
        == "queued"
    )
    assert await get_pool().fetchval("SELECT count(*) FROM rm_scoring_runs") == 0


async def test_private_dispatch_broker_failure_releases_lease(client, monkeypatch):
    _, _, _, _, run_id = await private_run(client, monkeypatch)
    delay = Mock(side_effect=RuntimeError("broker unavailable"))
    monkeypatch.setattr(tasks.compute_customer_score, "delay", delay)
    assert await evaluator.reconcile_customer_scores() == 1
    assert (
        await get_pool().fetchval(
            "SELECT dispatched_at FROM rm_customer_scoring_runs WHERE id=$1", run_id
        )
        is None
    )
    delay.side_effect = None
    assert await evaluator.reconcile_customer_scores() == 1
    assert delay.call_count == 2


async def test_concurrent_private_sweeps_lease_one_delivery(client, monkeypatch):
    _, _, _, _, run_id = await private_run(client, monkeypatch)
    delay = Mock()
    monkeypatch.setattr(tasks.compute_customer_score, "delay", delay)
    pool = get_pool()
    sweeps = []
    try:
        async with pool.acquire() as conn, conn.transaction():
            # Force both UPDATE statements to take their initial snapshots
            # before either can change the dispatch lease. After release, the
            # losing statement must recheck freshness against the updated row.
            await conn.fetchval(
                "SELECT id FROM rm_customer_scoring_runs WHERE id=$1 FOR UPDATE", run_id
            )
            sweeps = [asyncio.create_task(evaluator.reconcile_customer_scores()) for _ in range(2)]
            waiting = 0
            for _ in range(500):
                waiting = await pool.fetchval(
                    """SELECT count(*) FROM pg_stat_activity
                    WHERE datname=current_database() AND wait_event_type='Lock'
                    AND query LIKE '%rm_customer_scoring_runs%'
                    AND query NOT LIKE '%pg_stat_activity%'"""
                )
                if waiting >= 2:
                    break
                await asyncio.sleep(0.01)
            assert waiting >= 2, "Both dispatch sweeps must wait on the same queued row"
        assert sorted(await asyncio.gather(*sweeps)) == [0, 1]
        delay.assert_called_once_with(str(run_id))
    finally:
        for sweep in sweeps:
            if not sweep.done():
                sweep.cancel()
        await asyncio.gather(*sweeps, return_exceptions=True)


async def test_private_reconcile_fails_only_stale_private_running_jobs(client, monkeypatch):
    auth, _, model_id, trace_id, private_id = await private_run(client, monkeypatch)
    response = await client.post(
        f"/api/v1/rm/traces/{trace_id}/score",
        headers=auth,
        json={"reward_model_id": str(model_id)},
    )
    assert response.status_code == 202
    default_id = UUID(response.json()["id"])
    pool = get_pool()
    for table, run_id in (
        ("rm_scoring_runs", default_id),
        ("rm_customer_scoring_runs", private_id),
    ):
        await pool.execute(
            f"UPDATE {table} SET status='running',started_at=now()-interval '36 minutes' WHERE id=$1",
            run_id,
        )
    assert await evaluator.reconcile_customer_scores() == 0
    row = await pool.fetchrow(
        "SELECT status,error,finished_at FROM rm_customer_scoring_runs WHERE id=$1", private_id
    )
    assert row["status"] == "failed" and row["finished_at"]
    assert "interrupted" in row["error"]
    assert (
        await pool.fetchval("SELECT status FROM rm_scoring_runs WHERE id=$1", default_id)
        == "running"
    )
