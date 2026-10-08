"""Loom regressions. Inference and training are stubbed; API/DB behavior is real."""

import json
from uuid import UUID

import pytest

from backend.services.rm import automatic_dataset, feedback, jobs
from backend.services.rm import workbench_auto as auto
from backend.services.rm import workbench_grader as wire
from backend.tasks import reward_models as tasks

from .test_rm_workbench import BASE, account, model_and_queue_boundaries, upload  # noqa: F401
from .test_workbench_automatic import answer, evaluate, get_eval
from .test_workbench_credit import distribution


async def annotated_traces(client, monkeypatch):
    user = await account(client)
    ids = []

    async def grade(snapshot):
        response = answer(snapshot)
        for index, result in enumerate(response["results"]):
            if result["criterion_id"] == "trace_success":
                result["verdict"] = (
                    "success"
                    if "success" in snapshot["context_events"][0]["content"]
                    else "failure"
                )
            else:
                result["verdict"] = ["strongly_negative", "neutral", "strongly_positive"][index % 3]
            result["probabilities"] = {
                label: 1.0 if label == result["verdict"] else 0.0
                for label in result["probabilities"]
            }
        return response

    monkeypatch.setattr(wire, "grade", grade)
    for name in ("train success", "train failure", "eval success", "eval failure"):
        tid = await upload(
            client,
            user,
            session_id=name,
            messages=[
                ("user", f"Fix {name}"),
                ("assistant", f"Guessing {name}"),
                ("assistant", f"Checking {name}"),
                ("assistant", f"Verified {name}"),
            ],
        )
        await auto.process_trace(tid)
        ids.append(tid)
    config = {
        "input_version": 3,
        "annotation_source": "automatic",
        "rubric": ["Complete the task"],
        "task_groups": {str(tid): f"task-{i}" for i, tid in enumerate(ids)},
        "evaluation_groups": ["task-2", "task-3"],
        "max_actions_per_trace": 24,
    }
    return user, ids, config


async def test_continuous_credit_matches_detail_summary_history_and_training(
    client, pool, monkeypatch
):
    user = await account(client)

    async def grade(snapshot):
        raw = answer(snapshot)["raw_output"]
        values = [
            distribution(negative=0.1, neutral=0.2, positive=0.6, strongly_positive=0.1),
            distribution(positive=0.6, strongly_positive=0.4),
            distribution(insufficient_evidence=1),
        ]
        for i, target in enumerate(snapshot["targets"]):
            raw["answers"][target["question_id"]].update(
                choice="insufficient_evidence" if i == 2 else "positive",
                probabilities=values[i],
            )
        questions = snapshot["provider_request"]["questions"]
        return wire.parse_response(
            raw, list(questions), choices={k: q["criteria"] for k, q in questions.items()}
        )

    monkeypatch.setattr(wire, "grade", grade)
    messages = [
        ("user", "Fix parser"),
        ("assistant", "Somewhat helpful"),
        ("assistant", "More helpful"),
        ("assistant", "Uncertain"),
    ]
    tid = await upload(client, user, messages=messages)
    await auto.process_trace(tid)
    current = (await get_eval(client, user, tid))["current"]
    credits = current["credits"]
    assert [c["credit"] for c in credits] == [1, 1, None]  # Legacy API compatibility.
    assert [c["expected_credit"] for c in credits[:2]] == pytest.approx([0.35, 0.7])
    assert credits[2]["expected_credit"] is None
    listed = await client.get("/api/v1/rm/traces", headers=user["headers"])
    assert listed.json()["traces"][0]["evaluation"]["action_credit"] == pytest.approx(
        {"mean": 0.525, "min": 0.35, "max": 0.7, "count": 2}
    )
    config = {
        "rubric": ["Complete the task"],
        "task_groups": {str(tid): "task"},
        "evaluation_groups": [],
    }
    pairs = await automatic_dataset.build_pairs(user["uuid"], [tid], config, 100)
    assert len(pairs) == 1  # Same winning label, but different expected credit.
    assert pairs[0]["chosen_credit"] == pytest.approx(0.7)
    assert pairs[0]["rejected_credit"] == pytest.approx(0.35)
    assert pairs[0]["credit_method"] == auto.policy.CREDIT_METHOD
    historical = await client.get(
        f"{BASE}/traces/{tid}/evaluation/{current['id']}", headers=user["headers"]
    )
    assert historical.json()["credits"] == credits
    await upload(client, user, messages=[*messages, ("user", "Another request")])
    pending = await get_eval(client, user, tid)
    assert [c["expected_credit"] for c in pending["previous_credits"][:2]] == pytest.approx(
        [0.35, 0.7]
    )


