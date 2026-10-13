"""Eager scoring/cache contracts with real Postgres and stubbed GPU execution."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from backend import database
from backend.services.rm import evaluator, precompute
from backend.tasks import reward_models as tasks
from rm_worker import cloud_scoring

from .test_rm_action_scores import request_score
from .test_rm_api import _detail, _import, _register
from .test_rm_datasets import _trace, _user_id

pytestmark = pytest.mark.usefixtures("rm_title_generator")


async def ready(client, pool, auth, *, status="succeeded", compute="modal"):
    owner = UUID(await _user_id(client, auth))
    mid = await pool.fetchval(
        """INSERT INTO rm_reward_models(owner_user_id,name,base_model,compute,epochs,max_pairs,
        trace_ids,status,metrics,artifact_key,finished_at)
        VALUES($1,'eager','Qwen/Qwen3-0.6B',$2,1,20,ARRAY[gen_random_uuid()],$3,$4,'saved/model.tar.gz',now()) RETURNING id""",
        owner,
        compute,
        status,
        {"action_scoring_version": 1},
    )
    return mid, owner


async def idle(pool):
    await pool.execute("UPDATE rm_traces SET updated_at=now()-interval '31 seconds'")


async def test_scheduler_is_bounded_deduplicated_owned_and_skips_unready_models(client, pool):
    auth, other = await _register(client), await _register(client)
    ids = await _import(client, auth, *[_trace(str(i), "answer") for i in range(20)])
    await _import(client, other, _trace("private", "other owner's trace"))
    first, owner = await ready(client, pool, auth)
    second, _ = await ready(client, pool, auth)
    third, _ = await ready(client, pool, auth)
    failed, _ = await ready(client, pool, auth, status="failed")
    local, _ = await ready(client, pool, auth, compute="local")
    await idle(pool)
    await precompute.schedule()
    await precompute.schedule()
    batches = await pool.fetch("SELECT * FROM rm_scoring_batches")
    assert len(batches) == 2
    assert {b["reward_model_id"] for b in batches} <= {first, second, third}
    assert not {b["reward_model_id"] for b in batches} & {failed, local}
    rows = await pool.fetch("SELECT * FROM rm_scoring_runs")
    assert len(rows) == 16
    assert all(r["owner_user_id"] == owner and str(r["trace_id"]) in ids for r in rows)
    assert all(r["automatic"] and r["batch_id"] for r in rows)
    # Manual dispatch cannot steal a run from its checkpoint-reusing batch.
    await tasks.score_trace_async(rows[0]["id"])
    assert (
        await pool.fetchval("SELECT status FROM rm_scoring_runs WHERE id=$1", rows[0]["id"])
        == "queued"
    )


async def test_idle_debounce_and_retry_ceiling(client, pool):
    auth = await _register(client)
    [tid] = await _import(client, auth, _trace("one", "answer"))
    await ready(client, pool, auth)
    await precompute.schedule()
    assert await pool.fetchval("SELECT count(*) FROM rm_scoring_batches") == 0
    await idle(pool)
    for _ in range(3):
        await precompute.schedule()
        bid = await pool.fetchval("SELECT id FROM rm_scoring_batches WHERE status='queued'")
        assert bid
        await precompute.fail(bid, "transient error")
    await precompute.schedule()
    assert await pool.fetchval("SELECT count(*) FROM rm_scoring_batches WHERE status='queued'") == 0
    # A changed trace gets a fresh retry allowance.
    await _import(client, auth, _trace("one", "changed answer"))
    await idle(pool)
    await precompute.schedule()
    assert await pool.fetchval("SELECT count(*) FROM rm_scoring_batches WHERE status='queued'") == 1
    assert (await _detail(client, auth, tid))["scoring_runs"][0]["status"] == "queued"


async def test_detached_dispatch_is_idempotent_and_recovers_failures(client, pool, monkeypatch):
    auth = await _register(client)
    await _import(client, auth, _trace("one", "answer"))
    await ready(client, pool, auth)
    await idle(pool)
    await precompute.schedule()
    bid = await pool.fetchval("SELECT id FROM rm_scoring_batches")
    dispatch = Mock(return_value="fc-background")
    monkeypatch.setattr(cloud_scoring, "dispatch", dispatch)
    await tasks.score_batch_async(bid)
    await tasks.score_batch_async(bid)
    dispatch.assert_called_once_with(str(bid))
    assert (
        await pool.fetchval("SELECT remote_call_id FROM rm_scoring_batches WHERE id=$1", bid)
        == "fc-background"
    )
    await pool.execute(
        "UPDATE rm_scoring_batches SET started_at=now()-interval '36 minutes' WHERE id=$1", bid
    )
    monkeypatch.setattr(tasks.score_batch, "delay", Mock())
    await precompute.reconcile()
    assert await pool.fetchval("SELECT status FROM rm_scoring_batches WHERE id=$1", bid) == "failed"
    assert (
        await pool.fetchval("SELECT status FROM rm_scoring_runs WHERE batch_id=$1", bid) == "failed"
    )
    next_id = await pool.fetchval("SELECT id FROM rm_scoring_batches WHERE status='queued'")
    dispatch.side_effect = RuntimeError("broker/cloud outage")
    with pytest.raises(RuntimeError):
        await tasks.score_batch_async(next_id)
    assert (
        await pool.fetchval("SELECT status FROM rm_scoring_runs WHERE batch_id=$1", next_id)
        == "failed"
    )


async def test_batch_loads_checkpoint_once_publishes_each_trace_and_run_reuses_cache(
    client, pool, monkeypatch, tmp_path
):
    auth, other = await _register(client), await _register(client)
    ids = await _import(client, auth, _trace("one", "a"), _trace("two", "b"))
    mid, _ = await ready(client, pool, auth)
    await idle(pool)
    await precompute.schedule()
    bid = await pool.fetchval("SELECT id FROM rm_scoring_batches")
    await pool.execute(
        "UPDATE rm_scoring_batches SET status='running',started_at=now() WHERE id=$1", bid
    )
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "action_reward_stats.json").write_text('{"mean":0,"std":1}')
    downloaded = Mock(return_value=checkpoint)
    loaded = []
    texts_seen = []
    # Ask for the second trace while it is still queued for precomputation.
    requested = await request_score(client, auth, ids[1], str(mid))
    assert requested.json()["requested_at"]

    class Model:
        def __init__(self, path):
            loaded.append(path)

        def score(self, texts, *, on_progress):
            texts_seen.extend(texts)
            on_progress(len(texts))
            return [0.5] * len(texts)

    monkeypatch.setitem(sys.modules, "rm_worker.scoring", SimpleNamespace(RewardModel=Model))
    from rm_worker import artifacts

    monkeypatch.setattr(artifacts, "download_model", downloaded)
    monkeypatch.setattr(database, "init_pool", AsyncMock())
    monkeypatch.setattr(database, "close_db", AsyncMock())
    await cloud_scoring.score(str(bid))
    assert downloaded.call_count == 1 and loaded == [checkpoint]
    assert texts_seen[0].endswith("assistant: b")
    assert (
        await pool.fetchval("SELECT status FROM rm_scoring_batches WHERE id=$1", bid) == "succeeded"
    )
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_scoring_runs WHERE batch_id=$1 AND status='succeeded'", bid
        )
        == 2
    )
    dispatch = Mock()
    monkeypatch.setattr(tasks.score_trace, "delay", dispatch)
    for tid in ids:
        detail = await _detail(client, auth, tid)
        assert len(detail["action_scores"]) == 1
        response = await request_score(client, auth, tid, str(mid))
        assert response.status_code == 202 and response.json()["status"] == "succeeded"
        assert response.json()["id"] == detail["scoring_runs"][0]["id"]
        assert (await request_score(client, other, tid, str(mid))).status_code == 404
    dispatch.assert_not_called()
    assert await pool.fetchval("SELECT count(*) FROM rm_scoring_runs") == 2
    # Shared auto-score reconciliation also consumes a valid cache hit, instead
    # of keeping an already-scored trace at the front of its queue forever.
    await pool.execute(
        "INSERT INTO rm_evaluator_registry(singleton,model_id) VALUES(true,$1) ON CONFLICT(singleton) DO UPDATE SET model_id=$1",
        mid,
    )
    await pool.execute(
        "INSERT INTO rm_auto_scores(trace_id) VALUES($1) ON CONFLICT(trace_id) DO NOTHING",
        UUID(ids[0]),
    )
    _, created = await evaluator.enqueue_score(
        UUID(await _user_id(client, auth)), UUID(ids[0]), mid, automatic=True
    )
    assert not created
    assert not await pool.fetchval("SELECT 1 FROM rm_auto_scores WHERE trace_id=$1", UUID(ids[0]))
    await precompute.schedule()
    assert await pool.fetchval("SELECT count(*) FROM rm_scoring_batches") == 1
    [new_id] = await _import(client, auth, _trace("three", "new trace"))
    await pool.execute(
        "UPDATE rm_traces SET updated_at=now()-interval '31 seconds' WHERE id=$1", UUID(new_id)
    )
    await precompute.schedule()
    newly_queued = await pool.fetch("SELECT trace_id FROM rm_scoring_runs WHERE status='queued'")
    assert {str(row["trace_id"]) for row in newly_queued} == {new_id}
    # A newer checkpoint invalidates cached results even on unchanged traces.
    await pool.execute("UPDATE rm_reward_models SET finished_at=now() WHERE id=$1", mid)
    fresh = await request_score(client, auth, ids[0], str(mid))
    assert fresh.json()["status"] == "queued"
    dispatch.assert_called_once()


async def test_backfill_covers_every_trace_and_isolates_per_trace_failures(
    client, pool, monkeypatch, tmp_path
):
    auth = await _register(client)
    ids = await _import(client, auth, *[_trace(str(i), "answer") for i in range(20)])
    [bad] = await _import(client, auth, _trace("bad", "UNSCORABLE"))
    await ready(client, pool, auth)
    await idle(pool)
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "action_reward_stats.json").write_text('{"mean":0,"std":1}')
    loaded = []

    class Model:
        def __init__(self, path):
            loaded.append(path)

        def score(self, texts, *, on_progress):
            if any("UNSCORABLE" in text for text in texts):
                raise ValueError("This trace failed inference")
            on_progress(len(texts))
            return [0.5] * len(texts)

    monkeypatch.setitem(sys.modules, "rm_worker.scoring", SimpleNamespace(RewardModel=Model))
    from rm_worker import artifacts

    monkeypatch.setattr(artifacts, "download_model", lambda *args: checkpoint)
    monkeypatch.setattr(database, "init_pool", AsyncMock())
    monkeypatch.setattr(database, "close_db", AsyncMock())
    for _ in range(6):
        await precompute.schedule()
        bid = await pool.fetchval("SELECT id FROM rm_scoring_batches WHERE status='queued'")
        if bid is None:
            break
        await pool.execute(
            "UPDATE rm_scoring_batches SET status='running',started_at=now() WHERE id=$1", bid
        )
        await cloud_scoring.score(str(bid))
    succeeded = await pool.fetch("SELECT trace_id FROM rm_scoring_runs WHERE status='succeeded'")
    assert {str(row["trace_id"]) for row in succeeded} == set(ids)
    assert await pool.fetchval("SELECT count(*) FROM rm_action_scores") == 20
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_scoring_runs WHERE trace_id=$1 AND status='failed'", UUID(bad)
        )
        == 3
    )
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_scoring_runs WHERE status IN ('queued','running')"
        )
        == 0
    )
    assert len(loaded) == await pool.fetchval("SELECT count(*) FROM rm_scoring_batches")
    assert 3 <= len(loaded) <= 5
