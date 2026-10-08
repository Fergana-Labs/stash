"""Automatic annotation: labels and rule scores per trace version, retries and privacy.

The labeling model is mocked. Native ingestion, queueing, APIs and DB are real.
"""

import json
from datetime import datetime
from uuid import UUID

import pytest

from backend.config import settings
from backend.services.rm import step_labeler
from backend.services.rm import workbench as legacy
from backend.services.rm import workbench_auto as auto
from backend.services.rm import workbench_evaluation as policy
from backend.services.rm import workbench_grader as wire
from backend.services.rm.adapters import parse_traces

from .test_rm_workbench import BASE, account, model_and_queue_boundaries, upload  # noqa: F401
from .test_workbench_grader import events


def answer(snapshot):
    """A grading-model reply to one of the fixed questions (corrections still ask them)."""
    questions = snapshot["provider_request"]["questions"]
    raw = {"model": "jev-test", "usage": {"input_tokens": 3, "output_tokens": 1}, "answers": {}}
    for key, question in questions.items():
        choice = "failure" if key == "trace_success" else "strongly_negative"
        raw["answers"][key] = {
            "type": "choice",
            "choice": choice,
            "confidence": 0.91,
            "probabilities": {c: 1.0 if c == choice else 0.0 for c in question["criteria"]},
        }
    return wire.parse_response(
        raw, list(questions), choices={k: q["criteria"] for k, q in questions.items()}
    )


def _label(actor, **fields):
    base = dict.fromkeys(
        ("intent", "verdict", "verdict_target", "sentiment", "type", "effect", "result", "outcome", "stance", "coverage", "note"))  # fmt: skip
    return {**base, "actor": actor, "is_output": False, "evidence": "", **fields}


REQUEST = _label("user", intent="new_request", verdict="none", sentiment="neutral")
ANSWER = _label(
    "agent", type="output", is_output=True, outcome="answer", stance="asserted", coverage="1/1"
)


def rejects(target):
    return _label(
        "user", intent="correction", verdict="rejected", verdict_target=target, sentiment="negative"
    )


@pytest.fixture
def labeler(monkeypatch):
    """Stand in for the labeling model. `labels` maps a chunk to its label; a
    chunk not listed is a request (user) or an unconfirmed answer (agent)."""
    state = {"calls": [], "labels": {}, "before": None}

    async def label_chunk(client, cache_key, transcript, chunk):
        if state["before"]:
            await state["before"](chunk)
        state["calls"].append(chunk["chunk_id"])
        default = REQUEST if chunk["actor"] == "user" else ANSWER
        return dict(state["labels"].get(chunk["chunk_id"], default), chunk_id=chunk["chunk_id"])

    monkeypatch.setattr(step_labeler, "label_chunk", label_chunk)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "TYPESAFE_API_KEY", None)
    return state


async def evaluate(client, pool, labeler):
    user = await account(client)
    tid = await upload(client, user)
    await auto.process_trace(tid)
    return user, tid, labeler["calls"]


