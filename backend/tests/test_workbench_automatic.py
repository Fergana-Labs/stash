"""Fixed evaluation: durable requests, retrospective evidence, retries and privacy.

Provider inference is mocked. Native ingestion, queueing, APIs and DB are real.
"""

import copy
import json
from uuid import UUID

import pytest

from backend.services.rm import workbench as legacy
from backend.services.rm import workbench_auto as auto
from backend.services.rm import workbench_evaluation as policy
from backend.services.rm import workbench_grader as wire
from backend.services.rm.adapters import parse_traces

from .test_rm_workbench import BASE, account, model_and_queue_boundaries, upload  # noqa: F401
from .test_workbench_grader import events


def answer(snapshot):
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


async def evaluate(client, pool, monkeypatch):
    user = await account(client)
    tid = await upload(client, user)
    calls = []

    async def grade(snapshot):
        # Exact input is saved before inference, even if inference fails.
        row = await pool.fetchrow(
            "SELECT * FROM rm_wb_evaluation_calls WHERE status='running' ORDER BY created_at DESC LIMIT 1"
        )
        assert row and row["input_snapshot"] == snapshot
        calls.append(copy.deepcopy(snapshot))
        return answer(snapshot)

    monkeypatch.setattr(wire, "grade", grade)
    await auto.process_trace(tid)
    return user, tid, calls


async def get_eval(client, user, tid):
    response = await client.get(f"{BASE}/traces/{tid}/evaluation", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def test_ingested_trace_needs_no_grader_and_credit_is_not_confidence(
    client, pool, monkeypatch
):
    user, tid, calls = await evaluate(client, pool, monkeypatch)
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_graders") == 0
    assert len(calls) == 2
    result = (await get_eval(client, user, tid))["current"]
    assert result["status"] == "completed" and result["outcome"] == "failure"
    assert result["credited_actions"] == result["total_actions"] == 1
    assert result["credits"][0]["credit"] == -2
    assert result["credits"][0]["confidence"] == 0.91
    assert result["actions"][0]["id"] == result["credits"][0]["step_id"]
    assert result["boundary"]["session_end_confirmed"] is False
    listed = await client.get("/api/v1/rm/traces", headers=user["headers"])
    assert listed.status_code == 200, listed.text
    assert listed.json()["traces"][0]["evaluation"]["current"] is True
    await client.post(f"{BASE}/traces/{tid}/assess", headers=user["headers"])
    await auto.process_trace(tid)
    assert len(calls) == 2  # Redelivery cannot charge or increment coverage twice.


async def test_later_work_is_new_version_and_history_retains_exact_evidence(
    client, pool, monkeypatch
):
    user, tid, calls = await evaluate(client, pool, monkeypatch)
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
    assert (await get_eval(client, user, tid))["previous_credits"] == pending["previous_credits"]
    assert len(calls) == 2
    await upload(client, user, messages=messages + [("assistant", "I haven't fixed it yet.")])
    await auto.process_trace(tid)
    updated = await get_eval(client, user, tid)
    assert updated["previous_credits"] == []
    after = updated["current"]
    assert after["id"] != before["id"] and after["total_actions"] == 2
    old = await client.get(
        f"{BASE}/traces/{tid}/evaluation/{before['id']}", headers=user["headers"]
    )
    assert old.json() == before
    # Credit for the early success claim sees the later contradiction.
    assert any(e["content"] == "No, the zero test failed." for e in calls[-1]["context_events"])
    assert calls[-1]["targets"][0]["step_id"] == before["actions"][0]["id"]


@pytest.mark.parametrize("invalid_response", [False, True])
async def test_failed_credit_call_retries_without_repeating_success_call(
    client, pool, monkeypatch, invalid_response
):
    user = await account(client)
    tid = await upload(client, user)
    seen = []

    async def grade(snapshot):
        seen.append(list(snapshot["provider_request"]["questions"]))
        if len(seen) == 2:
            if invalid_response:
                raw = answer(snapshot)["raw_output"]
                # Real production failure: chosen label disagrees with probabilities.
                raw["answers"]["credit_0"]["choice"] = "positive"
                wire.parse_response(raw, ["credit_0"], choices={"credit_0": policy.CREDITS})
            raise wire.GradingError("Transient failure", retryable=True)
        return answer(snapshot)

    monkeypatch.setattr(wire, "grade", grade)
    await auto.process_trace(tid)
    failed = await get_eval(client, user, tid)
    assert failed["queue"]["status"] == "queued"
    assert failed["current"]["credited_actions"] == 0
    await auto.process_trace(tid)
    done = (await get_eval(client, user, tid))["current"]
    assert seen == [["trace_success"], ["credit_0"], ["credit_0"]]
    assert done["status"] == "completed" and done["credited_actions"] == 1
    assert [c["status"] for c in done["calls"]] == ["completed", "failed", "completed"]


async def test_evaluation_continues_past_500_daily_calls(client, pool, monkeypatch):
    user, tid, calls = await evaluate(client, pool, monkeypatch)
    previous = (await get_eval(client, user, tid))["current"]
    # Failed attempts also counted toward the old daily cap. Seed prior calls
    # without invoking the provider hundreds of times.
    await pool.execute(
        """INSERT INTO rm_wb_evaluation_calls
        (evaluation_id,owner_user_id,batch_index,attempt,input_snapshot,status)
        SELECT $1,$2,0,n,'{}'::jsonb,'failed' FROM generate_series(2,499) n""",
        UUID(previous["id"]),
        user["uuid"],
    )
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_evaluation_calls") == 500
    later = await upload(client, user, "later-run")
    await auto.process_trace(later)
    result = await get_eval(client, user, later)
    assert result["current"]["status"] == "completed"
    assert result["queue"]["error"] is None
    assert len(calls) == 4
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_evaluation_calls") == 502


async def test_recover_resumes_old_budget_pause_without_repeating_saved_calls(
    client, pool, monkeypatch
):
    monkeypatch.setattr(auto, "MAX_CALLS_PER_PASS", 1)
    user, tid, calls = await evaluate(client, pool, monkeypatch)
    queued = await get_eval(client, user, tid)
    assert queued["queue"]["status"] == "queued"
    assert queued["queue"]["error"] is None
    assert queued["current"]["outcome"] == "failure" and len(calls) == 1
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
    assert len(calls) == 2


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


async def test_lost_worker_lease_cannot_complete_an_evaluation(client, pool, monkeypatch):
    user = await account(client)
    tid = await upload(client, user)

    async def grade(snapshot):
        await pool.execute("UPDATE rm_wb_queue SET status='queued' WHERE trace_id=$1", tid)
        return answer(snapshot)

    monkeypatch.setattr(wire, "grade", grade)
    await auto.process_trace(tid)
    current = (await get_eval(client, user, tid))["current"]
    assert current["status"] != "completed" and current["outcome"] is None
    assert current["calls"][0]["status"] == "failed"


async def test_evaluation_access_matches_trace_sharing_and_rejects_cross_trace_feedback(
    client, pool, monkeypatch
):
    owner, tid, _ = await evaluate(client, pool, monkeypatch)
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
    client, pool, monkeypatch
):
    user, tid, _ = await evaluate(client, pool, monkeypatch)
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


