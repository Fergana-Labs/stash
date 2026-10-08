"""Learned action scores: training publication, saved-checkpoint inference, and isolation.

All model execution is stubbed; these tests never train or load weights.
"""

import json
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.database import get_pool
from backend.services.rm import datasets, feedback, jobs
from backend.tasks import reward_models as rm_tasks
from rm_worker import evaluation, score_run

from .test_rm_api import REFUND_TRACE, _detail, _import, _register
from .test_rm_datasets import _create_model, _fake_worker, _user_id
from .test_rm_datasets import artifact_dir as artifact_dir

pytestmark = pytest.mark.usefixtures("rm_title_generator")


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def write_scores(directory):
    items = read_rows(directory / "action_score_items.jsonl")
    rows = evaluation.action_score_rows(
        items, [float(i) for i in range(len(items))], {"mean": 0, "std": 1}
    )
    (directory / "action_scores.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return items


async def saved_model(client, auth, monkeypatch, *, action_model=True, compute="local"):
    model_id = await _create_model(client, auth, monkeypatch, compute=compute)
    await get_pool().execute(
        "UPDATE rm_reward_models SET status = 'succeeded', metrics = $2, artifact_key = 'saved/model.tar.gz', finished_at = now() WHERE id = $1",
        model_id,
        {"action_scoring_version": 1} if action_model else {},
    )
    return model_id


async def request_score(client, auth, trace_id, model_id):
    return await client.post(
        f"/api/v1/rm/traces/{trace_id}/score", headers=auth, json={"reward_model_id": model_id}
    )


async def test_action_inputs_end_at_action_and_never_use_future_observations(client):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    steps = (await _detail(client, auth, trace_id))["steps"]
    items = await datasets.action_score_items(await _user_id(client, auth), UUID(trace_id))
    assert [i["step_id"] for i in items] == [steps[2]["id"], steps[4]["id"]]
    assert items[0]["text"].endswith('assistant → lookup_order({"order_id": "1182"})')
    assert "delivered" not in items[0]["text"]
    assert "full refund" not in items[0]["text"]
    assert "delivered" in items[1]["text"]


async def test_training_publishes_learned_scores_without_creating_comments(
    client, monkeypatch, artifact_dir
):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    model_id = await _create_model(client, auth, monkeypatch)

    async def build(*args):
        items = await datasets.action_score_items(await _user_id(client, auth))
        return [
            {
                "trace_id": trace_id,
                "chosen": i["text"],
                "rejected": "alternative",
                "granularity": "action",
            }
            for i in items
        ], []

    monkeypatch.setattr(feedback, "build_feedback_pairs", build)

    def outputs(directory):
        write_scores(directory)
        (directory / "scores.jsonl").write_text("")
        (directory / "result.json").write_text(
            json.dumps({"metrics": {"action_scoring_version": 1}})
        )

    _fake_worker(monkeypatch, outputs)
    await rm_tasks.train_reward_model_async(model_id)
    detail = await _detail(client, auth, trace_id)
    assert len(detail["action_scores"]) == 2
    assert detail["annotations"] == []
    assert {s["reward_model_id"] for s in detail["action_scores"]} == {model_id}
    assert [s["score"] for s in detail["action_scores"]] == [0, 1]


@pytest.mark.parametrize("compute", ["local", "modal"])
async def test_saved_model_scores_trace_and_deduplicates_jobs(
    client, monkeypatch, artifact_dir, compute
):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    model_id = await saved_model(client, auth, monkeypatch, compute=compute)
    dispatched = []
    monkeypatch.setattr(rm_tasks.score_trace, "delay", dispatched.append)
    response = await request_score(client, auth, trace_id, model_id)
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    again = await request_score(client, auth, trace_id, model_id)
    assert again.json()["id"] == run_id
    assert dispatched == [run_id]

    def outputs(directory):
        assert json.loads((directory / "job.json").read_text()) == {
            "kind": "score",
            "reward_model_key": "saved/model.tar.gz",
        }
        assert not (directory / "pairs.jsonl").exists()
        write_scores(directory)

    calls = _fake_worker(monkeypatch, outputs)
    await rm_tasks.score_trace_async(UUID(run_id))
    await rm_tasks.score_trace_async(UUID(run_id))  # duplicate Celery delivery
    assert calls == ["rm_worker.modal_runner" if compute == "modal" else "rm_worker.score_run"]
    detail = await _detail(client, auth, trace_id)
    assert len(detail["action_scores"]) == 2
    assert detail["scoring_runs"][0]["status"] == "succeeded"
    response = await client.post(
        "/api/v1/rm/query",
        headers=auth,
        json={"sql": "SELECT step_index, score, credit FROM action_scores ORDER BY step_index"},
    )
    assert response.status_code == 200, response.text
    assert [row[0] for row in response.json()["rows"]] == [2, 4]
    # Reimport replaces step IDs, so old action scores cannot decorate new actions.
    await _import(client, auth, REFUND_TRACE)
    assert (await _detail(client, auth, trace_id))["action_scores"] == []
    assert (await request_score(client, auth, trace_id, model_id)).json()["id"] != run_id


async def test_ownership_and_legacy_models(client, monkeypatch):
    auth, other = await _register(client), await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    [other_trace] = await _import(client, other, REFUND_TRACE)
    model_id = await saved_model(client, auth, monkeypatch)
    other_model = await saved_model(client, other, monkeypatch)
    legacy = await saved_model(client, auth, monkeypatch, action_model=False)
    assert (await request_score(client, auth, trace_id, other_model)).status_code == 404
    assert (await request_score(client, auth, other_trace, model_id)).status_code == 404
    assert (await request_score(client, auth, trace_id, legacy)).status_code == 422
    response = await client.post(
        "/api/v1/rm/query", headers=other, json={"sql": "SELECT * FROM action_scores"}
    )
    assert response.json()["rows"] == []


@pytest.mark.parametrize("problem", ["missing", "duplicate", "nonfinite", "bounds", "reimport"])
async def test_scoring_failure_is_atomic_and_retryable(client, monkeypatch, artifact_dir, problem):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    model_id = await saved_model(client, auth, monkeypatch)
    monkeypatch.setattr(rm_tasks.score_trace, "delay", lambda *a: None)
    run_id = (await request_score(client, auth, trace_id, model_id)).json()["id"]

    async def worker(module, directory):
        write_scores(directory)
        path = directory / "action_scores.jsonl"
        rows = read_rows(path)
        if problem == "missing":
            rows.pop()
        elif problem == "duplicate":
            rows.append(rows[0])
        elif problem == "nonfinite":
            rows[0]["score"] = float("nan")
        elif problem == "bounds":
            rows[0]["credit"] = 2
        else:
            await _import(client, auth, REFUND_TRACE)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    monkeypatch.setattr(jobs, "run_worker", worker)
    with pytest.raises(ValueError):
        await rm_tasks.score_trace_async(UUID(run_id))
    detail = await _detail(client, auth, trace_id)
    assert detail["action_scores"] == []
    assert detail["scoring_runs"][0]["status"] == "failed"
    assert detail["scoring_runs"][0]["error"]
    assert (await request_score(client, auth, trace_id, model_id)).json()["id"] != run_id


def test_evaluation_does_not_leak_neighboring_actions_or_cross_trace_pairs():
    pairs = [
        {"trace_id": str(i), "granularity": "action", "chosen": f"{i}-{j}"}
        for i in range(20)
        for j in range(3)
    ]
    train, test = evaluation.split_pairs(pairs)
    train_ids, test_ids = {p["trace_id"] for p in train}, {p["trace_id"] for p in test}
    assert train_ids and test_ids and train_ids.isdisjoint(test_ids)
    cross = {"trace_ids": [next(iter(train_ids)), next(iter(test_ids))]}
    new_train, new_test = evaluation.split_pairs([*pairs, cross])
    assert new_train == train and new_test == test
    assert evaluation.split_pairs(pairs) == (train, test)
    assert evaluation.split_pairs(pairs[:3]) == (pairs[:3], [])


def test_action_scale_is_relative_and_validates_model_outputs():
    items = [{"trace_id": "t", "step_id": str(i)} for i in range(3)]
    scores = evaluation.action_score_rows(items, [-2, 0, 2], {"mean": 0, "std": 1})
    assert -1 < scores[0]["credit"] < 0
    assert scores[1]["credit"] == 0
    assert 0 < scores[2]["credit"] < 1
    assert evaluation.reward_stats([-2, 2]) == {"mean": 0, "std": 2}
    with pytest.raises(ValueError):
        evaluation.reward_stats([1, 1])
    with pytest.raises(ValueError):
        evaluation.action_score_rows(items, [0], {"mean": 0, "std": 1})


def test_saved_checkpoint_inference_uses_the_saved_action_scale(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "action_reward_stats.json").write_text('{"mean": 2, "std": 3}')
    texts_seen = []

    class Model:
        def __init__(self, path):
            assert path == checkpoint

        def score(self, texts):
            texts_seen.extend(texts)
            return [2, 5]

    monkeypatch.setitem(sys.modules, "rm_worker.scoring", SimpleNamespace(RewardModel=Model))
    monkeypatch.setattr(score_run, "download_model", lambda key, path: checkpoint)
    (tmp_path / "job.json").write_text('{"kind": "score", "reward_model_key": "saved"}')
    items = [{"trace_id": "trace", "step_id": str(i), "text": f"prefix {i}"} for i in range(2)]
    (tmp_path / "action_score_items.jsonl").write_text("".join(json.dumps(i) + "\n" for i in items))
    score_run.run(tmp_path)
    assert texts_seen == ["prefix 0", "prefix 1"]
    rows = read_rows(tmp_path / "action_scores.jsonl")
    assert rows[0]["credit"] == 0
    assert rows[1]["credit"] == pytest.approx(0.462117)
    assert json.loads((tmp_path / "result.json").read_text()) == {"action_count": 2}


def test_whole_trace_checkpoint_inference_without_action_calibration(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    texts_seen = []

    class Model:
        def __init__(self, path):
            assert path == checkpoint

        def score(self, texts):
            texts_seen.extend(texts)
            return [0.87]

    monkeypatch.setitem(sys.modules, "rm_worker.scoring", SimpleNamespace(RewardModel=Model))
    monkeypatch.setattr(score_run, "download_model", lambda key, path: checkpoint)
    (tmp_path / "job.json").write_text('{"kind": "score", "reward_model_key": "saved"}')
    (tmp_path / "action_score_items.jsonl").write_text("")
    jobs._write_jsonl(
        tmp_path / "score_items.jsonl", [{"trace_id": "trace", "text": "whole recorded trace"}]
    )
    score_run.run(tmp_path)
    assert texts_seen == ["whole recorded trace"]
    assert read_rows(tmp_path / "scores.jsonl") == [{"trace_id": "trace", "score": 0.87}]
    assert read_rows(tmp_path / "action_scores.jsonl") == []