async def get_eval(client, user, tid):
    response = await client.get(f"{BASE}/traces/{tid}/evaluation", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def test_ingested_trace_is_labeled_and_scored_without_any_setup(client, pool, labeler):
    user, tid, calls = await evaluate(client, pool, labeler)
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_graders") == 0
    assert calls == ["u1", "a1"]  # one labeling call per chunk
    result = (await get_eval(client, user, tid))["current"]
    # An answer nobody reacted to scores 0.3: neither a success nor a failure.
    assert result["status"] == "completed" and result["outcome"] == "partial_success"
    assert result["outcome_probabilities"] == {"score": 0.3}
    assert result["credited_actions"] == result["total_actions"] == 1
    # An action's credit is its score.
    credit = result["credits"][0]
    assert credit["expected_credit"] == 0.3 and credit["credit_method"] == policy.RULE_METHOD
    # The ordinal category is the band the score falls in.
    assert credit["credit"] == 1 and credit["label"] == "positive"
    assert result["actions"][0]["id"] == result["credits"][0]["step_id"]
    assert result["boundary"]["session_end_confirmed"] is False
    listed = await client.get("/api/v1/rm/traces", headers=user["headers"])
    assert listed.status_code == 200, listed.text
    summary = listed.json()["traces"][0]["evaluation"]
    assert summary["current"] is True and summary["score"] == 0.3
    assert summary["action_credit"]["mean"] == 0.3
    # The labels and the score breakdown are on the trace's steps.
    detail = (await client.get(f"/api/v1/rm/traces/{tid}", headers=user["headers"])).json()
    answer_step = next(s for s in detail["steps"] if s["role"] == "assistant")
    assert answer_step["metadata"]["label"]["outcome"] == "answer"
    assert answer_step["metadata"]["reward"]["total"] == 0.3
    await client.post(f"{BASE}/traces/{tid}/assess", headers=user["headers"])
    await auto.process_trace(tid)
    assert calls == ["u1", "a1"]  # Redelivery labels nothing again.


async def test_later_work_is_new_version_and_only_new_steps_are_labeled(client, pool, labeler):
    user, tid, calls = await evaluate(client, pool, labeler)
    before = (await get_eval(client, user, tid))["current"]
    messages = [
        ("user", "Fix the count parser. Zero must remain valid."),
        ("assistant", "All tests pass."),
        ("user", "No, the zero test failed."),
    ]
    await upload(client, user, messages=messages)
    await auto.process_trace(tid)
    pending = await get_eval(client, user, tid)
    assert pending["current"] is None and pending["queue"]["status"] == "waiting"
    assert pending["previous_credits"] == [
        {**before["credits"][0], "evaluation_id": before["id"], "created_at": before["created_at"]}
    ]
    assert len(calls) == 2
    labeler["labels"]["u2"] = rejects("a1")
    await upload(client, user, messages=messages + [("assistant", "I haven't fixed it yet.")])
    await auto.process_trace(tid)
    assert calls == ["u1", "a1", "u2", "a2"]  # the unchanged steps keep their labels
    updated = await get_eval(client, user, tid)
    assert updated["previous_credits"] == []
    after = updated["current"]
    assert after["id"] != before["id"] and after["total_actions"] == 2
    old = await client.get(
        f"{BASE}/traces/{tid}/evaluation/{before['id']}", headers=user["headers"]
    )
    assert old.json() == before
    # The early success claim is scored with the later rejection in view.
    first, second = after["credits"]
    assert first["step_id"] == before["actions"][0]["id"]
    assert first["expected_credit"] == -1 and first["label"] == "strongly_negative"
    assert second["expected_credit"] == 0.3


async def test_a_provider_failure_is_retried_and_then_completes(client, pool, labeler):
    user = await account(client)
    tid = await upload(client, user)
    failures = iter([True])

    async def fail_once(chunk):
        if next(failures, False):
            raise step_labeler.LabelingError("labeling model returned 503")

    labeler["before"] = fail_once
    await auto.process_trace(tid)
    failed = await get_eval(client, user, tid)
    assert failed["queue"]["status"] == "queued"
    assert failed["current"]["status"] == "failed" and failed["current"]["credits"] == []
    await auto.process_trace(tid)
    done = (await get_eval(client, user, tid))["current"]
    assert done["status"] == "completed" and done["credited_actions"] == 1


async def test_a_trace_over_the_context_limit_is_split_and_scored(
    client, pool, labeler, monkeypatch
):
    monkeypatch.setattr(settings, "STEP_LABELING_MAX_CHUNKS", 1)
    user, tid, calls = await evaluate(client, pool, labeler)
    result = await get_eval(client, user, tid)
    assert result["queue"]["status"] == "completed"
    assert result["current"]["status"] == "completed" and len(calls) == 2


async def test_a_missing_provider_key_is_repaired_once_the_key_arrives(
    client, pool, labeler, monkeypatch
):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    user, tid, _ = await evaluate(client, pool, labeler)
    result = await get_eval(client, user, tid)
    assert result["configured"] is False and result["queue"]["status"] == "failed"
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    await auto.recover()
    await auto.process_trace(tid)
    assert (await get_eval(client, user, tid))["current"]["status"] == "completed"


async def test_recover_resumes_old_budget_pause(client, pool, labeler):
    user = await account(client)
    tid = await upload(client, user)
    await pool.execute(
        """UPDATE rm_wb_queue SET due_at=now()+interval '1 day',
        error='Daily Jev evaluation budget reached; resumes tomorrow' WHERE trace_id=$1""",
        tid,
    )
    await auto.recover()
    row = await pool.fetchrow(
        "SELECT status,error,due_at<=now() AS ready FROM rm_wb_queue WHERE trace_id=$1", tid
    )
    assert dict(row) == {"status": "queued", "error": None, "ready": True}
    await auto.process_trace(tid)
    assert (await get_eval(client, user, tid))["current"]["status"] == "completed"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("running", "Daily Jev evaluation budget reached; resumes tomorrow"),
        ("queued", "An unrelated failure"),
        ("queued", None),
    ],
)
async def test_budget_recovery_leaves_other_queue_entries_unchanged(client, pool, status, error):
    user = await account(client)
    tid = await upload(client, user)
    before = await pool.fetchrow(
        """UPDATE rm_wb_queue SET status=$2,error=$3,due_at=now()+interval '1 day'
        WHERE trace_id=$1 RETURNING *""",
        tid,
        status,
        error,
    )
    await auto.recover()
    assert await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", tid) == before


