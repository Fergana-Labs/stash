"""Playground isolation and saved-checkpoint inference; no model weights are loaded."""

import json
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.database import get_pool
from backend.tasks import reward_models as tasks
from rm_worker import playground_run
from rm_worker.context import PREFIX, render_action_input

from .test_rm_action_scores import saved_model
from .test_rm_api import REFUND_TRACE, _import, _register
from .test_rm_datasets import _fake_worker
from .test_rm_datasets import artifact_dir as artifact_dir

pytestmark = pytest.mark.usefixtures("rm_title_generator", "artifact_dir")
INPUT = {"prompt": "Refund the duplicate charge", "responses": ["I refunded it.", "No."]}


async def setup(client, monkeypatch):
    auth = await _register(client)
    await _import(client, auth, REFUND_TRACE)
    model_id = await saved_model(client, auth, monkeypatch)
    dispatched = []
    monkeypatch.setattr(tasks.playground_score, "delay", dispatched.append)
    return auth, model_id, f"/api/v1/rm/reward-models/{model_id}/playground", dispatched


async def test_saved_model_inference_deduplicates_and_never_changes_traces(client, monkeypatch):
    auth, model_id, url, dispatched = await setup(client, monkeypatch)
    response = await client.post(url, headers=auth, json=INPUT)
    assert response.status_code == 202, response.text
    run = response.json()
    assert (await client.post(url, headers=auth, json=INPUT)).json()["id"] == run["id"]
    assert dispatched == [run["id"]]
    other_input = {**INPUT, "prompt": "Another request"}
    assert (await client.post(url, headers=auth, json=other_input)).status_code == 409

    def outputs(directory):
        job = json.loads((directory / "job.json").read_text())
        assert job["kind"] == "playground"
        assert job["reward_model_key"] == "saved/model.tar.gz"
        assert job["input"]["responses"] == INPUT["responses"]
        assert not (directory / "pairs.jsonl").exists()
        (directory / "result.json").write_text('{"scores":[0, -1.25]}')

    calls = _fake_worker(monkeypatch, outputs)
    await tasks.playground_async(UUID(run["id"]))
    await tasks.playground_async(UUID(run["id"]))
    assert calls == [
        "rm_worker.modal_runner"
    ]  # Even a locally trained checkpoint runs in the cloud.
    detail = (await client.get(f"{url}/{run['id']}", headers=auth)).json()
    assert detail["status"] == "succeeded"
    assert detail["scores"] == [0, -1.25]
    history = (await client.get(url, headers=auth)).json()
    assert history["total"] == 1
    assert history["items"][0]["scores"] == [0, -1.25]
    assert "input" not in history["items"][0]
    pool = get_pool()
    for table in ("rm_scoring_runs", "rm_trace_scores", "rm_action_scores", "rm_annotations"):
        assert await pool.fetchval(f"SELECT count(*) FROM {table}") == 0


async def test_owner_isolation_and_model_readiness(client, monkeypatch):
    auth, model_id, url, _ = await setup(client, monkeypatch)
    other = await _register(client)
    run = (await client.post(url, headers=auth, json=INPUT)).json()
    for endpoint in (url, f"{url}/{run['id']}", f"/api/v1/rm/reward-models/{model_id}/examples"):
        assert (await client.get(endpoint, headers=other)).status_code == 404
    assert (await client.post(url, headers=other, json=INPUT)).status_code == 404
    await get_pool().execute(
        "UPDATE rm_reward_models SET status = 'running' WHERE id = $1", model_id
    )
    assert (await client.post(url, headers=auth, json=INPUT)).status_code == 409


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"prompt": " ", "responses": ["yes"]},
        {"prompt": "a", "responses": [" "]},
        {"prompt": "a", "responses": ["a"] * 3},
        {"prompt": "a" * 12001, "responses": ["b"]},
        {"example_index": -1},
        {"example_index": 0, **INPUT},
        {**INPUT, "texts": ["bypass"]},
    ],
)
async def test_rejects_invalid_inputs_without_launching_worker(client, monkeypatch, data):
    auth, _, url, dispatched = await setup(client, monkeypatch)
    assert (await client.post(url, headers=auth, json=data)).status_code == 422
    assert not dispatched