async def test_numeric_summary_and_search_are_current_literal_and_permission_scoped(
    client, pool, monkeypatch
):
    owner, tid, _ = await evaluate(client, pool, monkeypatch)
    await pool.execute("UPDATE rm_traces SET title='No matching title' WHERE id=$1", tid)
    other = await account(client)
    await upload(client, other)
    response = await client.get(
        "/api/v1/rm/traces", headers=owner["headers"], params={"q": "zero", "limit": 1}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1 and data["traces"][0]["id"] == str(tid)
    evaluation = data["traces"][0]["evaluation"]
    assert evaluation["score"] == 0
    assert evaluation["action_credit"] == {"mean": -1, "min": -1, "max": -1, "count": 1}
    literal = await client.get("/api/v1/rm/traces", headers=owner["headers"], params={"q": "%"})
    assert literal.json()["total"] == 0
    await upload(
        client,
        owner,
        messages=[
            ("user", "Fix the count parser. Zero must remain valid."),
            ("assistant", "All tests pass."),
            ("user", "Another task"),
            ("assistant", "Another response"),
        ],
    )
    listed = await client.get("/api/v1/rm/traces", headers=owner["headers"])
    assert listed.json()["traces"][0]["evaluation"]["current"] is False


async def test_training_uses_saved_annotations_and_preserves_both_signals_and_partitions(
    client, pool, monkeypatch, tmp_path
):
    user, ids, config = await annotated_traces(client, monkeypatch)

    async def unexpected(*args, **kwargs):
        raise AssertionError("Training must reuse saved automatic annotations")

    monkeypatch.setattr(wire, "grade", unexpected)
    monkeypatch.setattr(feedback, "build_feedback_pairs", unexpected)
    monkeypatch.setattr(tasks.train_reward_model, "delay", lambda *args: None)
    monkeypatch.setenv("RM_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("RM_COMPUTE", "modal")
    pairs = await automatic_dataset.build_pairs(user["uuid"], ids, config, 4)
    assert {
        (p["granularity"], config["task_groups"][p["trace_id"]] in config["evaluation_groups"])
        for p in pairs
    } == {
        ("action", True),
        ("action", False),
        ("trace", True),
        ("trace", False),
    }
    for pair in pairs:
        assert (
            len(
                {
                    config["task_groups"][tid] in config["evaluation_groups"]
                    for tid in pair["trace_ids"]
                }
            )
            == 1
        )
    created = await client.post(
        "/api/v1/rm/reward-models",
        headers=user["headers"],
        json={
            "name": "automatic",
            "trace_ids": [str(tid) for tid in ids],
            "training_config": config,
        },
    )
    assert created.status_code == 200, created.text
    model_id = UUID(created.json()["id"])

    async def worker(module, directory):
        assert module == "rm_worker.modal_runner"
        if (directory / "pairs.jsonl").exists():
            assert all(
                p["source"] == "automatic_annotation"
                for p in jobs._read_jsonl(directory / "pairs.jsonl")
            )
        items = jobs._read_jsonl(directory / "score_items.jsonl")
        assert items
        if (directory / "pairs.jsonl").exists():
            assert {item["trace_id"] for item in items} == {str(tid) for tid in ids}
        assert all("entire recorded trace" in item["text"] for item in items)
        jobs._write_jsonl(
            directory / "scores.jsonl",
            [{"trace_id": item["trace_id"], "score": 0.87} for item in items],
        )
        actions = jobs._read_jsonl(directory / "action_score_items.jsonl")
        jobs._write_jsonl(
            directory / "action_scores.jsonl",
            [
                {
                    "trace_id": item["trace_id"],
                    "step_id": item["step_id"],
                    "score": 1,
                    "credit": 0.5,
                }
                for item in actions
            ],
        )
        (directory / "result.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "input_version": 3,
                        "action_scoring_version": 1,
                        "trace_scoring_version": 1,
                    }
                }
            )
        )

    monkeypatch.setattr(jobs, "run_worker", worker)
    await jobs.run_training(model_id)
    assert (
        await pool.fetchval("SELECT status FROM rm_reward_models WHERE id=$1", model_id)
        == "succeeded"
    )
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_trace_scores WHERE reward_model_id=$1", model_id
        )
        == 4
    )
    listed = await client.get(
        "/api/v1/rm/traces", headers=user["headers"], params={"reward_model_id": str(model_id)}
    )
    assert all(t["latest_score"]["score"] == 0.87 for t in listed.json()["traces"])
    assert all(t["action_credit"]["mean"] == 0.5 for t in listed.json()["traces"])
    stranger = await account(client)
    assert (
        await client.get(
            "/api/v1/rm/traces",
            headers=stranger["headers"],
            params={"reward_model_id": str(model_id)},
        )
    ).status_code == 404

    # Apply the saved checkpoint to a new production run without re-annotation.
    monkeypatch.setattr(tasks.score_trace, "delay", lambda *args: None)
    fresh = await upload(client, user, session_id="fresh")
    requested = await client.post(
        f"/api/v1/rm/traces/{fresh}/score",
        headers=user["headers"],
        json={"reward_model_id": str(model_id)},
    )
    assert requested.status_code == 202, requested.text
    await jobs.run_scoring(UUID(requested.json()["id"]))
    assert (
        await pool.fetchval(
            "SELECT score FROM rm_trace_scores WHERE trace_id=$1 AND reward_model_id=$2",
            fresh,
            model_id,
        )
        == 0.87
    )

    async def changed_during_scoring(module, directory):
        await worker(module, directory)
        await upload(
            client,
            user,
            session_id="fresh",
            messages=[
                ("user", "Fix the count parser. Zero must remain valid."),
                ("assistant", "All tests pass."),
                ("user", "Check once more"),
                ("assistant", "Checked again"),
            ],
        )

    monkeypatch.setattr(jobs, "run_worker", changed_during_scoring)
    requested = await client.post(
        f"/api/v1/rm/traces/{fresh}/score",
        headers=user["headers"],
        json={"reward_model_id": str(model_id)},
    )
    with pytest.raises(ValueError, match="Trace changed"):
        await jobs.run_scoring(UUID(requested.json()["id"]))
    listed = await client.get(
        "/api/v1/rm/traces", headers=user["headers"], params={"reward_model_id": str(model_id)}
    )
    assert next(t for t in listed.json()["traces"] if t["id"] == str(fresh))["latest_score"] is None


