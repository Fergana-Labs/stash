"""Pair construction, GEPA examples, and job result ingestion (fake worker, no torch)."""

import json
import sys
from pathlib import Path

import pytest

from backend.database import get_pool
from backend.services.rm import datasets, feedback, jobs
from backend.tasks import reward_models as rm_tasks

from .test_rm_api import (
    GREETING_TRACE,
    REFUND_TRACE,
    _all_trace_ids,
    _annotate,
    _detail,
    _import,
    _register,
    _trainable_labels,
)

pytestmark = pytest.mark.usefixtures("rm_title_generator")


@pytest.fixture(autouse=True)
def no_feedback_inference(monkeypatch):
    monkeypatch.setenv("RM_COMPUTE", "local")

    async def extract(steps, evidence):
        return feedback.Extraction(feedback=[])

    monkeypatch.setattr(feedback, "extract_preferences", extract)


async def _user_id(client, auth) -> str:
    return (await client.get("/api/v1/users/me", headers=auth)).json()["id"]


async def _all_pairs(client, auth, max_pairs: int = datasets.DEFAULT_MAX_PAIRS) -> list[dict]:
    owner = await _user_id(client, auth)
    return await datasets.build_pairs(owner, await datasets.all_trace_ids(owner), max_pairs)


def _trace(external_id: str, answer: str) -> dict:
    return {
        "id": external_id,
        "steps": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": f"question {external_id}"},
            {"role": "assistant", "content": answer},
        ],
    }


def test_render_skips_system_and_shows_tool_calls():
    steps = [
        {"role": "system", "content": "Be brief.", "tool_name": None, "tool_input": None},
        {"role": "user", "content": "hi", "tool_name": None, "tool_input": None},
        {
            "role": "assistant",
            "content": "Checking.",
            "tool_name": "lookup",
            "tool_input": {"id": 1},
        },
    ]
    assert (
        datasets.render_steps(steps)
        == 'user: hi\n\nassistant: Checking.\nassistant → lookup({"id": 1})'
    )


async def test_ratings_collapse_per_target(client):
    """Disagreeing labels cancel out; a net-positive target is chosen."""
    auth = await _register(client)
    a, b, c = await _import(client, auth, _trace("a", "A"), _trace("b", "B"), _trace("c", "C"))
    for rating in (1, 1, -1):
        await _annotate(client, auth, a, rating=rating)
    for rating in (1, -1):
        await _annotate(client, auth, b, rating=rating)  # sums to zero: skipped
    await _annotate(client, auth, c, rating=-1)

    pairs = await _all_pairs(client, auth)
    assert len(pairs) == 1
    assert pairs == [
        {
            "chosen": "user: question a\n\nassistant: A",
            "rejected": "user: question c\n\nassistant: C",
        }
    ]


async def test_step_targets_render_the_prefix_and_never_pair_with_traces(client):
    auth = await _register(client)
    [refund_id] = await _import(client, auth, REFUND_TRACE)
    steps = (await _detail(client, auth, refund_id))["steps"]
    await _annotate(client, auth, refund_id, step_id=steps[2]["id"], rating=1)
    await _annotate(client, auth, refund_id, step_id=steps[4]["id"], rating=-1)
    [greeting_id] = await _import(client, auth, GREETING_TRACE)
    await _annotate(client, auth, greeting_id, rating=1)  # trace-level, no trace-level partner

    pairs = await _all_pairs(client, auth)
    assert len(pairs) == 1
    chosen, rejected = pairs[0]["chosen"], pairs[0]["rejected"]
    # The good step is judged in context of what came before it, not after.
    assert chosen.endswith('assistant → lookup_order({"order_id": "1182"})')
    assert "delivered" not in chosen
    assert rejected.startswith(chosen)
    assert rejected.endswith("assistant: Sure! I've issued a full refund to your card.")


async def test_pairs_are_shuffled_deterministically_and_capped(client):
    auth = await _register(client)
    ids = await _import(client, auth, *[_trace(str(i), f"answer {i}") for i in range(6)])
    for i, trace_id in enumerate(ids):
        await _annotate(client, auth, trace_id, rating=1 if i < 3 else -1)

    everything = await _all_pairs(client, auth)
    assert len(everything) == 9
    capped = await _all_pairs(client, auth, max_pairs=4)
    assert capped == everything[:4]
    assert await _all_pairs(client, auth) == everything