async def test_replays_frozen_pair_including_context_and_pages_examples(client, monkeypatch):
    auth, model_id, url, _ = await setup(client, monkeypatch)
    pair = {
        "chosen": "the complete original chosen input",
        "rejected": "different original context",
        "partition": "eval",
    }
    await get_pool().execute(
        "UPDATE rm_reward_models SET training_pairs = $2 WHERE id = $1", model_id, [pair, pair]
    )
    examples_url = f"/api/v1/rm/reward-models/{model_id}/examples"
    page = (await client.get(examples_url + "?offset=1&limit=1", headers=auth)).json()
    assert page["total"] == 2
    assert page["items"][0]["index"] == 1
    assert page["items"][0]["partition"] == "eval"
    assert (await client.post(url, headers=auth, json={"example_index": 9})).status_code == 404
    run = (await client.post(url, headers=auth, json={"example_index": 1})).json()
    assert run["input"] == {"example_index": 1, "texts": [pair["chosen"], pair["rejected"]]}


@pytest.mark.parametrize("scores", [[1], [True, 1], [float("nan"), 1], "bad"])
async def test_invalid_scores_fail_without_publication_and_allow_retry(client, monkeypatch, scores):
    auth, _, url, _ = await setup(client, monkeypatch)
    run = (await client.post(url, headers=auth, json=INPUT)).json()
    _fake_worker(
        monkeypatch,
        lambda directory: (directory / "result.json").write_text(json.dumps({"scores": scores})),
    )
    with pytest.raises(ValueError, match="invalid reward"):
        await tasks.playground_async(UUID(run["id"]))
    detail = (await client.get(f"{url}/{run['id']}", headers=auth)).json()
    assert detail["status"] == "failed" and detail["scores"] is None
    assert (await client.post(url, headers=auth, json=INPUT)).json()["id"] != run["id"]


async def test_dispatch_failure_timeout_and_missing_worker_can_recover(client, monkeypatch):
    auth, _, url, _ = await setup(client, monkeypatch)

    def fail(*args):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(tasks.playground_score, "delay", fail)
    assert (await client.post(url, headers=auth, json=INPUT)).status_code == 503
    assert (await client.get(url, headers=auth)).json()["items"][0]["status"] == "failed"
    monkeypatch.setattr(tasks.playground_score, "delay", lambda *a: None)
    run = (await client.post(url, headers=auth, json=INPUT)).json()
    await get_pool().execute(
        "UPDATE rm_playground_runs SET created_at = now() - interval '36 minutes' WHERE id = $1",
        run["id"],
    )
    assert (await client.get(f"{url}/{run['id']}", headers=auth)).json()["status"] == "failed"
    await tasks.playground_async(UUID(run["id"]))  # Late queue delivery is a no-op.
    monkeypatch.delenv("RM_WORKER_PYTHON")
    assert (await client.post(url, headers=auth, json=INPUT)).status_code == 503


@pytest.mark.parametrize("version", [1, 2, 3])
def test_worker_uses_checkpoint_format_and_rubric(tmp_path, monkeypatch, version):
    seen = []

    class FakeModel:
        input_version = version
        rubric = ["Respect authorization"]

        def __init__(self, checkpoint):
            assert checkpoint == tmp_path / "checkpoint"

        def score(self, texts):
            seen.extend(texts)
            return [0.0, -0.5]

    monkeypatch.setitem(sys.modules, "rm_worker.scoring", SimpleNamespace(RewardModel=FakeModel))
    monkeypatch.setattr(playground_run, "download_model", lambda key, path: path)
    (tmp_path / "job.json").write_text(
        json.dumps({"reward_model_key": "saved", "input": {**INPUT, "instructions": "Ask first"}})
    )
    playground_run.run(tmp_path)
    if version == 3:
        data = json.loads(seen[0][len(PREFIX) :])
        assert data["rubric"] == "Respect authorization"
        assert data["instructions"] == "Ask first"
        assert data["action"] == "assistant: I refunded it."
    else:
        assert seen[0].endswith("user: Refund the duplicate charge\n\nassistant: I refunded it.")
        assert seen[0].startswith("system: Ask first") == (version == 2)
    assert json.loads((tmp_path / "result.json").read_text())["scores"] == [0, -0.5]


def test_replay_does_not_rewrite_or_share_context_across_candidates():
    a = render_action_input(
        [{"role": "user", "content": "task A"}, {"role": "assistant", "content": "answer A"}]
    )
    b = render_action_input(
        [{"role": "user", "content": "task B"}, {"role": "assistant", "content": "answer B"}]
    )
    assert playground_run.candidate_texts({"texts": [a, b]}, 3, ["different rubric"]) == [a, b]
