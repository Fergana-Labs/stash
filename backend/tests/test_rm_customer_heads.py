"""Real database/API isolation and feature/head invalidation, without ML compute."""

import json
from uuid import UUID

import pytest

from backend.database import get_pool
from backend.services.rm import customer_heads as heads
from backend.services.rm import evaluator, jobs
from backend.tasks import reward_models as tasks
from rm_worker.basis_manifest import manifest_digest

from .test_rm_action_scores import read_rows, write_scores
from .test_rm_api import REFUND_TRACE, _detail, _import, _register
from .test_rm_datasets import _user_id
from .test_rm_datasets import artifact_dir as artifact_dir
from .test_rm_shared_evaluator import predictions, seed_corpus

pytestmark = pytest.mark.usefixtures("rm_title_generator")
URL = "/api/v1/rm/customer-heads"


def manifest():
    result = {
        "schema_version": 1,
        "evaluator_kind": "shared_basis_v1",
        "feature_version": "1" * 64,
        "basis_dimension": 2,
        "global_head": {"weights": [1.0, 0.0]},
        "input_version": 2,
    }
    result["manifest_digest"] = manifest_digest(result)
    return result


async def released(owner):
    model_id = await get_pool().fetchval(
        """INSERT INTO rm_reward_models(owner_user_id,name,base_model,compute,epochs,max_pairs,
        trace_ids,scope,status,artifact_key,metrics,finished_at) VALUES($1,'basis','test/frozen','modal',1,2,
        '{}','shared','succeeded','private/test.tar.gz',$2,now()) RETURNING id""",
        owner,
        {
            "evaluator_kind": "shared_basis_v1",
            "basis_manifest": manifest(),
            "input_version": 2,
            "action_scoring_version": 1,
        },
    )
    await get_pool().execute(
        """INSERT INTO rm_evaluator_releases(reward_model_id,registry_revision,reason)
        VALUES($1,(SELECT coalesce(max(registry_revision),0)+1 FROM rm_evaluator_releases),'test')""",
        model_id,
    )
    return model_id


async def cached(owner, model_id, suffix="a", trace_id=None):
    current = None
    if trace_id:
        current = await get_pool().fetchval(
            "SELECT updated_at FROM rm_traces WHERE id=$1", trace_id
        )
    m = manifest()
    async with get_pool().acquire() as conn, conn.transaction():
        return (
            await heads.cache_pair(
                conn,
                owner,
                model_id,
                feature_version=m["feature_version"],
                manifest_digest=m["manifest_digest"],
                context_digest=heads.digest({"task": suffix}),
                input_a_digest=heads.digest({"a": suffix}),
                input_b_digest=heads.digest({"b": suffix}),
                features_a=[-1.0, 0.0],
                features_b=[1.0, 0.0],
                trace_id=trace_id,
                trace_updated_at=current,
            )
        )["id"]


async def setup(client):
    auth, other = await _register(client), await _register(client)
    owner = UUID(await _user_id(client, auth))
    model_id = await released(owner)
    pair_id = await cached(owner, model_id)
    return auth, other, owner, model_id, pair_id


