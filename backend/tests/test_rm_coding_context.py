import json
from uuid import UUID

import pytest

from backend.services.rm import feedback, jobs
from backend.tasks import reward_models as tasks
from rm_worker.context import PREFIX, render_action_input

from .test_rm_api import _detail, _import, _register

pytestmark = pytest.mark.usefixtures("rm_title_generator")


def trace(name):
    return {
        "id": name,
        "steps": [
            {"role": "system", "content": "Do not edit customer repos."},
            {"role": "user", "content": "Fix " + name},
            {"role": "assistant", "content": "I checked the failing test."},
        ],
    }


async def test_personal_training_freezes_task_groups_and_preserves_context(
    client, pool, monkeypatch, tmp_path
):
    auth = await _register(client)
    ids = await _import(client, auth, trace("training"), trace("held-out"))
    details = [await _detail(client, auth, tid) for tid in ids]
    monkeypatch.setattr(tasks.train_reward_model, "delay", lambda *a: None)
    monkeypatch.setenv("RM_COMPUTE", "modal")
    monkeypatch.setenv("RM_ARTIFACT_DIR", str(tmp_path))
    config = {
        "input_version": 3,
        "rubric": ["Respect the task constraints."],
        "task_groups": {ids[0]: "train-task", ids[1]: "eval-task"},
        "evaluation_groups": ["eval-task"],
    }
    created = await client.post(
        "/api/v1/rm/reward-models",
        headers=auth,
        json={"name": "coding-v1", "trace_ids": ids, "training_config": config},
    )
    assert created.status_code == 200, created.text
    model_id = UUID(created.json()["id"])

    async def comparisons(owner, selected, limit, *, training_config):
        assert training_config["rubric"] == config["rubric"]
        pairs = []
        findings = []
        for tid, detail in zip(ids, details, strict=True):
            for alternative in ("Unsupported claim", "Skip verification"):
                steps = detail["steps"]
                pairs.append(
                    {
                        "trace_id": tid,
                        "chosen": render_action_input(steps, config["rubric"]),
                        "rejected": render_action_input(
                            [*steps[:-1], {"role": "assistant", "content": alternative}],
                            config["rubric"],
                        ),
                        "source": "feedback_revision",
                        "granularity": "action",
                        "action_type": "response",
                        "evidence": {"step_index": 2},
                    }
                )
            findings.append({"trace_id": tid, "step_index": 2})
        return pairs, findings

    monkeypatch.setattr(feedback, "build_feedback_pairs", comparisons)

    async def worker(module, directory):
        assert module == "rm_worker.modal_runner"
        job = json.loads((directory / "job.json").read_text())
        assert job["input_version"] == 3 and job["fixed_split"]
        pairs = jobs._read_jsonl(directory / "pairs.jsonl")
        assert {p["task_group"] for p in pairs if p["partition"] == "eval"} == {"eval-task"}
        assert all(p["chosen"].startswith(PREFIX) for p in pairs)
        items = jobs._read_jsonl(directory / "action_score_items.jsonl")
        assert len(items) == 2
        assert all("Do not edit customer repos." in item["text"] for item in items)
        (directory / "result.json").write_text(
            json.dumps({"metrics": {"input_version": 3, "action_scoring_version": 1}})
        )
        jobs._write_jsonl(directory / "scores.jsonl", [])
        jobs._write_jsonl(
            directory / "action_scores.jsonl",
            [
                {**{k: item[k] for k in ["trace_id", "step_id"]}, "score": 1.0, "credit": 0.5}
                for item in items
            ],
        )

    monkeypatch.setattr(jobs, "run_worker", worker)
    await jobs.run_training(model_id)
    model = await pool.fetchrow("SELECT * FROM rm_reward_models WHERE id=$1", model_id)
    assert model["status"] == "succeeded"
    assert model["feedback"][0]["included_in_training"]
    assert not model["feedback"][1]["included_in_training"]
    assert model["feedback"][1]["included_in_evaluation"]

    # Held-out tasks must not become skill-optimization prompts or feedback.
    monkeypatch.setattr(tasks.run_gepa, "delay", lambda *a: None)
    created_skill = await client.post(
        "/api/v1/rm/gepa-runs", headers=auth, json={"reward_model_id": str(model_id)}
    )
    assert created_skill.status_code == 200, created_skill.text

    async def skill_worker(module, directory):
        examples = jobs._read_jsonl(directory / "gepa_examples.jsonl")
        assert {e["trace_id"] for e in examples} == {ids[0]}
        (directory / "result.json").write_text(
            json.dumps(
                {
                    "skill_name": "verify",
                    "skill_description": "Verify changes",
                    "best_skill": "Run the relevant test",
                    "best_score": 0.5,
                    "seed_skill": "Verify",
                    "seed_score": 0.1,
                    "candidates": [],
                }
            )
        )

    # Fake pairs only need their grounded explanation for GEPA.
    for pair in model["training_pairs"]:
        pair["evidence"].update(
            source="ai_judgment", evidence_quote="Observed action", reason="Check"
        )
    await pool.execute(
        "UPDATE rm_reward_models SET training_pairs=$2 WHERE id=$1",
        model_id,
        model["training_pairs"],
    )
    monkeypatch.setattr(jobs, "run_worker", skill_worker)
    await jobs.run_gepa(UUID(created_skill.json()["id"]))