async def test_lost_worker_lease_cannot_complete_an_evaluation(client, pool, labeler):
    user = await account(client)
    tid = await upload(client, user)

    async def lose_lease(chunk):
        await pool.execute("UPDATE rm_wb_queue SET status='queued' WHERE trace_id=$1", tid)

    labeler["before"] = lose_lease
    await auto.process_trace(tid)
    current = (await get_eval(client, user, tid))["current"]
    assert current["status"] != "completed" and current["outcome"] is None
    assert current["calls"] == []


async def test_evaluation_access_matches_trace_sharing_and_rejects_cross_trace_feedback(
    client, pool, labeler
):
    owner, tid, _ = await evaluate(client, pool, labeler)
    outsider = await account(client)
    eid = (await get_eval(client, owner, tid))["current"]["id"]
    for path in (f"{BASE}/traces/{tid}/evaluation", f"{BASE}/traces/{tid}/evaluation/{eid}"):
        result = await client.get(path, headers=outsider["headers"])
        assert result.status_code == 404
    await pool.execute(
        "INSERT INTO rm_wb_trace_reviewers(trace_id,user_id) VALUES($1,$2)", tid, outsider["uuid"]
    )
    assert (await get_eval(client, outsider, tid))["current"]["id"] == eid
    other_tid = await upload(client, owner, "other")
    response = await client.post(
        f"{BASE}/feedback",
        headers=owner["headers"],
        json={"trace_id": str(other_tid), "evaluation_id": eid, "comment": "wrong trace"},
    )
    assert response.status_code == 422, response.text


async def test_correction_uses_frozen_evidence_and_never_mutates_fixed_questions(
    client, pool, labeler, monkeypatch
):
    user, tid, _ = await evaluate(client, pool, labeler)
    evaluation = (await get_eval(client, user, tid))["current"]
    target = evaluation["credits"][0]["step_id"]
    # A replaced/deleted live event must not destroy the saved action identity.
    await pool.execute("DELETE FROM rm_trace_steps WHERE id=$1", UUID(target))
    response = await client.post(
        f"{BASE}/feedback",
        headers=user["headers"],
        json={
            "trace_id": str(tid),
            "evaluation_id": evaluation["id"],
            "target_step_id": target,
            "comment": "The claim is incorrect. Verify the tests.",
            "change_kind": "both",
        },
    )
    assert response.status_code == 201, response.text

    async def draft(**kwargs):
        data = json.loads(kwargs["prompt"])
        assert data["input"]["revision_hash"] == evaluation["revision_hash"]
        assert data["input"]["targets"][0]["step_id"] == target
        return legacy.CorrectionDraft(
            change_kind="both",
            proposed_verdict=None,
            explanation="Verify tests",
            grader_prompt="Change the fixed question",
            instruction_text="Run tests before claiming they passed.",
            title="Verify tests",
        )

    monkeypatch.setattr(legacy.llm, "complete_structured", draft)
    fid = UUID(response.json()["id"])
    await legacy.prepare_feedback(fid)
    row = await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", fid)
    assert row["status"] == "completed", row["error"]
    assert row["evaluation_target_step_id"] == UUID(target)
    changes = await pool.fetch("SELECT kind FROM rm_wb_changes WHERE feedback_id=$1", fid)
    assert [c["kind"] for c in changes] == ["instruction"]
    assert await pool.fetchval("SELECT builtin FROM rm_wb_graders") is True
    listed = await client.get(f"{BASE}/graders", headers=user["headers"])
    assert listed.json() == []


def test_credit_uses_later_evidence_and_has_explicit_target_in_model_visible_instructions():
    steps = events() + [
        {
            "id": "s6",
            "idx": 6,
            "role": "assistant",
            "content": "I was wrong.",
            "metadata": {"phase": "final"},
        }
    ]
    snapshot = policy.build_input(steps, [steps[2], steps[4]])
    assert "FUTURE_CORRECTION" in json.dumps(snapshot["context_events"])
    questions = snapshot["provider_request"]["questions"]
    assert questions["credit_0"]["instructions"]["target_step_id"] == "s2"
    assert questions["credit_1"]["instructions"]["target_step_id"] == "s4"
    assert snapshot["revision_hash"] == policy.build_input(steps)["revision_hash"]
    assert snapshot["boundary"]["kind"] == "completed_response"


@pytest.mark.parametrize(
    "last",
    [
        {"role": "assistant", "content": "Working", "metadata": {"phase": "commentary"}},
        {"role": "assistant", "content": "", "tool_name": "exec"},
        {"role": "tool", "content": "All tests passed"},
        {"role": "user", "content": "Fix that"},
    ],
)
def test_live_work_has_no_outcome_boundary(last):
    assert policy.boundary([{"id": "x", "idx": 0, **last}]) is None


