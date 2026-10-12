"""Real log/DB/API transport with stubbed inference; no weights or local ML."""

import json
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from backend.database import get_pool
from backend.services.rm import jobs, scoring_progress
from backend.tasks import reward_models as rm_tasks
from rm_worker import score_run
from rm_worker.progress import PREFIX

from .test_rm_action_scores import request_score, saved_model
from .test_rm_api import REFUND_TRACE, _detail, _import, _register


def event():
    return {
        "stage": "scoring",
        "completed": 4,
        "total": 10,
        "elapsed_seconds": 8,
        "updated_at": datetime.now(UTC).isoformat(),
    }


async def test_scoring_worker_log_uses_scoring_saver(tmp_path, monkeypatch):
    run_id = uuid4()
    directory = tmp_path / str(run_id)
    directory.mkdir()
    (directory / "job.json").write_text('{"kind":"score"}')
    value = event()
    # Execute a tiny Python subprocess, through the real job runner.
    (tmp_path / "fake_score.py").write_text(
        "print(" + repr(PREFIX + json.dumps(value)) + ", flush=True)"
    )
    save = AsyncMock()
    monkeypatch.setattr(scoring_progress, "save", save)
    monkeypatch.setattr(jobs, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("RM_WORKER_PYTHON", sys.executable)
    await jobs.run_worker("fake_score", directory)
    save.assert_awaited_once_with(run_id, value)


async def test_progress_survives_api_polling_and_does_not_update_terminal_runs(client, monkeypatch):
    auth, other = await _register(client), await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    model_id = await saved_model(client, auth, monkeypatch)
    monkeypatch.setattr(rm_tasks.score_trace, "delay", lambda *args: None)
    response = await request_score(client, auth, trace_id, model_id)
    assert response.json()["progress"] is None
    run_id = UUID(response.json()["id"])
    pool = get_pool()
    await pool.execute(
        "UPDATE rm_scoring_runs SET status='running',started_at=now() WHERE id=$1", run_id
    )
    value = event()
    await scoring_progress.save(run_id, value)
    detail = await _detail(client, auth, trace_id)
    assert detail["scoring_runs"][0]["progress"] == value
    assert detail["scoring_runs"][0]["started_at"]
    assert (await client.get(f"/api/v1/rm/traces/{trace_id}", headers=other)).status_code == 404
    await pool.execute("UPDATE rm_scoring_runs SET status='succeeded' WHERE id=$1", run_id)
    await scoring_progress.stage(run_id, "loading")
    assert (await _detail(client, auth, trace_id))["scoring_runs"][0]["progress"] == value


async def test_telemetry_db_failure_does_not_fail_scoring(monkeypatch):
    pool = AsyncMock()
    pool.execute.side_effect = RuntimeError("temporary DB failure")
    monkeypatch.setattr(scoring_progress, "get_pool", lambda: pool)
    await scoring_progress.stage(uuid4(), "starting")


def test_scoring_counts_actions_and_trace_outcomes_together(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "action_reward_stats.json").write_text('{"mean":0,"std":1}')
    events = []

    class Reporter:
        def update(self, stage, completed=0, total=0):
            events.append((stage, completed, total))

    class Model:
        def __init__(self, path):
            assert path == checkpoint

        def score(self, texts, *, on_progress):
            for completed in range(1, len(texts) + 1):
                on_progress(completed)
            return [0.5] * len(texts)

    monkeypatch.setattr(score_run, "Reporter", Reporter)
    monkeypatch.setitem(sys.modules, "rm_worker.scoring", SimpleNamespace(RewardModel=Model))
    monkeypatch.setattr(score_run, "download_model", lambda *args: checkpoint)
    (tmp_path / "job.json").write_text('{"reward_model_key":"saved"}')
    jobs._write_jsonl(
        tmp_path / "action_score_items.jsonl",
        [{"trace_id": "trace", "step_id": str(i), "text": str(i)} for i in range(5)],
    )
    jobs._write_jsonl(tmp_path / "score_items.jsonl", [{"trace_id": "trace", "text": "outcome"}])
    score_run.run(tmp_path)
    assert events[:2] == [("downloading", 0, 0), ("loading", 0, 0)]
    assert [e for e in events if e[0] == "scoring"] == [("scoring", i, 6) for i in range(7)]
    assert events[-1] == ("saving", 0, 0)
    assert len(jobs._read_jsonl(tmp_path / "action_scores.jsonl")) == 5
    assert jobs._read_jsonl(tmp_path / "scores.jsonl") == [{"trace_id": "trace", "score": 0.5}]