async def test_gepa_examples_replay_the_input_and_carry_unflagged_comments(client):
    auth = await _register(client)
    refund_id, greeting_id = await _import(client, auth, REFUND_TRACE, GREETING_TRACE)
    await _annotate(client, auth, refund_id, comment="Check the refund policy first")
    wrong = await _annotate(client, auth, refund_id, rating=1, comment="Great answer")
    await client.patch(
        f"/api/v1/rm/annotations/{wrong['id']}", json={"label_error": True}, headers=auth
    )
    await _annotate(client, auth, greeting_id, rating=1)

    owner = await _user_id(client, auth)
    examples = await datasets.gepa_examples(owner, await datasets.all_trace_ids(owner))
    by_trace = {example["trace_id"]: example for example in examples}
    # The trace's own system prompt travels separately: the worker appends the skill to it.
    # The input stops at the first assistant turn.
    assert by_trace[refund_id] == {
        "trace_id": refund_id,
        "system": "You are a support agent.",
        "messages": [{"role": "user", "content": "I want a refund for order 1182"}],
        "feedback": ["Check the refund policy first"],
    }
    assert by_trace[greeting_id] == {
        "trace_id": greeting_id,
        "system": None,
        "messages": [{"role": "user", "content": "hi there"}],
        "feedback": [],
    }


@pytest.fixture
def artifact_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("RM_WORKER_PYTHON", sys.executable)
    return tmp_path


def _fake_worker(monkeypatch, write_outputs):
    calls = []

    async def fake_run_worker(module: str, directory: Path) -> None:
        calls.append(module)
        write_outputs(directory)

    monkeypatch.setattr(jobs, "run_worker", fake_run_worker)
    return calls


async def _create_model(client, auth, monkeypatch, compute="local", trace_ids=None) -> str:
    """A queued model trained on `trace_ids`, or on every trace the owner has."""
    monkeypatch.setattr(rm_tasks.train_reward_model, "delay", lambda *a: None)
    monkeypatch.setenv("RM_COMPUTE", compute)
    if trace_ids is None:
        trace_ids = await _all_trace_ids(client, auth)
    resp = await client.post(
        "/api/v1/rm/reward-models",
        json={"name": "rm", "trace_ids": trace_ids},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _labelled_pair(client, auth) -> tuple[str, str]:
    """Two + traces and one −: the smallest label set the worker can train on (2 pairs)."""
    good, _, bad = await _trainable_labels(client, auth)
    return good, bad


async def test_training_ingests_metrics_and_scores(client, monkeypatch, artifact_dir):
    auth = await _register(client)
    good, bad = await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)
    owner = await _user_id(client, auth)
    metrics = {
        "train_pairs": 1,
        "eval_pairs": 1,
        "eval_accuracy": 1.0,
        "final_loss": 0.3,
        "epochs": 1,
        "device": "cpu",
        "seconds": 1.5,
    }

    def write_outputs(directory: Path) -> None:
        job = json.loads((directory / "job.json").read_text())
        assert job == {
            "kind": "train",
            "base_model": "Qwen/Qwen3-0.6B",
            "epochs": 1,
            "compute": "local",
            "artifact_key": f"reward-models/{owner}/{model_id}.tar.gz",
        }
        assert len((directory / "pairs.jsonl").read_text().splitlines()) == 2
        items = [
            json.loads(line) for line in (directory / "score_items.jsonl").read_text().splitlines()
        ]
        (directory / "result.json").write_text(json.dumps({"metrics": metrics}))
        (directory / "scores.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "trace_id": item["trace_id"],
                        "score": 2.0 if item["trace_id"] == good else -2.0,
                    }
                )
                + "\n"
                for item in items
            )
        )

    calls = _fake_worker(monkeypatch, write_outputs)
    await rm_tasks.train_reward_model_async(model_id)

    assert calls == ["rm_worker.train"]
    model = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert model["status"] == "succeeded"
    assert model["num_pairs"] == 2
    assert model["metrics"] == metrics
    assert model["started_at"] and model["finished_at"]
    assert [s["score"] for s in (await _detail(client, auth, good))["scores"]] == [2.0]
    assert [s["score"] for s in (await _detail(client, auth, bad))["scores"]] == [-2.0]
    listing = (await client.get("/api/v1/rm/traces", headers=auth)).json()["traces"]
    latest = {t["id"]: t["latest_score"] for t in listing}
    assert latest[good] == {"reward_model_id": model_id, "reward_model_name": "rm", "score": 2.0}


