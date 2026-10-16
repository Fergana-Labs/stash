"""Composable evals: eval signals, run outcomes with learned credit, evals as optimization reward."""

from uuid import UUID, uuid4

from httpx import AsyncClient

from backend.services.rm import optimization
from backend.services.rm import optimization_policy as policy
from backend.services.rm import optimization_worker as worker

from .test_intuitions import LABELS, QUESTIONS, _examples, _grade_all, _register
from .test_intuitions import fake_jev as fake_jev
from .test_rm_monitoring import enabled

IM = "/api/v1/intuitions"
OPT = "/api/v1/rm/optimizations"


async def _create(client, auth, rubric, name="Replies") -> tuple[int, dict]:
    resp = await client.post(
        IM,
        headers=auth,
        json={
            "name": name,
            "output_type": "choice",
            "description": "Would I send it?",
            "labels": LABELS,
            "rubric": rubric,
        },
    )
    return resp.status_code, resp.json()


async def _save(client, auth, model_id, examples=None):
    await client.post(
        f"{IM}/{model_id}/examples", headers=auth, json={"examples": examples or _examples()}
    )
    await _grade_all(client, auth, model_id)
    fit = await client.post(f"{IM}/{model_id}/draft/fit", headers=auth, json={})
    assert fit.status_code == 200, fit.text
    resp = await client.post(f"{IM}/{model_id}/draft/promote", headers=auth, json={"force": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _saved_eval(client, auth, rubric=QUESTIONS, name="Polite") -> str:
    status, body = await _create(client, auth, rubric, name)
    assert status == 201, body
    model_id = body["model"]["id"]
    await _save(client, auth, model_id)
    return model_id


async def test_an_eval_uses_another_evals_pinned_decision(client: AsyncClient, fake_jev):
    auth = await _register(client)
    polite = await _saved_eval(client, auth)
    v1 = (await client.get(f"{IM}/{polite}", headers=auth)).json()["active"]["id"]

    status, body = await _create(
        client, auth, [QUESTIONS[1], {"type": "eval", "eval_id": polite}], "Send it?"
    )
    assert status == 201, body
    parent = body["model"]["id"]
    (signal,) = [q for q in body["draft"]["rubric"] if q["type"] == "eval"]
    assert signal["id"] == "eval_polite" and signal["version_id"] == v1
    assert signal["criteria"] == {"send": "ok", "rewrite": "bad"}
    assert "eval_id" not in body["draft"]["rubric"][0]  # Judge questions keep their shape.
    assert body["draft"]["feature_names"][-2:] == ["eval_polite=send", "eval_polite=rewrite"]

    before = len(fake_jev)
    await _save(client, auth, parent)
    # The judge only ever answers the parent's own question; the signal comes from the eval.
    assert all(questions == ["length"] for _, questions in fake_jev[before:])

    served = (
        await client.post(f"{IM}/{parent}/predict", headers=auth, json={"item": "please thanks"})
    ).json()
    assert served["rubric"]["eval_polite"]["send"] > 0.5
    contributions = served["contributions"]["send"]
    assert "eval_polite=send" in contributions

    # Saving a new version of the dependency does not change the parent's pinned signal.
    await client.patch(
        f"{IM}/{polite}/draft", headers=auth, json={"description": "Would I send it now?"}
    )
    await _grade_all(client, auth, polite)
    await client.post(f"{IM}/{polite}/draft/fit", headers=auth, json={})
    await client.post(f"{IM}/{polite}/draft/promote", headers=auth, json={"force": True})
    again = (
        await client.post(f"{IM}/{parent}/predict", headers=auth, json={"item": "please thanks"})
    ).json()
    assert again["rubric"]["eval_polite"] == served["rubric"]["eval_polite"]
    detail = (await client.get(f"{IM}/{parent}", headers=auth)).json()
    assert [q["version_id"] for q in detail["active"]["rubric"] if q["type"] == "eval"] == [v1]


async def test_eval_signals_reject_cycles_self_use_and_other_owners(client: AsyncClient, fake_jev):
    auth = await _register(client)
    polite = await _saved_eval(client, auth)
    status, body = await _create(client, auth, [{"type": "eval", "eval_id": polite}], "Parent")
    parent = body["model"]["id"]
    await _save(client, auth, parent)

    cycle = await client.patch(
        f"{IM}/{polite}/draft",
        headers=auth,
        json={"rubric": QUESTIONS + [{"type": "eval", "eval_id": parent}]},
    )
    assert cycle.status_code == 422 and "cycle" in cycle.json()["detail"]
    itself = await client.patch(
        f"{IM}/{parent}/draft", headers=auth, json={"rubric": [{"type": "eval", "eval_id": parent}]}
    )
    assert itself.status_code == 422
    unsaved_status, unsaved = await _create(client, auth, QUESTIONS, "Unsaved")
    status, _ = await _create(
        client, auth, [{"type": "eval", "eval_id": unsaved["model"]["id"]}], "Uses unsaved"
    )
    assert status == 422

    other = await _register(client)
    status, body = await _create(client, other, [{"type": "eval", "eval_id": polite}], "Theirs")
    assert status == 422 and "not found" in body["detail"]
    # Judge questions cannot claim to be eval signals.
    status, _ = await _create(client, auth, [{**QUESTIONS[0], "eval_id": polite}], "Bad")
    assert status == 422


async def test_run_outcomes_are_credited_to_the_decisions_that_predict_them(
    client: AsyncClient, fake_jev
):
    auth = await _register(client)
    model_id = await _saved_eval(client, auth)
    for i in range(12):
        good = i % 2 == 0
        resp = await client.post(
            f"{IM}/{model_id}/predict",
            headers=auth,
            json={"item": f"please {i} thanks" if good else f"no {i}", "run": f"r{i}", "step": 0},
        )
        assert resp.status_code == 200, resp.text
        # Planted signal: runs where the eval said "send" succeeded.
        outcome = 1.0 if resp.json()["label"] == "send" else 0.0
        resp = await client.post(
            f"{IM}/runs/r{i}/outcome", headers=auth, json={"value": outcome, "note": "closed"}
        )
        assert resp.status_code == 200, resp.text
    # One run failed even though the eval said "send".
    surprise = (
        await client.post(
            f"{IM}/{model_id}/predict",
            headers=auth,
            json={"item": "please good surprise", "run": "r-bad"},
        )
    ).json()
    await client.post(f"{IM}/runs/r-bad/outcome", headers=auth, json={"value": 0})

    run = (await client.get(f"{IM}/runs/r0", headers=auth)).json()
    assert run["outcome"] == 1.0 and run["calls"][0]["eval_name"] == "Polite"
    assert run["calls"][0]["step"] == 0
    assert (await client.get(f"{IM}/runs/missing", headers=auth)).status_code == 404
    assert (
        await client.post(f"{IM}/runs/r0/outcome", headers=auth, json={"value": 1.5})
    ).status_code == 422

    credit = (await client.get(f"{IM}/{model_id}/credit", headers=auth)).json()
    assert credit["ready"] and credit["runs"] == 13
    weights = {w["decision"]: w["weight"] for w in credit["weights"]}
    assert weights["send"] > weights["rewrite"]
    assert credit["cv_accuracy"] >= 0.75
    by_decision = {d["decision"]: d for d in credit["by_decision"]}
    assert by_decision["rewrite"]["success_rate"] == 0
    (flagged,) = [c for c in credit["calls_by_credit"] if c["suspect"]]
    assert flagged["prediction_id"] == surprise["prediction_id"]

    queue = (await client.get(f"{IM}/{model_id}/label-queue", headers=auth)).json()
    assert queue[0]["prediction_id"] == surprise["prediction_id"]
    assert "its run failed after this decision" in queue[0]["reasons"]


async def test_credit_waits_for_enough_mixed_outcomes(client: AsyncClient, fake_jev):
    auth = await _register(client)
    model_id = await _saved_eval(client, auth)
    for i in range(3):
        await client.post(
            f"{IM}/{model_id}/predict", headers=auth, json={"item": f"please {i}", "run": f"x{i}"}
        )
        await client.post(f"{IM}/runs/x{i}/outcome", headers=auth, json={"value": 1})
    credit = (await client.get(f"{IM}/{model_id}/credit", headers=auth)).json()
    assert not credit["ready"] and credit["runs"] == 3 and credit["success_rate"] == 1


def test_eval_items_freeze_the_cleaned_task_steps():
    trace = {"id": uuid4(), "title": "Refund ticket"}
    wrapper = '<stash-optimization run="r" revision="v">Be brief</stash-optimization>'
    targets = [
        {"role": "user", "content": f"{wrapper} Where is my refund?", "tool_name": None},
        {"role": "assistant", "content": "Thinking", "metadata": {"thinking": True}},
        {"role": "assistant", "content": "It was sent today.", "tool_name": None},
    ]
    (item,) = policy.eval_items(trace, targets)
    steps = item["eval_item"]["steps"]
    assert [s["content"] for s in steps] == ["Where is my refund?", "It was sent today."]
    assert item["trace_id"] == str(trace["id"])
    assert policy.eval_items(trace, targets[:1]) == []


async def test_prompt_optimization_scored_by_an_eval(client, pool, monkeypatch, fake_jev):
    auth, owner = await enabled(client, pool)
    eval_id = await _saved_eval(client, auth)
    body = {
        "name": "Reply optimization",
        "agent": "support",
        "scope": "default",
        "eval_id": eval_id,
        "target_label": "send",
        "runs_per_arm": 5,
        "max_rounds": 1,
    }
    assert (
        await client.post(OPT, headers=auth, json={**body, "target_label": "maybe"})
    ).status_code == 422
    assert (
        await client.post(OPT, headers=auth, json={**body, "reward_model_id": str(uuid4())})
    ).status_code == 422
    created = await client.post(OPT, headers=auth, json=body)
    assert created.status_code == 201, created.text
    program = created.json()
    assert program["status"] == "active" and program["reward_model"] is None
    assert program["eval"]["name"] == "Polite" and program["eval"]["target_label"] == "send"
    listed = (await client.get(OPT, headers=auth)).json()
    assert listed[0]["eval_name"] == "Polite"
    pid = UUID(program["id"])

    await worker.advance(pid)
    rid = await pool.fetchval("SELECT id FROM rm_optimization_rounds WHERE optimization_id=$1", pid)
    snapshots = []

    async def propose(snapshot):
        snapshots.append(snapshot)
        return worker.Proposal(instructions="Always say please.", rationale="Polite replies pass.")

    monkeypatch.setattr(worker, "propose", propose)
    await worker.generate(rid)
    objective = snapshots[0]["objective"]
    assert objective["eval_name"] == "Polite" and "send" in objective["measure"]
    assert [q["id"] for q in snapshots[0]["rubric"]] == ["polite", "length"]

    for n in range(10):
        assigned = (
            await client.post(
                f"{OPT}/{pid}/runs",
                headers=auth,
                json={
                    "work_key": str(n),
                    "agent": "support",
                    "scope": "default",
                    "agent_version": "a1",
                },
            )
        ).json()
        run_id = UUID(assigned["run_id"])
        arm = await pool.fetchval("SELECT arm FROM rm_optimization_runs WHERE id=$1", run_id)
        reply = f"please thanks {n}" if arm == "candidate" else f"no {n}"
        items = [
            {
                "trace_id": str(uuid4()),
                "eval_item": {
                    "title": "t",
                    "steps": [{"index": 0, "role": "assistant", "content": reply}],
                },
            }
        ]
        await pool.execute(
            "UPDATE rm_optimization_runs SET status='queued',score_items=$2 WHERE id=$1",
            run_id,
            items,
        )
        await worker.score(run_id)
        row = await pool.fetchrow(
            "SELECT status,reward,error FROM rm_optimization_runs WHERE id=$1", run_id
        )
        assert row["status"] == "completed", row["error"]
        assert (row["reward"] > 0.5) == (arm == "candidate")

    logged = await pool.fetch(
        "SELECT caller, ref FROM intuition_predictions WHERE model_id=$1 AND caller='optimization'",
        UUID(eval_id),
    )
    assert len(logged) == 10
    await worker.advance(pid)
    data = await optimization.detail(owner, pid)
    assert data["rounds"][0]["status"] == "promoted"

    rewards = await client.get(
        f"{OPT}/monitoring/rewards",
        headers=auth,
        params={"agent": "support", "model_id": eval_id, "program_id": str(pid)},
    )
    assert rewards.status_code == 200, rewards.text
    assert rewards.json()["unit"] == "eval_probability" and rewards.json()["total"] == 10
    overview = (await client.get(f"{OPT}/monitoring", headers=auth)).json()
    assert overview["programs"][0]["eval_name"] == "Polite"
