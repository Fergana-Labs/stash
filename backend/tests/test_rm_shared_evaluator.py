"""Shared evaluator lifecycle and tenant isolation; all remote computation is stubbed."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest

from backend.database import get_pool
from backend.routers import admin
from backend.services.rm import datasets, evaluator, feedback, jobs
from backend.tasks import reward_models as tasks
from rm_worker.release_gate import check_partition, evaluate_release

from .test_rm_action_scores import write_scores
from .test_rm_api import REFUND_TRACE, _annotate, _detail, _import, _register
from .test_rm_datasets import _user_id
from .test_rm_datasets import artifact_dir as artifact_dir
from .test_rm_feedback import conversation, evidence

pytestmark = pytest.mark.usefixtures("rm_title_generator")
ADMIN = {"X-Admin-Token": "test-operator"}


@pytest.fixture(autouse=True)
def operator(monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_PASSWORD", "test-operator")
    for task in (tasks.score_trace, tasks.collect_examples, tasks.train_evaluator):
        monkeypatch.setattr(task, "delay", lambda *a: None)


def examples():
    return [
        {
            "example_id": str(uuid4()),
            "partition": "train" if i < 2 else "eval",
            "task_group": str(i),
            "chosen": f"context {i}: correct",
            "rejected": f"context {i}: incorrect",
            "domain": "train" if i < 2 else f"domain-{i % 2}",
            "agent": "train" if i < 2 else f"agent-{i % 2}",
            "action_type": "tool_call" if i % 2 else "response",
            "granularity": "action",
        }
        for i in range(22)
    ]


async def seed_corpus(owner):
    async with get_pool().acquire() as conn, conn.transaction():
        for p in examples():
            await evaluator.insert_example(
                conn,
                owner,
                p,
                task_group=p["task_group"],
                domain=p["domain"],
                agent=p["agent"],
                partition=p["partition"],
                provenance={
                    "source": "human",
                    "permission": "test fixture",
                    "evidence": "reviewed",
                },
            )
    return await evaluator.corpus_snapshot()


def predictions(pairs, misses=()):
    return [
        {"example_id": p["example_id"], "correct": i not in misses}
        for i, p in enumerate(p for p in pairs if p["partition"] == "eval")
    ]


async def candidate(owner, *, ready=True):
    row = await evaluator.create_candidate(owner, "Shared candidate", "tiny/test", 1)
    if ready:
        pairs = await get_pool().fetchval(
            "SELECT training_pairs FROM rm_reward_models WHERE id=$1", row["id"]
        )
        report = evaluate_release(pairs, predictions(pairs), None)
        report["dataset_hash"] = evaluator.digest(pairs)
        await get_pool().execute(
            """UPDATE rm_reward_models SET status='succeeded', artifact_key='shared/test.tar.gz',
            metrics=$2, release_report=$3, finished_at=now() WHERE id=$1""",
            row["id"],
            {"action_scoring_version": 1, "input_version": 2},
            report,
        )
    return row["id"]


async def test_shared_default_scores_private_traces_without_exposing_corpus(
    client, monkeypatch, artifact_dir
):
    operator_auth, auth, other = (
        await _register(client),
        await _register(client),
        await _register(client),
    )
    owner = UUID(await _user_id(client, operator_auth))
    await seed_corpus(owner)
    model_id = await candidate(owner)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    [other_id] = await _import(client, other, REFUND_TRACE)
    # Candidate remains invisible until released, even when its ID is known.
    url = f"/api/v1/rm/traces/{trace_id}/score"
    assert (
        await client.post(url, headers=auth, json={"reward_model_id": str(model_id)})
    ).status_code == 404
    assert (await client.post(url, headers=auth, json={})).status_code == 422
    await evaluator.promote(model_id, "Reviewed bootstrap")
    public = (await client.get("/api/v1/rm/evaluator", headers=auth)).json()["default"]
    assert public["id"] == str(model_id) and "training_pairs" not in public
    for path in (
        f"/api/v1/rm/reward-models/{model_id}",
        f"/api/v1/rm/reward-models/{model_id}/weights",
    ):
        assert (await client.get(path, headers=auth)).status_code == 404
    assert (await client.get("/api/v1/admin/rm/examples", headers=auth)).status_code == 401
    assert (await client.get("/api/v1/rm/reward-models", headers=auth)).json() == []
    response = await client.post(url, headers=auth, json={})
    assert response.status_code == 202, response.text

    async def worker(module, directory):
        assert module == "rm_worker.modal_runner"
        items = write_scores(directory)
        assert "system: You are a support agent." in items[0]["text"]
        assert "delivered" not in items[0]["text"]

    monkeypatch.setattr(jobs, "run_worker", worker)
    await tasks.score_trace_async(UUID(response.json()["id"]))
    detail = await _detail(client, auth, trace_id)
    assert len(detail["action_scores"]) == 2 and not detail["shared_training_allowed"]
    assert detail["automatic_scoring"] is None and detail["training_collection"] is None
    assert detail["action_credit"]["count"] == 2
    assert (await _detail(client, other, other_id))["action_scores"] == []
    query = await client.post(
        "/api/v1/rm/query", headers=auth, json={"sql": "SELECT * FROM action_scores"}
    )
    assert len(query.json()["rows"]) == 2
    assert not await get_pool().fetchval(
        "SELECT 1 FROM rm_training_examples WHERE trace_id=$1", UUID(trace_id)
    )


async def test_import_dispatch_is_durable_debounced_and_bounded(client, monkeypatch):
    auth = await _register(client)
    owner = UUID(await _user_id(client, auth))
    await seed_corpus(owner)
    await evaluator.promote(await candidate(owner), "bootstrap")
    [trace] = await _import(client, auth, REFUND_TRACE)
    # Ingestion's 30-second idle delay prevents scoring every streaming span.
    assert (await evaluator.reconcile())["scoring_queued"] == 0
    await get_pool().execute("UPDATE rm_auto_scores SET due_at=now()")

    def unavailable(*a):
        raise ConnectionError("broker down")

    monkeypatch.setattr(tasks.score_trace, "delay", unavailable)
    with pytest.raises(ConnectionError):
        await evaluator.reconcile()
    assert await get_pool().fetchval("SELECT count(*) FROM rm_scoring_runs") == 1
    sent = []
    monkeypatch.setattr(tasks.score_trace, "delay", sent.append)
    await evaluator.reconcile()
    assert len(sent) == 1
    for _ in range(3):
        await get_pool().execute("UPDATE rm_scoring_runs SET status='failed'")
        await get_pool().execute("UPDATE rm_auto_scores SET due_at=now()")
        await evaluator.reconcile()
    assert await get_pool().fetchval("SELECT count(*) FROM rm_scoring_runs") == 3
    await _import(client, auth, REFUND_TRACE)
    assert (
        await get_pool().fetchval(
            "SELECT attempts FROM rm_auto_scores WHERE trace_id=$1", UUID(trace)
        )
        == 0
    )


async def test_permission_feedback_revisions_and_revocation(client, monkeypatch):
    auth, other = await _register(client), await _register(client)
    owner = UUID(await _user_id(client, auth))
    [trace] = await _import(client, auth, REFUND_TRACE)
    tid = UUID(trace)
    url = f"/api/v1/rm/traces/{trace}/training-contribution"
    assert (await client.patch(url, headers=other, json={"allowed": True})).status_code == 404
    calls = []

    async def build(*args, **kwargs):
        calls.append(kwargs)
        return [
            {
                "chosen": "prior context: good",
                "rejected": "prior context: bad",
                "action_type": "tool_call",
                "evidence": {"source": "user_feedback"},
            }
        ], []

    monkeypatch.setattr(feedback, "build_feedback_pairs", build)
    await evaluator.collect_examples(tid)
    assert not calls
    assert (await client.patch(url, headers=auth, json={"allowed": True})).status_code == 200
    await evaluator.collect_examples(tid)
    pairs = await evaluator.corpus_snapshot()
    assert len(pairs) == 1 and pairs[0]["partition"] == "train"
    assert calls == [{"shared": True}]
    await _annotate(client, auth, trace, comment="The tool needs an order ID")
    assert not await evaluator.corpus_snapshot()
    await evaluator.collect_examples(tid)
    assert len(await evaluator.corpus_snapshot()) == 1
    await evaluator.set_contribution(owner, tid, False)
    assert not await evaluator.corpus_snapshot()
    with pytest.raises(ValueError, match="revoked"):
        await evaluator.check_snapshot_valid(pairs)
    assert not await get_pool().fetchval("SELECT 1 FROM rm_example_collection")
    # Revocation during an in-flight extraction cannot restore the contribution.
    await evaluator.set_contribution(owner, tid, True)

    async def revoke(*args, **kwargs):
        await evaluator.set_contribution(owner, tid, False)
        return await build(*args, **kwargs)

    monkeypatch.setattr(feedback, "build_feedback_pairs", revoke)
    await evaluator.collect_examples(tid)
    assert not await evaluator.corpus_snapshot()


async def test_operator_examples_validate_actions_and_freeze_task_partition(client):
    auth = await _register(client)
    payload = {
        "owner_user_id": await _user_id(client, auth),
        "context": [{"role": "user", "content": "Find order"}],
        "task_context": {"tools": ["lookup_order"]},
        "chosen": dict(REFUND_TRACE["steps"][2]),
        "rejected": {"role": "assistant", "content": "Done without looking"},
        "task_group": "order-1182",
        "domain": "support",
        "agent": "bot",
        "partition": "eval",
        "source": "verified_outcome",
        "evidence": "Replay checked by operator",
        "permission_reference": "approved fixture",
    }
    url = "/api/v1/admin/rm/examples"
    response = await client.post(url, headers=ADMIN, json=payload)
    assert response.status_code == 201, response.text
    pair = (await evaluator.corpus_snapshot())[0]
    assert pair["action_type"] == "tool_call" and "Task and tool context:" in pair["chosen"]
    assert (await client.post(url, headers=ADMIN, json=payload)).status_code == 409
    await client.delete(url + "/" + response.json()["id"], headers=ADMIN)
    payload["partition"] = "train"
    assert (await client.post(url, headers=ADMIN, json=payload)).status_code == 422
    payload["chosen"]["role"] = "tool"
    assert (await client.post(url, headers=ADMIN, json=payload)).status_code == 422


async def test_candidate_remote_training_gate_promotion_and_rollback(
    client, monkeypatch, artifact_dir
):
    auth = await _register(client)
    owner = UUID(await _user_id(client, auth))
    pairs = await seed_corpus(owner)
    initial = await candidate(owner)
    await evaluator.promote(initial, "bootstrap")
    new = await candidate(owner, ready=False)
    calls = []

    async def worker(module, directory):
        calls.append(module)
        job = json.loads((directory / "job.json").read_text())
        if job["kind"] == "train":
            assert job["fixed_split"] and job["input_version"] == 2 and job["compute"] == "modal"
            assert not (directory / "action_score_items.jsonl").read_text()
            (directory / "result.json").write_text(
                json.dumps({"metrics": {"action_scoring_version": 1, "input_version": 2}})
            )
        else:
            frozen = [
                json.loads(line)
                for line in (directory / "evaluation_pairs.jsonl").read_text().splitlines()
            ]
            assert {p["example_id"] for p in frozen} == {
                p["example_id"] for p in pairs if p["partition"] == "eval"
            }
            (directory / "evaluation.json").write_text(
                json.dumps(predictions(frozen, [0, 1] if "baseline" in directory.name else []))
            )

    monkeypatch.setattr(jobs, "run_worker", worker)
    await tasks.train_evaluator_async(new)
    await tasks.train_evaluator_async(new)  # redelivery does not retrain
    assert calls == ["rm_worker.modal_runner"] * 3
    report = await get_pool().fetchval(
        "SELECT release_report FROM rm_reward_models WHERE id=$1", new
    )
    assert report["passed"] and report["slices"]["overall"]["baseline_accuracy"] == 0.9
    assert (await evaluator.promote(new, "improvement"))["revision"] == 2
    assert (await evaluator.promote(initial, "rollback after inspection", rollback=True))[
        "revision"
    ] == 3
    assert (await evaluator.default_evaluator())["id"] == initial
    assert await get_pool().fetchval("SELECT count(*) FROM rm_evaluator_releases") == 3


async def test_gate_blocks_revoked_data_failed_benchmarks_and_stale_parent(client):
    auth = await _register(client)
    owner = UUID(await _user_id(client, auth))
    await seed_corpus(owner)
    a, b = await candidate(owner), await candidate(owner)
    await evaluator.promote(a, "bootstrap")
    with pytest.raises(ValueError, match="Default changed"):
        await evaluator.promote(b, "stale")
    c = await candidate(owner)
    await get_pool().execute(
        "DELETE FROM rm_training_examples WHERE id=(SELECT id FROM rm_training_examples LIMIT 1)"
    )
    with pytest.raises(ValueError, match="revoked"):
        await evaluator.promote(c, "invalid")
    await get_pool().execute("UPDATE rm_reward_models SET release_report='{}' WHERE id=$1", c)
    with pytest.raises(ValueError, match="release gate"):
        await evaluator.promote(c, "invalid")
    with pytest.raises(ValueError, match="previously released"):
        await evaluator.promote(c, "invalid rollback", rollback=True)
    assert (await evaluator.default_evaluator())["id"] == a


async def test_recurring_training_requires_enablement_novel_data_and_cadence(client):
    auth = await _register(client)
    owner = UUID(await _user_id(client, auth))
    await seed_corpus(owner)
    assert await evaluator.schedule_candidate() is None
    config = {
        "owner_user_id": str(owner),
        "enabled": True,
        "min_new_examples": 2,
        "interval_hours": 1,
        "auto_promote": True,
    }
    response = await client.put("/api/v1/admin/rm/automation", headers=ADMIN, json=config)
    assert response.status_code == 200, response.text
    created = await asyncio.gather(evaluator.schedule_candidate(), evaluator.schedule_candidate())
    assert sum(c is not None for c in created) == 1
    row = await get_pool().fetchrow("SELECT * FROM rm_reward_models")
    assert row["compute"] == "modal" and row["automatic_release"]
    await get_pool().execute("UPDATE rm_reward_models SET status='failed'")
    assert await evaluator.schedule_candidate() is None
    await get_pool().execute(
        "UPDATE rm_evaluator_automation SET last_attempt_at=now()-interval '2 hours'"
    )
    assert await evaluator.schedule_candidate() is None  # no new training examples
    assert (await client.get("/api/v1/admin/rm/automation", headers=ADMIN)).json()["error"] is None


def test_gate_requires_unseen_tasks_domains_agents_and_improvement():
    pairs = examples()
    assert evaluate_release(pairs, predictions(pairs), None)["passed"]
    unchanged = evaluate_release(pairs, predictions(pairs), predictions(pairs))
    assert not unchanged["passed"] and "does not improve" in str(unchanged["reasons"])
    weak = evaluate_release(pairs, predictions(pairs, range(10)), None)
    assert not weak["passed"]
    for p in pairs:
        p["domain"] = "one-domain"
        p["agent"] = "one-agent"
    assert not evaluate_release(pairs, predictions(pairs), None)["passed"]
    pairs[-1]["task_group"] = pairs[0]["task_group"]
    with pytest.raises(ValueError, match="task group"):
        check_partition(pairs)


def test_gate_rejects_mismatched_predictions_and_slice_regressions():
    pairs = examples()
    with pytest.raises(ValueError, match="frozen benchmark"):
        evaluate_release(pairs, predictions(pairs)[:-1], None)
    baseline = predictions(pairs, [0, 2, 4, 6])
    candidate_predictions = predictions(pairs, [1])  # higher overall; regresses on tools
    report = evaluate_release(pairs, candidate_predictions, baseline)
    assert not report["passed"] and "Regression on action:tool_call" in report["reasons"]
    pairs[-1]["chosen"] = pairs[0]["chosen"]
    with pytest.raises(ValueError, match="duplicate"):
        check_partition(pairs)


async def test_shared_human_feedback_requires_independent_review_without_later_evidence(
    monkeypatch,
):
    calls = []

    async def complete(**kwargs):
        calls.append(kwargs)
        if kwargs["output_model"] is feedback.ComparisonReview:
            assert "You need to ask" not in kwargs["prompt"]
            return feedback.ComparisonReview(
                preferred="tie", grounded=True, reason="No defensible preference"
            )
        return kwargs["output_model"].model_validate(
            {
                "reason": "Reviewer asks for verification",
                "feedback": {
                    "source": "user_feedback",
                    "evidence_id": "step:2",
                    "evidence_quote": None,
                    "label": "negative",
                    "confidence": "high",
                    "revision": "Please provide the order number.",
                },
            }
        )

    monkeypatch.setattr(feedback.llm, "complete_structured", complete)
    result = await feedback.extract_preferences(conversation(), evidence(), review_all=True)
    assert len(calls) == 2 and result.feedback[0].revision is None


async def test_shared_input_context_and_rating_evidence_match_inference(client, monkeypatch):
    auth = await _register(client)
    source = {**REFUND_TRACE, "metadata": {"evaluation_context": {"tools": ["lookup_order"]}}}
    [trace] = await _import(client, auth, source)
    owner = UUID(await _user_id(client, auth))
    detail = await _detail(client, auth, trace)
    await _annotate(client, auth, trace, step_id=detail["steps"][2]["id"], rating=-1)

    async def extract(steps, sources, **kwargs):
        assert kwargs["review_all"] and "Task and tool context:" in steps[0]["content"]
        assert "Reviewer rated this action negatively." in [s["text"] for s in sources.values()]
        return feedback.Extraction(feedback=[])

    monkeypatch.setattr(feedback, "extract_preferences", extract)
    await feedback.build_feedback_pairs(owner, [UUID(trace)], 10, shared=True)
    items = await datasets.action_score_items(owner, UUID(trace), input_version=2)
    assert items[0]["text"].startswith('Task and tool context: {"tools": ["lookup_order"]}')
    assert "system: You are a support agent." in items[0]["text"]
    assert "delivered" not in items[0]["text"]


@pytest.mark.parametrize("enabled", [True, False])
async def test_autopromotion_honors_gate_and_current_operator_switch(
    client, monkeypatch, artifact_dir, enabled
):
    auth = await _register(client)
    owner = UUID(await _user_id(client, auth))
    await seed_corpus(owner)
    await evaluator.configure_automation(
        {
            "enabled": True,
            "owner_user_id": owner,
            "base_model": "tiny/test",
            "epochs": 1,
            "min_new_examples": 2,
            "interval_hours": 1,
            "auto_promote": True,
        }
    )
    row = await evaluator.schedule_candidate()

    async def worker(module, directory):
        (directory / "result.json").write_text(
            json.dumps({"metrics": {"action_scoring_version": 1, "input_version": 2}})
        )

    async def evaluate(directory, key, pairs):
        return predictions(pairs)

    monkeypatch.setattr(jobs, "run_worker", worker)
    monkeypatch.setattr(evaluator, "evaluate_checkpoint", evaluate)
    await get_pool().execute("UPDATE rm_evaluator_automation SET enabled=$1", enabled)
    await tasks.train_evaluator_async(row["id"])
    default = await evaluator.default_evaluator()
    assert (default["id"] if default else None) == (row["id"] if enabled else None)