async def test_zero_label_default_and_private_explicit_customer_adaptation(client):
    auth, other, owner, model_id, pair_id = await setup(client)
    body = {"shared_model_id": str(model_id), "pair_id": str(pair_id)}
    before = await client.post(f"{URL}/compare", headers=auth, json=body)
    assert before.status_code == 200, before.text
    assert before.json()["p_a_wins"] < 0.5 and not before.json()["calibrated"]
    assert (
        await client.post(f"{URL}/pairs/{pair_id}/label", headers=auth, json={"winner": "a"})
    ).status_code == 200
    fitted = await client.post(
        f"{URL}/fit",
        headers=auth,
        json={
            "shared_model_id": str(model_id),
            "name": "customer",
            "pair_ids": [str(pair_id)],
            "l2": 0.1,
        },
    )
    assert fitted.status_code == 201, fitted.text
    assert fitted.json()["fit"]["pairs"] == 1
    assert "head" not in fitted.json() and "weights" not in fitted.text
    body["head_id"] = fitted.json()["id"]
    after = await client.post(f"{URL}/compare", headers=auth, json=body)
    assert after.status_code == 200 and after.json()["p_a_wins"] > 0.5
    assert (await client.get(URL, headers=other)).json() == []
    for endpoint, payload in (
        ("fit", {"shared_model_id": str(model_id), "name": "leak", "pair_ids": [str(pair_id)]}),
        ("compare", body),
    ):
        assert (
            await client.post(f"{URL}/{endpoint}", headers=other, json=payload)
        ).status_code == 404
    assert (await client.get(f"{URL}/{body['head_id']}", headers=other)).status_code == 404
    assert (await client.get(f"{URL}/pairs", headers=other)).json() == []
    assert (
        await client.get(f"/api/v1/rm/reward-models/{model_id}/weights", headers=auth)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/rm/reward-models/{model_id}/playground",
            headers=auth,
            json={"prompt": "task", "responses": ["answer"]},
        )
    ).status_code == 404
    await get_pool().execute(
        """INSERT INTO rm_evaluator_registry(singleton,model_id,revision) VALUES(true,$1,1)
        ON CONFLICT(singleton) DO UPDATE SET model_id=$1,revision=1""",
        model_id,
    )
    public = await client.get("/api/v1/rm/evaluator", headers=auth)
    assert public.json()["default"]["feature_version"] == manifest()["feature_version"]
    assert public.json()["default"]["evaluator_kind"] == "shared_basis_v1"
    assert "weights" not in public.text and "basis_manifest" not in public.text


async def test_public_caller_cannot_inject_features_or_claim_verified_labels(client):
    auth, _, _, model_id, pair_id = await setup(client)
    response = await client.post(
        f"{URL}/fit",
        headers=auth,
        json={
            "shared_model_id": str(model_id),
            "name": "fake",
            "features_a": [1, 0],
            "verified": True,
        },
    )
    assert response.status_code == 422
    response = await client.post(
        f"{URL}/pairs/{pair_id}/label",
        headers=auth,
        json={"winner": "a", "source": "verified_outcome"},
    )
    assert response.status_code == 422
    unlabeled = await client.post(
        f"{URL}/fit",
        headers=auth,
        json={"shared_model_id": str(model_id), "name": "unknown", "pair_ids": [str(pair_id)]},
    )
    assert unlabeled.status_code == 422
    zero = await client.post(
        f"{URL}/fit", headers=auth, json={"shared_model_id": str(model_id), "name": "zero"}
    )
    assert zero.status_code == 201 and zero.json()["fit"]["pairs"] == 0


async def test_changed_and_revoked_source_feedback_invalidates_saved_head(client):
    auth, _, owner, model_id, source = await setup(client)
    target = await cached(owner, model_id, "target")
    await heads.label_pair(owner, source, "a")
    trained = await heads.fit(owner, model_id, "test", [source], 0.1)
    body = {"shared_model_id": str(model_id), "pair_id": str(target), "head_id": str(trained["id"])}
    assert (await client.post(f"{URL}/compare", headers=auth, json=body)).status_code == 200
    revision = await get_pool().fetchval(
        "SELECT revision FROM rm_customer_feature_pairs WHERE id=$1", source
    )
    await heads.label_pair(owner, source, "a")  # An identical network retry preserves the head.
    assert (
        await get_pool().fetchval(
            "SELECT revision FROM rm_customer_feature_pairs WHERE id=$1", source
        )
        == revision
    )
    assert (await client.post(f"{URL}/compare", headers=auth, json=body)).status_code == 200
    await heads.label_pair(owner, source, "b")
    assert (await client.post(f"{URL}/compare", headers=auth, json=body)).status_code == 422
    fresh = await heads.fit(owner, model_id, "test", [source], 0.1)
    assert fresh["version"] == 2
    body["head_id"] = str(fresh["id"])
    assert (await client.delete(f"{URL}/pairs/{source}", headers=auth)).status_code == 204
    assert (await client.post(f"{URL}/compare", headers=auth, json=body)).status_code == 422
    assert (
        await client.post(
            f"{URL}/compare",
            headers=auth,
            json={"shared_model_id": str(model_id), "pair_id": str(target)},
        )
    ).status_code == 200


