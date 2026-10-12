"""Real DB state transitions, with cloud work stubbed (no local inference)."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from backend import database
from backend.services.rm import evaluator, jobs, training_progress
from backend.tasks import reward_models as tasks
from rm_worker import cloud_training

from .test_rm_datasets import _register, _user_id


async def model(client, pool, status="queued", age=0, progress=None):
    auth = await _register(client)
    owner = await _user_id(client, auth)
    row = await pool.fetchrow(
        """INSERT INTO rm_reward_models(owner_user_id,name,base_model,compute,epochs,max_pairs,
        trace_ids,status,started_at,progress) VALUES($1,'recovery','Qwen/Qwen3-0.6B','modal',1,20,
        ARRAY[gen_random_uuid()],$2,$3,$4) RETURNING id""",
        UUID(owner),
        status,
        datetime.now(UTC) - timedelta(minutes=age),
        progress,
    )
    return auth, row["id"]


async def test_cloud_submission_is_deduplicated_and_progress_keeps_call_id(
    client, pool, monkeypatch
):
    _, mid = await model(client, pool)
    dispatch = Mock(return_value="fc-recovery")
    monkeypatch.setattr(cloud_training, "dispatch", dispatch)
    monkeypatch.setattr(
        jobs, "run_training", AsyncMock(side_effect=AssertionError("No Render training"))
    )
    await tasks.train_reward_model_async(mid)
    await tasks.train_reward_model_async(mid)
    dispatch.assert_called_once_with(str(mid))
    await training_progress.stage(mid, "preparing")
    row = await pool.fetchrow("SELECT status, progress FROM rm_reward_models WHERE id=$1", mid)
    assert row["status"] == "running"
    assert row["progress"]["remote_call_id"] == "fc-recovery"
    assert row["progress"]["stage"] == "preparing"
    await pool.execute("UPDATE rm_reward_models SET status='succeeded' WHERE id=$1", mid)
    await tasks.train_reward_model_async(mid)
    dispatch.assert_called_once()


async def test_dispatch_failure_is_visible_and_old_delivery_does_not_restart_it(
    client, pool, monkeypatch
):
    _, mid = await model(client, pool)
    dispatch = Mock(side_effect=RuntimeError("Cloud submission unavailable"))
    monkeypatch.setattr(cloud_training, "dispatch", dispatch)
    with pytest.raises(RuntimeError, match="Cloud submission unavailable"):
        await tasks.train_reward_model_async(mid)
    await tasks.train_reward_model_async(mid)
    dispatch.assert_called_once()
    row = await pool.fetchrow(
        "SELECT status,error,finished_at FROM rm_reward_models WHERE id=$1", mid
    )
    assert row["status"] == "failed" and row["finished_at"]
    assert row["error"] == "Cloud submission unavailable"


async def test_recovery_expires_interrupted_submissions_and_cloud_timeouts_only(
    client, pool, monkeypatch
):
    _, interrupted = await model(client, pool, "running", age=36)
    _, cloud_timeout = await model(
        client, pool, "running", age=71, progress={"remote_call_id": "fc-old"}
    )
    _, active = await model(
        client, pool, "running", age=40, progress={"remote_call_id": "fc-active"}
    )
    monkeypatch.setattr(evaluator, "schedule_candidate", AsyncMock())
    monkeypatch.setattr(evaluator, "default_evaluator", AsyncMock(return_value=None))
    await evaluator.reconcile()
    rows = {r["id"]: r for r in await pool.fetch("SELECT id,status,error FROM rm_reward_models")}
    assert rows[interrupted]["status"] == rows[cloud_timeout]["status"] == "failed"
    assert "before cloud submission" in rows[interrupted]["error"]
    assert "recovery deadline" in rows[cloud_timeout]["error"]
    assert rows[active]["status"] == "running"


async def test_retry_preserves_model_identity_and_enforces_owner_and_terminal_state(
    client, pool, monkeypatch
):
    auth, mid = await model(client, pool, "failed", progress={"remote_call_id": "fc-old"})
    other = await _register(client)
    delay = Mock()
    monkeypatch.setattr(tasks.train_reward_model, "delay", delay)
    endpoint = f"/api/v1/rm/reward-models/{mid}/retry"
    assert (await client.post(endpoint, headers=other)).status_code == 404
    response = await client.post(endpoint, headers=auth)
    assert response.status_code == 202, response.text
    assert response.json()["id"] == str(mid) and response.json()["status"] == "queued"
    row = await pool.fetchrow("SELECT progress,started_at FROM rm_reward_models WHERE id=$1", mid)
    assert row["progress"] is None and row["started_at"] is None
    delay.assert_called_once_with(str(mid))
    assert (await client.post(endpoint, headers=auth)).status_code == 409


async def test_cloud_preparation_failure_is_persisted_without_render_worker(
    client, pool, monkeypatch
):
    _, mid = await model(client, pool, "running")
    monkeypatch.setattr(database, "init_pool", AsyncMock())
    monkeypatch.setattr(database, "close_db", AsyncMock())
    monkeypatch.setattr(
        jobs, "run_training", AsyncMock(side_effect=ValueError("Invalid comparison"))
    )
    with pytest.raises(ValueError, match="Invalid comparison"):
        await cloud_training.train(str(mid))
    row = await pool.fetchrow("SELECT status,error FROM rm_reward_models WHERE id=$1", mid)
    assert row["status"] == "failed" and row["error"] == "Invalid comparison"


async def test_cloud_cancellation_is_a_visible_failure(client, pool, monkeypatch):
    _, mid = await model(client, pool, "running")
    monkeypatch.setattr(database, "init_pool", AsyncMock())
    monkeypatch.setattr(database, "close_db", AsyncMock())
    monkeypatch.setattr(jobs, "run_training", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await cloud_training.train(str(mid))
    row = await pool.fetchrow(
        "SELECT status,error,finished_at FROM rm_reward_models WHERE id=$1", mid
    )
    assert row["status"] == "failed" and row["finished_at"]
    assert row["error"] == "Cloud training was cancelled or timed out"


@pytest.mark.parametrize("ignore_termination", [False, True])
async def test_cancelling_worker_reaps_its_real_subprocess(
    tmp_path, monkeypatch, ignore_termination
):
    # A tiny sleeping Python child, never a training or inference process.
    directory = tmp_path / str(uuid4())
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps({"kind": "train"}))
    (tmp_path / "tiny_worker.py").write_text(
        "import os, pathlib, signal, sys, time\n"
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if ignore_termination else "")
        + "pathlib.Path(sys.argv[-1], 'pid').write_text(str(os.getpid()))\n"
        + "time.sleep(60)\n"
    )
    monkeypatch.setattr(jobs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(jobs, "WORKER_STOP_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setenv("RM_WORKER_PYTHON", sys.executable)
    task = asyncio.create_task(jobs.run_worker("tiny_worker", directory))
    try:
        async with asyncio.timeout(3):
            while not (directory / "pid").exists():
                await asyncio.sleep(0.01)
        pid = int((directory / "pid").read_text())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