async def test_modal_compute_runs_the_modal_module(client, monkeypatch, artifact_dir):
    auth = await _register(client)
    await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch, compute="modal")

    def write_outputs(directory: Path) -> None:
        (directory / "result.json").write_text(json.dumps({"metrics": {}}))
        (directory / "scores.jsonl").write_text("")

    calls = _fake_worker(monkeypatch, write_outputs)
    await rm_tasks.train_reward_model_async(model_id)
    assert calls == ["rm_worker.modal_runner"]


async def test_labels_flagged_while_queued_fail_the_job_before_the_worker(
    client, monkeypatch, artifact_dir
):
    """The create-time check can go stale; the job re-checks before downloading a model."""
    auth = await _register(client)
    good, bad = await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)
    [negative] = (await _detail(client, auth, bad))["annotations"]
    await client.patch(
        f"/api/v1/rm/annotations/{negative['id']}", json={"label_error": True}, headers=auth
    )
    calls = _fake_worker(monkeypatch, lambda directory: None)

    with pytest.raises(datasets.NotEnoughPairs):
        await rm_tasks.train_reward_model_async(model_id)

    assert calls == []
    model = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert model["status"] == "failed"
    assert "0 preference pairs; need at least 2" in model["error"]
    assert "Automatic assessment could not establish enough grounded comparisons" in model["error"]
    assert model["metrics"] is None


async def test_worker_crash_stores_the_log_tail(client, monkeypatch, artifact_dir):
    """A real subprocess: the user sees why the worker died, not just 'failed'."""
    auth = await _register(client)
    await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)

    # The backend's venv has no rm_worker.modal_runner deps; any missing module
    # exercises the same path. Point the module at one that cannot exist.
    real_run_worker = jobs.run_worker

    async def run_missing_module(module: str, directory: Path) -> None:
        await real_run_worker("rm_worker.does_not_exist", directory)

    monkeypatch.setattr(jobs, "run_worker", run_missing_module)
    with pytest.raises(jobs.WorkerFailed):
        await rm_tasks.train_reward_model_async(model_id)

    model = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert model["status"] == "failed"
    assert "No module named rm_worker.does_not_exist" in model["error"]
    assert (artifact_dir / model_id / "worker.log").exists()


async def test_missing_env_var_is_named_in_the_error(client, monkeypatch, artifact_dir):
    auth = await _register(client)
    await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)
    monkeypatch.delenv("RM_WORKER_PYTHON")

    with pytest.raises(RuntimeError):
        await rm_tasks.train_reward_model_async(model_id)

    model = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert model["status"] == "failed"
    assert "RM_WORKER_PYTHON" in model["error"]