async def test_previous_annotations_fill_gaps_as_new_batches_arrive(client, pool, monkeypatch):
    monkeypatch.setattr(policy, "ACTIONS_PER_BATCH", 1)
    user = await account(client)
    messages = [
        ("user", "Fix the parser"),
        ("assistant", "First attempt"),
        ("assistant", "Second attempt"),
        ("assistant", "Final answer"),
    ]
    tid = await upload(client, user, messages=messages)

    async def grade(snapshot):
        return answer(snapshot)

    monkeypatch.setattr(wire, "grade", grade)
    await auto.process_trace(tid)
    before = (await get_eval(client, user, tid))["current"]
    assert len(before["credits"]) == 3
    await upload(
        client, user, messages=messages + [("user", "Check again"), ("assistant", "Checked again")]
    )
    monkeypatch.setattr(auto, "MAX_CALLS_PER_PASS", 2)
    await auto.process_trace(tid)
    partial = await get_eval(client, user, tid)
    assert len(partial["current"]["credits"]) == 1
    assert {c["step_id"] for c in partial["previous_credits"]} == {
        c["step_id"] for c in before["credits"][1:]
    }
    assert all(c["evaluation_id"] == before["id"] for c in partial["previous_credits"])
    await auto.process_trace(tid)
    partial = await get_eval(client, user, tid)
    assert len(partial["current"]["credits"]) == 3
    assert partial["previous_credits"] == []
    await auto.process_trace(tid)
    assert (await get_eval(client, user, tid))["current"]["status"] == "completed"


async def test_previous_annotations_never_attach_to_rewritten_steps(client, pool, monkeypatch):
    user, tid, _ = await evaluate(client, pool, monkeypatch)
    # Stable ids alone are not sufficient if recorded content has changed.
    await pool.execute(
        "UPDATE rm_trace_steps SET content='Rewritten response' WHERE trace_id=$1 AND role='assistant'",
        tid,
    )
    result = await get_eval(client, user, tid)
    assert result["current"] is None
    assert result["previous_credits"] == []