async def test_cache_pin_and_trace_revisions_fail_closed(client):
    auth, _, owner, model_id, _ = await setup(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    traced = await cached(owner, model_id, "trace", UUID(trace_id))
    await get_pool().execute(
        "UPDATE rm_traces SET updated_at=updated_at+interval '1 second' WHERE id=$1", UUID(trace_id)
    )
    response = await client.post(
        f"{URL}/compare",
        headers=auth,
        json={"shared_model_id": str(model_id), "pair_id": str(traced)},
    )
    assert response.status_code == 422 and "changed" in response.text
    fresh = await cached(owner, model_id, "trace", UUID(trace_id))
    assert fresh != traced
    assert (await cached(owner, model_id, "trace", UUID(trace_id))) == fresh
    assert (
        await client.post(
            f"{URL}/compare",
            headers=auth,
            json={"shared_model_id": str(model_id), "pair_id": str(fresh)},
        )
    ).status_code == 200
    [second_trace] = await _import(client, auth, {**REFUND_TRACE, "id": "another-source"})
    another_source = await cached(owner, model_id, "trace", UUID(second_trace))
    assert another_source not in (traced, fresh)
    assert (
        await client.post(
            f"{URL}/compare",
            headers=auth,
            json={"shared_model_id": str(model_id), "pair_id": str(another_source)},
        )
    ).status_code == 200
    async with get_pool().acquire() as conn, conn.transaction():
        with pytest.raises(ValueError, match="another shared basis"):
            await heads.cache_pair(
                conn,
                owner,
                model_id,
                feature_version="9" * 64,
                manifest_digest=manifest()["manifest_digest"],
                context_digest="3" * 64,
                input_a_digest="4" * 64,
                input_b_digest="5" * 64,
                features_a=[1, 0],
                features_b=[0, 1],
            )


async def test_changed_manifest_and_wrong_model_head_fail_closed(client):
    auth, _, owner, model_id, pair_id = await setup(client)
    original = await heads.fit(owner, model_id, "zero", [])
    other_model = await released(owner)
    other_pair = await cached(owner, other_model)
    response = await client.post(
        f"{URL}/compare",
        headers=auth,
        json={
            "shared_model_id": str(other_model),
            "pair_id": str(other_pair),
            "head_id": str(original["id"]),
        },
    )
    assert response.status_code == 422 and "checkpoint" in response.text
    changed = manifest()
    changed["global_head"]["weights"] = [2, 0]
    changed["manifest_digest"] = manifest_digest(changed)
    await get_pool().execute(
        "UPDATE rm_reward_models SET metrics=$2 WHERE id=$1",
        model_id,
        {"evaluator_kind": "shared_basis_v1", "basis_manifest": changed},
    )
    response = await client.post(
        f"{URL}/compare",
        headers=auth,
        json={"shared_model_id": str(model_id), "pair_id": str(pair_id)},
    )
    assert response.status_code == 422 and "basis" in response.text


async def test_candidate_configuration_and_remote_basis_job(client, monkeypatch, artifact_dir):
    auth = await _register(client)
    owner = UUID(await _user_id(client, auth))
    await seed_corpus(owner)
    row = await evaluator.create_candidate(
        owner,
        "basis",
        "test/frozen",
        1,
        evaluator_kind="shared_basis_v1",
        basis_dimension=2,
        basis_options={"fit_steps": 2},
        base_model_license="test-only",
    )
    saved = await get_pool().fetchrow("SELECT * FROM rm_reward_models WHERE id=$1", row["id"])
    assert saved["training_config"]["basis_dimension"] == 2 and saved["compute"] == "modal"
    assert all(
        p["profile_id"] == str(owner) and p["customer_id"] is None for p in saved["training_pairs"]
    )

    async def worker(module, directory):
        job = json.loads((directory / "job.json").read_text())
        assert module == "rm_worker.modal_runner" and job["kind"] == "basis_train"
        assert job["basis_dimension"] == 2 and job["base_model_license"] == "test-only"
        (directory / "result.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "input_version": 2,
                        "action_scoring_version": 1,
                        "evaluator_kind": "shared_basis_v1",
                        "basis_manifest": manifest(),
                    }
                }
            )
        )

    async def evaluate(directory, model_key, pairs):
        return predictions(pairs)

    monkeypatch.setattr(jobs, "run_worker", worker)
    monkeypatch.setattr(evaluator, "evaluate_checkpoint", evaluate)
    await evaluator.train_candidate(row["id"])
    report = await get_pool().fetchval(
        "SELECT release_report FROM rm_reward_models WHERE id=$1", row["id"]
    )
    assert report["passed"] and report["evaluator_kind"] == "shared_basis_v1"
    assert report["research_guarantees_established"] is False