async def test_gepa_run_ingests_the_best_skill(client, monkeypatch, artifact_dir):
    auth = await _register(client)
    await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)
    await get_pool().execute(
        "UPDATE rm_reward_models SET status = 'succeeded', artifact_key = 'test/model.tar.gz' WHERE id = $1::uuid",
        model_id,
    )
    monkeypatch.setattr(rm_tasks.run_gepa, "delay", lambda *a: None)
    resp = await client.post(
        "/api/v1/rm/gepa-runs",
        json={
            "reward_model_id": model_id,
            "task_model": "openai/qwen3-8b",
            "task_api_base": "http://localhost:8000/v1",
            "reflection_model": "anthropic/claude-sonnet-5",
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    run_id = run["id"]
    # The worker names the skill; until it succeeds there is no name.
    assert (run["skill_name"], run["skill_description"]) == (None, None)
    header = "---\nname: short-answers\ndescription: Use when answering yes/no questions.\n---\n\n"
    seed_skill = header + "Use when answering yes/no questions."
    best_skill = header + "Answer in one sentence, then offer help."
    candidates = [{"skill": seed_skill, "score": 0.1}, {"skill": best_skill, "score": 0.9}]
    skill_url = f"/api/v1/rm/gepa-runs/{run_id}/skill"
    assert (await client.get(skill_url, headers=auth)).status_code == 404  # not finished

    def write_outputs(directory: Path) -> None:
        job = json.loads((directory / "job.json").read_text())
        assert job == {
            "kind": "gepa",
            "reward_model_key": "test/model.tar.gz",
            "task_model": "openai/qwen3-8b",
            "task_api_base": "http://localhost:8000/v1",
            "reflection_model": "anthropic/claude-sonnet-5",
            "max_metric_calls": 40,
        }
        assert len((directory / "gepa_examples.jsonl").read_text().splitlines()) == 3
        (directory / "result.json").write_text(
            json.dumps(
                {
                    "skill_name": "short-answers",
                    "skill_description": "Use when answering yes/no questions.",
                    "best_skill": best_skill,
                    "best_score": 0.9,
                    "seed_skill": seed_skill,
                    "seed_score": 0.1,
                    "candidates": candidates,
                }
            )
        )

    calls = _fake_worker(monkeypatch, write_outputs)
    await rm_tasks.run_gepa_async(run_id)

    assert calls == ["rm_worker.gepa_run"]
    run = (await client.get(f"/api/v1/rm/gepa-runs/{run_id}", headers=auth)).json()
    assert run["status"] == "succeeded"
    assert run["skill_name"] == "short-answers"
    assert run["skill_description"] == "Use when answering yes/no questions."
    assert (run["best_skill"], run["best_score"]) == (best_skill, 0.9)
    assert (run["seed_skill"], run["seed_score"]) == (seed_skill, 0.1)
    assert run["candidates"] == candidates
    assert "owner_user_id" not in run

    resp = await client.get(skill_url, headers=auth)
    assert resp.status_code == 200
    assert resp.text == best_skill
    assert resp.headers["content-type"].startswith("text/markdown")
    assert resp.headers["content-disposition"] == 'attachment; filename="SKILL.md"'
    intruder = await _register(client)
    assert (await client.get(skill_url, headers=intruder)).status_code == 404


async def test_scores_from_unfinished_models_are_not_shown(client, monkeypatch):
    """A model still running (or that failed) hasn't earned a place next to the trace."""
    auth = await _register(client)
    trace_id, _ = await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)
    await get_pool().execute(
        "UPDATE rm_reward_models SET status = 'running' WHERE id = $1::uuid", model_id
    )
    await get_pool().execute(
        "INSERT INTO rm_trace_scores (reward_model_id, trace_id, score) "
        "VALUES ($1::uuid, $2::uuid, 1.0)",
        model_id,
        trace_id,
    )

    detail = await _detail(client, auth, trace_id)
    assert detail["scores"] == []
    assert detail["latest_score"] is None


async def test_bad_worker_output_leaves_no_half_succeeded_model(client, monkeypatch, artifact_dir):
    """Metrics without scores (or the reverse) would show a model as trained when it isn't."""
    auth = await _register(client)
    good, _ = await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)

    def write_outputs(directory: Path) -> None:
        (directory / "result.json").write_text(json.dumps({"metrics": {"eval_accuracy": 1.0}}))
        (directory / "scores.jsonl").write_text(json.dumps({"trace_id": good}) + "\n")  # no score

    _fake_worker(monkeypatch, write_outputs)
    with pytest.raises(KeyError):
        await rm_tasks.train_reward_model_async(model_id)

    model = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert model["status"] == "failed"
    assert model["metrics"] is None
    count = await get_pool().fetchval(
        "SELECT count(*) FROM rm_trace_scores WHERE reward_model_id = $1::uuid", model_id
    )
    assert count == 0


