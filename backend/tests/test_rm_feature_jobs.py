"""Feature computation is durable, private, and tied to exact worker inputs."""

import json
from uuid import UUID

import pytest

from backend.database import get_pool
from backend.services.rm import customer_heads as heads
from backend.services.rm import feature_jobs, jobs
from backend.tasks import reward_models as tasks

from .test_rm_api import REFUND_TRACE, _import, _register
from .test_rm_customer_heads import manifest, released
from .test_rm_datasets import _user_id
from .test_rm_datasets import artifact_dir as artifact_dir

pytestmark = pytest.mark.usefixtures("rm_title_generator")
URL = "/api/v1/rm/customer-feature-jobs"


async def setup(client):
    auth, other = await _register(client), await _register(client)
    owner = UUID(await _user_id(client, auth))
    model_id = await released(owner)
    return (
        auth,
        other,
        owner,
        {
            "shared_model_id": str(model_id),
            "context": [{"role": "user", "content": "Find the order before refunding it"}],
            "a": {"role": "assistant", "content": "First look up the order"},
            "b": {"role": "assistant", "content": "Refund an invented order"},
        },
    )


def fake_features(monkeypatch, *, wrong_input=False):
    calls = []

    async def worker(module, directory):
        calls.append(module)
        assert module == "rm_worker.modal_runner"
        job = json.loads((directory / "job.json").read_text())
        assert job["kind"] == "basis_features"
        rows = jobs._read_jsonl(directory / "feature_items.jsonl")
        outputs = [
            {
                "id": row["id"],
                "input_digest": "0" * 64 if wrong_input else feature_jobs.text_digest(row["text"]),
                "feature_version": job["feature_version"],
                "manifest_digest": job["manifest_digest"],
                "features": [1.0 if row["id"] == "a" else -1.0, 0.0],
            }
            for row in rows
        ]
        jobs._write_jsonl(directory / "features.jsonl", outputs)
        (directory / "result.json").write_text(json.dumps({"basis_manifest": manifest()}))

    monkeypatch.setattr(jobs, "run_worker", worker)
    return calls


async def test_feature_job_survives_broker_failure_and_creates_private_labelable_pair(
    client, monkeypatch, artifact_dir
):
    auth, other, owner, body = await setup(client)

    def unavailable(*args):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(tasks.compute_customer_features, "delay", unavailable)
    response = await client.post(URL, headers=auth, json=body)
    assert response.status_code == 202, response.text
    job_id = UUID(response.json()["id"])
    assert (await client.get(f"{URL}/{job_id}", headers=other)).status_code == 404
    assert (await client.post(URL, headers=auth, json=body)).json()["id"] == str(job_id)
    dispatched = []
    monkeypatch.setattr(tasks.compute_customer_features, "delay", dispatched.append)
    assert await feature_jobs.reconcile() == 1
    assert dispatched == [str(job_id)]
    calls = fake_features(monkeypatch)
    await feature_jobs.run(job_id)
    await feature_jobs.run(job_id)
    assert len(calls) == 1
    ready = (await client.get(f"{URL}/{job_id}", headers=auth)).json()
    assert (
        ready["status"] == "succeeded" and ready["inputs"]["a"]["content"] == body["a"]["content"]
    )
    pair_id = ready["pair_id"]
    assert (
        await client.post(
            f"/api/v1/rm/customer-heads/pairs/{pair_id}/label", headers=auth, json={"winner": "a"}
        )
    ).status_code == 200
    fit = await client.post(
        "/api/v1/rm/customer-heads/fit",
        headers=auth,
        json={"shared_model_id": body["shared_model_id"], "name": "support", "pair_ids": [pair_id]},
    )
    assert fit.status_code == 201, fit.text
    assert fit.json()["fit"]["pairs"] == 1
    assert "features_a" not in ready and "global_weights" not in fit.json()


async def test_worker_cannot_publish_features_of_another_input(client, monkeypatch, artifact_dir):
    auth, other, _, body = await setup(client)
    monkeypatch.setattr(tasks.compute_customer_features, "delay", lambda *a: None)
    job_id = UUID((await client.post(URL, headers=auth, json=body)).json()["id"])
    fake_features(monkeypatch, wrong_input=True)
    with pytest.raises(ValueError, match="another input"):
        await feature_jobs.run(job_id)
    assert (await client.get(f"{URL}/{job_id}", headers=auth)).json()["status"] == "failed"
    assert not await get_pool().fetchval("SELECT 1 FROM rm_customer_feature_pairs")
    assert (await client.post(f"{URL}/{job_id}/retry", headers=other)).status_code == 404
    retry = await client.post(f"{URL}/{job_id}/retry", headers=auth)
    assert retry.status_code == 202 and retry.json()["attempts"] == 1
    assert (await client.post(f"{URL}/{job_id}/retry", headers=auth)).status_code == 422
    fake_features(monkeypatch)
    await feature_jobs.run(job_id)
    assert (await client.get(f"{URL}/{job_id}", headers=auth)).json()["status"] == "succeeded"


async def test_feature_retries_are_bounded(client, monkeypatch, artifact_dir):
    auth, _, _, body = await setup(client)
    monkeypatch.setattr(tasks.compute_customer_features, "delay", lambda *a: None)
    job_id = UUID((await client.post(URL, headers=auth, json=body)).json()["id"])
    fake_features(monkeypatch, wrong_input=True)
    for attempt in range(1, 4):
        with pytest.raises(ValueError, match="another input"):
            await feature_jobs.run(job_id)
        response = await client.post(f"{URL}/{job_id}/retry", headers=auth)
        assert response.status_code == (202 if attempt < 3 else 422)


async def test_changed_trace_invalidates_feature_publication(client, monkeypatch, artifact_dir):
    auth, _, _, body = await setup(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    body["trace_id"] = trace_id
    monkeypatch.setattr(tasks.compute_customer_features, "delay", lambda *a: None)
    job_id = UUID((await client.post(URL, headers=auth, json=body)).json()["id"])
    fake_features(monkeypatch)
    await get_pool().execute(
        "UPDATE rm_traces SET updated_at=updated_at+interval '1 second' WHERE id=$1", UUID(trace_id)
    )
    with pytest.raises(heads.HeadInvalid, match="Trace changed"):
        await feature_jobs.run(job_id)


async def test_feature_api_rejects_vectors_and_non_agent_alternatives(client, monkeypatch):
    auth, _, _, body = await setup(client)
    monkeypatch.setattr(tasks.compute_customer_features, "delay", lambda *a: None)
    body["features_a"] = [1.0, 0.0]
    assert (await client.post(URL, headers=auth, json=body)).status_code == 422
    del body["features_a"]
    body["a"]["role"] = "user"
    assert (await client.post(URL, headers=auth, json=body)).status_code == 422