async def test_customer_head_trace_scores_are_private_pinned_and_deduplicated(
    client, monkeypatch, artifact_dir
):
    auth, other, owner, model_id, pair_id = await setup(client)
    await heads.label_pair(owner, pair_id, "a")
    head = await heads.fit(owner, model_id, "customer", [pair_id], 0.1)
    second = await heads.fit(owner, model_id, "another", [], 1)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    dispatched = []
    monkeypatch.setattr(tasks.score_trace, "delay", dispatched.append)
    url = f"/api/v1/rm/traces/{trace_id}/score"
    body = {"reward_model_id": str(model_id), "customer_head_id": str(head["id"])}
    private = await client.post(url, headers=auth, json=body)
    assert private.status_code == 202, private.text
    duplicate = await client.post(url, headers=auth, json=body)
    assert duplicate.json()["id"] == private.json()["id"]
    alternative = await client.post(
        url, headers=auth, json={**body, "customer_head_id": str(second["id"])}
    )
    default = await client.post(url, headers=auth, json={"reward_model_id": str(model_id)})
    assert len({private.json()["id"], alternative.json()["id"], default.json()["id"]}) == 3
    assert len(dispatched) == 3
    await get_pool().execute(
        """INSERT INTO rm_evaluator_registry(singleton,model_id,revision) VALUES(true,$1,1)
        ON CONFLICT(singleton) DO UPDATE SET model_id=$1,revision=1""",
        model_id,
    )

    async def worker(module, directory):
        assert module == "rm_worker.modal_runner"
        job = json.loads((directory / "job.json").read_text())
        write_scores(directory)
        if job.get("customer_head"):
            assert job["customer_head"]["head_id"] == str(head["id"])
            assert job["customer_head"]["manifest_digest"] == manifest()["manifest_digest"]
            rows = read_rows(directory / "action_scores.jsonl")
            for row in rows:
                row["score"] += 10
            jobs._write_jsonl(directory / "action_scores.jsonl", rows)
            (directory / "result.json").write_text(
                json.dumps(
                    {
                        "customer_provenance": heads.scoring_provenance(
                            job["customer_head"], manifest()
                        )
                    }
                )
            )
        else:
            assert job == {"kind": "score", "reward_model_key": "private/test.tar.gz"}

    monkeypatch.setattr(jobs, "run_worker", worker)
    await tasks.score_trace_async(UUID(default.json()["id"]))
    shared_before = await get_pool().fetch(
        "SELECT step_id,score,credit FROM rm_action_scores ORDER BY step_id"
    )
    await get_pool().execute(
        "INSERT INTO rm_auto_scores(trace_id) VALUES($1) ON CONFLICT DO NOTHING", UUID(trace_id)
    )
    await tasks.score_trace_async(UUID(private.json()["id"]))
    assert (
        await get_pool().fetch("SELECT step_id,score,credit FROM rm_action_scores ORDER BY step_id")
        == shared_before
    )
    assert await get_pool().fetchval(
        "SELECT 1 FROM rm_auto_scores WHERE trace_id=$1", UUID(trace_id)
    )
    response = await client.get(f"{URL}/scoring-runs/{private.json()['id']}", headers=auth)
    assert response.status_code == 200, response.text
    scores = response.json()["customer_scores"]
    assert [s["score"] for s in scores["actions"]] == [10, 11]
    assert scores["provenance"]["customer_head_version"] == 1
    assert scores["provenance"]["feature_version"] == manifest()["feature_version"]
    assert "weights" not in response.text
    assert (
        await client.get(f"{URL}/scoring-runs/{private.json()['id']}", headers=other)
    ).status_code == 404
    checkpoint_time = await get_pool().fetchval(
        "SELECT finished_at FROM rm_reward_models WHERE id=$1", model_id
    )
    await get_pool().execute(
        "UPDATE rm_reward_models SET finished_at=finished_at+interval '1 second' WHERE id=$1",
        model_id,
    )
    assert (
        await client.get(f"{URL}/scoring-runs/{private.json()['id']}", headers=auth)
    ).status_code == 422
    await get_pool().execute(
        "UPDATE rm_reward_models SET finished_at=$2 WHERE id=$1", model_id, checkpoint_time
    )
    latest_private = await client.post(url, headers=auth, json=body)
    assert latest_private.status_code == 202 and latest_private.json()["id"] != private.json()["id"]
    assert latest_private.json()["customer_head_id"] == str(head["id"])
    assert latest_private.json()["id"] != default.json()["id"]
    repeated_default = await client.post(url, headers=auth, json={"reward_model_id": str(model_id)})
    assert repeated_default.json()["id"] == default.json()["id"]
    assert repeated_default.json()["customer_head_id"] is None
    # The legacy default-score panel must not pick a newer personalized run.
    trace_detail = await _detail(client, auth, trace_id)
    assert [r["id"] for r in trace_detail["scoring_runs"]] == [default.json()["id"]]
    await heads.revoke_pair(owner, pair_id)
    assert (
        await client.get(f"{URL}/scoring-runs/{private.json()['id']}", headers=auth)
    ).status_code == 422