async def test_all_traces_from_a_task_cannot_be_split_across_train_and_eval(client, monkeypatch):
    auth = await _register(client)
    ids = await _import(client, auth, trace("a"), trace("b"))
    monkeypatch.setattr(tasks.train_reward_model, "delay", lambda *a: None)
    response = await client.post(
        "/api/v1/rm/reward-models",
        headers=auth,
        json={
            "name": "bad split",
            "trace_ids": ids,
            "training_config": {"task_groups": {tid: "same-task" for tid in ids}},
        },
    )
    assert response.status_code == 422
    assert "independent tasks" in response.text


def test_sampling_covers_the_trace_and_does_not_treat_agent_messages_as_human_feedback():
    steps = [
        {
            "idx": i,
            "role": "assistant",
            "content": str(i),
            "tool_name": "exec" if i % 2 else None,
            "tool_input": {},
        }
        for i in range(100)
    ]
    sampled = feedback.sample_actions(steps, 10)
    assert len(sampled) == 10
    assert {s["idx"] for s in sampled} >= {0, 1, 98, 99}
    assert feedback.sample_actions([{**steps[0], "metadata": {"thinking": True}}], 10) == []
    assert (
        feedback.user_feedback_evidence(
            [
                {
                    "idx": 0,
                    "role": "user",
                    "content": "<teammate-message>Excellent work</teammate-message>",
                }
            ]
        )
        == {}
    )


@pytest.mark.parametrize("missing_output", [False, True])
async def test_invalid_model_judgment_retries_then_abstains_without_losing_valid_findings(
    monkeypatch,
    missing_output,
):
    attempts = {}

    async def complete(**kwargs):
        target = json.loads(kwargs["prompt"])["target_response"]
        idx = target["idx"]
        attempts[idx] = attempts.get(idx, 0) + 1
        if idx == 1:
            if missing_output:
                raise feedback.llm.StructuredCompletionError("No structured output (max_tokens)")
            return feedback.ResponseExtraction.model_validate({})
        return feedback.ResponseExtraction(reason="No comparison needed", feedback=None)

    monkeypatch.setattr(feedback.llm, "complete_structured", complete)
    steps = [dict(idx=i, role="assistant", content="Progress", tool_name=None) for i in [1, 2]]
    result = await feedback.extract_preferences(steps, {}, input_version=3)
    assert result.feedback == []
    assert attempts == {1: 2, 2: 1}