async def test_trained_weights_download_is_owned_and_uses_durable_storage(client, monkeypatch):
    auth = await _register(client)
    await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)
    url = f"/api/v1/rm/reward-models/{model_id}/weights"
    assert (await client.get(url, headers=auth)).status_code == 404
    await get_pool().execute(
        "UPDATE rm_reward_models SET status='succeeded', artifact_key='test/model.tar.gz' WHERE id=$1::uuid",
        model_id,
    )
    calls = []

    def signed_download(key, filename):
        calls.append((key, filename))
        return "https://storage.example/checkpoint?expires=300"

    monkeypatch.setattr("backend.routers.reward_models.download_url", signed_download)
    intruder = await _register(client)
    assert (await client.get(url, headers=intruder)).status_code == 404
    assert calls == []
    response = await client.get(url, headers=auth)
    assert response.status_code == 200
    assert response.json() == {"url": "https://storage.example/checkpoint?expires=300"}
    assert calls == [("test/model.tar.gz", "rm-reward-model.tar.gz")]


async def test_one_button_skill_run_uses_the_documented_defaults(client, monkeypatch):
    """The UI's one button sends only the reward model."""
    auth = await _register(client)
    await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)
    await get_pool().execute(
        "UPDATE rm_reward_models SET status = 'succeeded', artifact_key = 'test/model.tar.gz' WHERE id = $1::uuid",
        model_id,
    )
    queued = []
    monkeypatch.setattr(rm_tasks.run_gepa, "delay", queued.append)

    resp = await client.post(
        "/api/v1/rm/gepa-runs", json={"reward_model_id": model_id}, headers=auth
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["task_model"] == "anthropic/claude-haiku-4-5"
    assert run["reflection_model"] == "anthropic/claude-sonnet-5"
    assert run["max_metric_calls"] == 40
    assert run["task_api_base"] is None
    assert queued == [run["id"]]


async def test_training_and_skills_use_only_the_selected_traces(client, monkeypatch, artifact_dir):
    """Pairs and GEPA examples come from the selection; scoring still covers every trace."""
    auth = await _register(client)
    selected = await _trainable_labels(client, auth)
    [outside] = await _import(client, auth, _trace("outside", "Maybe"))
    await _annotate(client, auth, outside, rating=-1, comment="hedging")
    model_id = await _create_model(client, auth, monkeypatch, trace_ids=selected)
    seen = {}

    def write_training_outputs(directory: Path) -> None:
        pairs = (directory / "pairs.jsonl").read_text()
        items = [
            json.loads(line) for line in (directory / "score_items.jsonl").read_text().splitlines()
        ]
        seen["pairs_mention_outside"] = "Maybe" in pairs
        seen["scored"] = {item["trace_id"] for item in items}
        (directory / "result.json").write_text(json.dumps({"metrics": {}}))
        (directory / "scores.jsonl").write_text("")

    _fake_worker(monkeypatch, write_training_outputs)
    await rm_tasks.train_reward_model_async(model_id)
    assert seen["pairs_mention_outside"] is False
    assert seen["scored"] == set(selected) | {outside}

    monkeypatch.setattr(rm_tasks.run_gepa, "delay", lambda *a: None)
    resp = await client.post(
        "/api/v1/rm/gepa-runs", json={"reward_model_id": model_id}, headers=auth
    )
    run_id = resp.json()["id"]

    def write_gepa_outputs(directory: Path) -> None:
        lines = (directory / "gepa_examples.jsonl").read_text().splitlines()
        seen["examples"] = {json.loads(line)["trace_id"] for line in lines}
        raise RuntimeError("stop after inspecting the inputs")

    _fake_worker(monkeypatch, write_gepa_outputs)
    with pytest.raises(RuntimeError):
        await rm_tasks.run_gepa_async(run_id)
    assert seen["examples"] == set(selected)


async def test_selected_trace_deleted_before_the_job_drops_out(client, monkeypatch, artifact_dir):
    auth = await _register(client)
    good, bad = await _labelled_pair(client, auth)
    model_id = await _create_model(client, auth, monkeypatch)
    resp = await client.delete(f"/api/v1/rm/traces/{bad}", headers=auth)
    assert resp.status_code == 204
    calls = _fake_worker(monkeypatch, lambda directory: None)

    with pytest.raises(datasets.NotEnoughPairs):
        await rm_tasks.train_reward_model_async(model_id)

    assert calls == []
    model = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert model["error"].startswith("the selected traces have 0 preference pairs")