def test_large_unicode_and_many_actions_keep_targets_and_record_omissions():
    steps = [
        {"id": str(i), "idx": i, "role": "assistant" if i % 2 else "user", "content": "😀" * 50000}
        for i in range(80)
    ]
    snapshot = policy.build_input(steps, [steps[i] for i in (1, 3, 5, 7)])
    assert set(t["step_id"] for t in snapshot["targets"]) <= {
        e["id"] for e in snapshot["context_events"]
    }
    assert "79" in {e["id"] for e in snapshot["context_events"]}
    assert snapshot["omissions"]
    wire._check_request_budget(snapshot["provider_request"])


@pytest.mark.parametrize("phase", ["commentary", "final"])
def test_native_codex_phase_survives_adapter(phase):
    text = json.dumps(
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": phase,
                "content": [{"type": "output_text", "text": "Response"}],
            },
        }
    )
    text = (
        json.dumps({"type": "session_meta", "payload": {"id": "test", "cwd": "/repo"}})
        + "\n"
        + text
    )
    _, traces = parse_traces(text, "codex")
    assert traces[0].steps[0].metadata["phase"] == phase


def test_thinking_after_a_final_response_waits_for_new_response():
    assert (
        policy.boundary(
            [
                {
                    "id": "end",
                    "idx": 0,
                    "role": "assistant",
                    "content": "Done",
                    "metadata": {"phase": "final"},
                },
                {
                    "id": "thought",
                    "idx": 1,
                    "role": "assistant",
                    "content": "More work",
                    "metadata": {"thinking": True},
                },
            ]
        )
        is None
    )


def test_celery_dispatch_calls_the_fixed_evaluator(monkeypatch):
    from backend.tasks import workbench as tasks

    sentinel = object()
    captured = []
    monkeypatch.setattr(auto, "process_trace", lambda tid: captured.append(tid) or sentinel)
    monkeypatch.setattr(tasks, "run_async", lambda value: value)
    tid = UUID("00000000-0000-0000-0000-000000000001")
    assert tasks.assess_trace.run(str(tid)) is sentinel
    assert captured == [tid]


def test_native_claude_completion_metadata_survives_adapter():
    text = json.dumps(
        {
            "type": "assistant",
            "sessionId": "test",
            "cwd": "/repo",
            "message": {
                "role": "assistant",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Done"}],
            },
        }
    )
    _, traces = parse_traces(text, "claude_code")
    assert traces[0].steps[-1].metadata["stop_reason"] == "end_turn"


async def test_previous_annotations_never_attach_to_rewritten_steps(client, pool, labeler):
    user, tid, _ = await evaluate(client, pool, labeler)
    # Stable ids alone are not sufficient if recorded content has changed.
    await pool.execute(
        "UPDATE rm_trace_steps SET content='Rewritten response' WHERE trace_id=$1 AND role='assistant'",
        tid,
    )
    result = await get_eval(client, user, tid)
    assert result["current"] is None
    assert result["previous_credits"] == []


async def test_trace_load_can_include_compact_scores_without_provider_payloads(
    client, pool, labeler
):
    user, tid, calls = await evaluate(client, pool, labeler)
    full = await get_eval(client, user, tid)
    response = await client.get(
        f"/api/v1/rm/traces/{tid}?include_evaluation=true", headers=user["headers"]
    )
    assert response.status_code == 200, response.text
    compact = response.json()["automatic_evaluation"]
    assert compact["current"]["credits"] == full["current"]["credits"]
    assert compact["current"]["outcome_probabilities"] == full["current"]["outcome_probabilities"]
    assert compact["current"]["calls"] == []
    assert compact["current"]["actions"] == []
    assert "provider_request" not in json.dumps(compact)
    # Appended work keeps earlier credits, without downloading its provider evidence.
    await upload(
        client,
        user,
        messages=[
            ("user", "Fix the count parser. Zero must remain valid."),
            ("assistant", "All tests pass."),
            ("user", "Please also check negatives"),
        ],
    )
    full = await get_eval(client, user, tid)
    compact = (
        await client.get(
            f"/api/v1/rm/traces/{tid}?include_evaluation=true", headers=user["headers"]
        )
    ).json()["automatic_evaluation"]

    def normalized(credits):
        return [{**c, "created_at": datetime.fromisoformat(c["created_at"])} for c in credits]

    assert normalized(compact["previous_credits"]) == normalized(full["previous_credits"])
    assert compact["previous_credits"]
    other = await account(client)
    assert (
        await client.get(
            f"/api/v1/rm/traces/{tid}?include_evaluation=true", headers=other["headers"]
        )
    ).status_code == 404