@pytest.mark.parametrize("mutation", ["feedback", "trace", "checkpoint", "worker_pin"])
async def test_customer_trace_scoring_rechecks_sources_at_publication(
    client, monkeypatch, artifact_dir, mutation
):
    auth, _, owner, model_id, pair_id = await setup(client)
    await heads.label_pair(owner, pair_id, "a")
    head = await heads.fit(owner, model_id, "customer", [pair_id], 0.1)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    monkeypatch.setattr(tasks.score_trace, "delay", lambda *a: None)
    response = await client.post(
        f"/api/v1/rm/traces/{trace_id}/score",
        headers=auth,
        json={"reward_model_id": str(model_id), "customer_head_id": str(head["id"])},
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["id"])

    async def worker(module, directory):
        job = json.loads((directory / "job.json").read_text())
        write_scores(directory)
        provenance = heads.scoring_provenance(job["customer_head"], manifest())
        if mutation == "feedback":
            await heads.label_pair(owner, pair_id, "b")
        elif mutation == "trace":
            await _import(client, auth, REFUND_TRACE)
        elif mutation == "checkpoint":
            await get_pool().execute(
                "UPDATE rm_reward_models SET finished_at=now() WHERE id=$1", model_id
            )
        else:
            provenance["feature_version"] = "9" * 64
        (directory / "result.json").write_text(json.dumps({"customer_provenance": provenance}))

    monkeypatch.setattr(jobs, "run_worker", worker)
    with pytest.raises(ValueError):
        await tasks.score_trace_async(run_id)
    row = await get_pool().fetchrow(
        "SELECT status,customer_scores FROM rm_scoring_runs WHERE id=$1", run_id
    )
    assert row["status"] == "failed" and row["customer_scores"] is None
    assert not await get_pool().fetchval("SELECT 1 FROM rm_action_scores")


async def test_private_trace_scoring_rejects_other_owners_heads(client, monkeypatch):
    auth, other, owner, model_id, pair_id = await setup(client)
    head = await heads.fit(owner, model_id, "zero", [])
    [trace_id] = await _import(client, other, REFUND_TRACE)
    monkeypatch.setattr(tasks.score_trace, "delay", lambda *a: None)
    response = await client.post(
        f"/api/v1/rm/traces/{trace_id}/score",
        headers=other,
        json={"reward_model_id": str(model_id), "customer_head_id": str(head["id"])},
    )
    assert response.status_code == 404
    assert not await get_pool().fetchval("SELECT 1 FROM rm_scoring_runs")
    response = await client.post(
        f"/api/v1/rm/traces/{trace_id}/score",
        headers=other,
        json={"reward_model_id": str(model_id), "customer_head": {"weights": [1, 2]}},
    )
    assert response.status_code == 422