async def test_stale_and_disputed_labels_cannot_train_the_model(client, pool, monkeypatch):
    user, ids, config = await annotated_traces(client, monkeypatch)
    await pool.execute(
        "INSERT INTO rm_annotations(owner_user_id,trace_id,label_error,comment) VALUES($1,$2,true,'Disputed annotation')",
        user["uuid"],
        ids[0],
    )
    await upload(
        client,
        user,
        session_id="train failure",
        messages=[
            ("user", "Fix train failure"),
            ("assistant", "Guessing train failure"),
            ("assistant", "Checking train failure"),
            ("assistant", "Verified train failure"),
            ("user", "Changed task"),
            ("assistant", "Changed result"),
        ],
    )
    pairs = await automatic_dataset.build_pairs(user["uuid"], ids, config, 100)
    assert pairs
    assert all(set(p["trace_ids"]).isdisjoint({str(ids[0]), str(ids[1])}) for p in pairs)


async def test_reviewer_suggestions_match_names_only_within_shared_workspaces(client, pool):
    owner, teammate, outsider = [await account(client, pool) for _ in range(3)]
    tid = await upload(client, owner)
    for user in (teammate, outsider):
        await pool.execute("UPDATE users SET display_name='Sam' WHERE id=$1", user["uuid"])
    workspace = await pool.fetchval(
        "INSERT INTO workspaces(name,domain,created_by,scope_user_id) VALUES('Team','team.test',$1,$1) RETURNING id",
        owner["uuid"],
    )
    for user in (owner, teammate):
        await pool.execute(
            "INSERT INTO workspace_members(workspace_id,user_id) VALUES($1,$2)",
            workspace,
            user["uuid"],
        )
    response = await client.get(
        f"{BASE}/traces/{tid}/reviewer-suggestions", headers=owner["headers"], params={"q": "sam"}
    )
    assert response.status_code == 200, response.text
    assert [r["user_id"] for r in response.json()] == [teammate["id"]]
    denied = await client.get(
        f"{BASE}/traces/{tid}/reviewer-suggestions",
        headers=outsider["headers"],
        params={"q": "sam"},
    )
    assert denied.status_code == 404
