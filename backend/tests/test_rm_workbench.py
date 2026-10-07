"""Production API flow: native trace -> judgments -> reviewed changes -> release.

The model boundaries are mocked; persistence, ownership, queueing, snapshots,
release gates, and native transcript ingestion use the real services/database.
"""

import json
from uuid import UUID

import pytest

from backend import auth
from backend.services.rm import workbench as service
from backend.services.rm import workbench_capture as capture
from backend.services.rm import workbench_grader as engine
from backend.services.rm import workbench_instructions as instructions
from backend.tasks import workbench as tasks

from .conftest import unique_name

BASE = "/api/v1/rm/workbench"
CONFIG = {
    "criteria": [
        {
            "id": "test_reporting",
            "name": "Report tests accurately",
            "description": "Do not claim passing tests without recorded evidence.",
        }
    ]
}


@pytest.fixture(autouse=True)
def model_and_queue_boundaries(monkeypatch):
    scheduled = []
    for name in ("reconcile", "assess_trace", "prepare_feedback", "check_change"):
        monkeypatch.setattr(
            getattr(tasks, name),
            "delay",
            lambda *args, _name=name, **kwargs: scheduled.append((_name, args)),
        )

    async def unexpected_model(*args, **kwargs):
        raise AssertionError("A test must explicitly supply its model response")

    monkeypatch.setattr(engine, "grade", unexpected_model)
    monkeypatch.setattr(service.llm, "complete_structured", unexpected_model)

    async def no_correction(snapshot):
        return capture.CorrectionSignal(
            correction=False, explanation="No correction in this fixture"
        )

    monkeypatch.setattr(capture, "classify", no_correction)
    return scheduled


async def account(client, pool=None):
    name = unique_name()
    response = await client.post(
        "/api/v1/users/register", json={"name": name, "password": "securepassword1"}
    )
    assert response.status_code == 201, response.text
    user = response.json()
    user["uuid"] = UUID(user["id"])
    user["headers"] = {"Authorization": f"Bearer {user['api_key']}"}
    user["email"] = f"{name}@example.test"
    if pool:
        await pool.execute("UPDATE users SET email=$2 WHERE id=$1", user["uuid"], user["email"])
    return user


def transcript(session_id, messages):
    records = [{"type": "session_meta", "payload": {"id": session_id, "cwd": "/repo"}}]
    records.extend(
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [
                    {"type": "input_text" if role == "user" else "output_text", "text": text}
                ],
            },
        }
        for role, text in messages
    )
    return "\n".join(json.dumps(r) for r in records).encode()


async def upload(client, user, session_id="run", messages=None):
    messages = messages or [
        ("user", "Fix the count parser. Zero must remain valid."),
        ("assistant", "All tests pass."),
    ]
    response = await client.post(
        "/api/v1/me/transcripts",
        headers=user["headers"],
        files={"file": ("run.jsonl", transcript(session_id, messages), "application/jsonl")},
        data={"session_id": session_id, "agent_name": "codex", "cwd": "/repo"},
    )
    assert response.status_code == 201, response.text
    assert "trace" in response.json(), response.text
    return UUID(response.json()["trace"]["id"])


async def grader(client, user, *, scope=None, config=None):
    response = await client.post(
        f"{BASE}/graders",
        headers=user["headers"],
        json={
            "name": "Coding checks",
            "scope": scope or {"repository": "/repo", "source_format": "codex"},
            "config": config or CONFIG,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def grade_response(snapshot, verdict="meets"):
    return {
        "results": [
            {
                "criterion_id": c["id"],
                "verdict": verdict,
                "evidence_step_ids": [],
                "reason": None,
                "confidence": 0.8,
                "probabilities": {verdict: 0.8},
            }
            for c in snapshot["criteria"]
        ],
        "raw_output": {"test_response": verdict},
        "duration_ms": 12,
        "usage": {"input_tokens": 123},
    }


async def assessments(client, user, trace_id):
    response = await client.get(f"{BASE}/traces/{trace_id}/assessments", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def correction(client, user, trace_id, assessment_id, monkeypatch):
    async def draft(**kwargs):
        assert kwargs["output_model"] is service.CorrectionDraft
        prompt = json.loads(kwargs["prompt"])
        assert prompt["assessment"]["id"] == assessment_id
        return service.CorrectionDraft(
            change_kind="both",
            proposed_verdict="violates",
            explanation="The agent claimed success without recorded passing checks; the judge accepted it.",
            grader_prompt="Require recorded test evidence before accepting a test success claim.",
            instruction_text="Inspect recorded test results before reporting success; state which checks were not run.",
            title="Report test evidence accurately",
        )

    monkeypatch.setattr(service.llm, "complete_structured", draft)
    response = await client.post(
        f"{BASE}/feedback",
        headers=user["headers"],
        json={
            "trace_id": str(trace_id),
            "assessment_id": assessment_id,
            "comment": "There is no passing test output. Both the report and the judgment are wrong.",
            "proposed_verdict": "violates",
            "change_kind": "both",
        },
    )
    assert response.status_code == 201, response.text
    fid = response.json()["id"]
    await service.prepare_feedback(UUID(fid))
    result = await client.get(f"{BASE}/feedback/{fid}", headers=user["headers"])
    assert result.status_code == 200, result.text
    return result.json()


async def test_grader_creation_queues_existing_owned_traces_and_applies_scope(
    client, pool, monkeypatch
):
    user, other = await account(client), await account(client)
    own_trace = await upload(client, user)
    other_trace = await upload(client, other)
    await pool.execute("UPDATE rm_wb_queue SET status='completed'")
    g = await grader(client, user)
    assert (
        await pool.fetchval("SELECT status FROM rm_wb_queue WHERE trace_id=$1", own_trace)
        == "queued"
    )
    assert (
        await pool.fetchval("SELECT status FROM rm_wb_queue WHERE trace_id=$1", other_trace)
        == "completed"
    )
    assert g["active_version"]["version"] == 1
    assert g["active_version"]["config"]["provider"] == "jev"
    outsider = await client.get(f"{BASE}/graders/{g['id']}", headers=other["headers"])
    assert outsider.status_code == 404
    calls = []

    async def grade(snapshot):
        calls.append(snapshot)
        return grade_response(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    await service.process_trace(own_trace)
    assert len(calls) == 1
    await client.patch(
        f"{BASE}/graders/{g['id']}",
        headers=user["headers"],
        json={"scope": {"repository": "/another-repo"}},
    )
    await service.process_trace(own_trace)
    assert len(calls) == 1


async def test_native_import_is_automatic_idempotent_and_preserves_past_inputs_on_append(
    client, pool, monkeypatch
):
    user = await account(client)
    await grader(client, user)
    tid = await upload(client, user)
    assert await pool.fetchval("SELECT status FROM rm_wb_queue WHERE trace_id=$1", tid) == "queued"
    calls = []

    async def grade(snapshot):
        # The exact input is durable before any paid provider call begins.
        stored = await pool.fetchrow(
            "SELECT * FROM rm_wb_assessments WHERE trace_id=$1 AND input_hash=$2 AND status='running'",
            tid,
            snapshot["input_hash"],
        )
        assert stored and stored["input_snapshot"] == snapshot
        calls.append(snapshot)
        return grade_response(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    await service.process_trace(tid)
    first = (await assessments(client, user, tid))["assessments"][0]
    await service.process_trace(tid)
    await upload(client, user)
    await service.process_trace(tid)
    assert len(calls) == 1
    await upload(
        client,
        user,
        messages=[
            ("user", "Fix the count parser. Zero must remain valid."),
            ("assistant", "All tests pass."),
            ("user", "Zero actually fails."),
            ("assistant", "I repaired the boundary condition."),
        ],
    )
    await service.process_trace(tid)
    rows = (await assessments(client, user, tid))["assessments"]
    assert len(calls) == 2 and len(rows) == 2
    preserved = next(r for r in rows if r["id"] == first["id"])
    assert preserved == first
    assert "Zero actually fails" not in json.dumps(preserved["input_snapshot"])
    assert "Zero actually fails" in json.dumps(calls[-1])


async def test_failed_provider_attempt_is_preserved_when_explicit_retry_succeeds(
    client, pool, monkeypatch
):
    user = await account(client)
    await grader(client, user)
    tid = await upload(client, user)
    calls = 0

    async def grade(snapshot):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise engine.GradingError("provider temporarily unavailable", retryable=True)
        return grade_response(snapshot, "insufficient_evidence")

    monkeypatch.setattr(engine, "grade", grade)
    await service.process_trace(tid)
    first = (await assessments(client, user, tid))["assessments"][0]
    assert first["status"] == "failed" and first["verdict"] is None
    assert "temporarily unavailable" in first["error"]
    queued = await client.post(f"{BASE}/traces/{tid}/assess", headers=user["headers"])
    assert queued.status_code == 202, queued.text
    await service.process_trace(tid)
    rows = (await assessments(client, user, tid))["assessments"]
    assert len(rows) == 2 and calls == 2
    assert next(r for r in rows if r["id"] == first["id"]) == first
    assert {r["attempt"] for r in rows} == {1, 2}
    assert next(r for r in rows if r["status"] == "completed")["verdict"] == "insufficient_evidence"


async def test_both_correction_requires_review_and_releases_only_checked_instruction(
    client, pool, monkeypatch
):
    user = await account(client)
    g = await grader(client, user)
    tid = await upload(client, user)

    async def grade(snapshot):
        return grade_response(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    await service.process_trace(tid)
    assessment = (await assessments(client, user, tid))["assessments"][0]
    feedback = await correction(client, user, tid, assessment["id"], monkeypatch)
    assert feedback["status"] == "completed" and feedback["review_status"] == "pending"
    assert {c["kind"] for c in feedback["changes"]} == {"instruction", "grader"}
    instruction = next(c for c in feedback["changes"] if c["kind"] == "instruction")
    assert instruction["status"] == "draft"
    premature = await client.post(
        f"{BASE}/changes/{instruction['id']}/check", headers=user["headers"]
    )
    assert premature.status_code == 422
    review = await client.post(
        f"{BASE}/feedback/{feedback['id']}/review",
        headers=user["headers"],
        json={"decision": "accept"},
    )
    assert review.status_code == 200, review.text
    check = await client.post(f"{BASE}/changes/{instruction['id']}/check", headers=user["headers"])
    assert check.status_code == 202, check.text
    await service.check_change(UUID(instruction["id"]))
    checked = (
        await client.get(f"{BASE}/changes/{instruction['id']}", headers=user["headers"])
    ).json()
    assert checked["status"] == "checked" and checked["check_report"]["passed"] is True
    assert checked["check_report"]["quality_measured"] is False
    released = await client.post(
        f"{BASE}/changes/{instruction['id']}/release", headers=user["headers"]
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "released"
    history = (
        await client.get(f"{BASE}/graders/{g['id']}/instruction-releases", headers=user["headers"])
    ).json()
    assert history[0]["content"] == instruction["content"]["text"]
    assert history[0]["active"] is True
    edit = await client.patch(
        f"{BASE}/changes/{instruction['id']}",
        headers=user["headers"],
        json={"content": {"text": "Silently changed."}},
    )
    assert edit.status_code == 422
    assert (await assessments(client, user, tid))["assessments"][0] == assessment


async def test_grader_cannot_release_using_its_own_source_correction_as_evaluation(
    client, pool, monkeypatch
):
    user = await account(client)
    g = await grader(client, user)
    tid = await upload(client, user)
    calls = []

    async def grade(snapshot):
        calls.append(snapshot)
        return grade_response(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    await service.process_trace(tid)
    a = (await assessments(client, user, tid))["assessments"][0]
    feedback = await correction(client, user, tid, a["id"], monkeypatch)
    await client.post(
        f"{BASE}/feedback/{feedback['id']}/review",
        headers=user["headers"],
        json={"decision": "accept"},
    )
    candidate = next(c for c in feedback["changes"] if c["kind"] == "grader")
    check = await client.post(f"{BASE}/changes/{candidate['id']}/check", headers=user["headers"])
    assert check.status_code == 202, check.text
    await service.check_change(UUID(candidate["id"]))
    checked = (
        await client.get(f"{BASE}/changes/{candidate['id']}", headers=user["headers"])
    ).json()
    assert checked["status"] == "checked"
    assert checked["check_report"]["passed"] is False
    assert checked["check_report"]["quality_measured"] is False
    assert checked["check_report"]["cases"] == []
    assert len(calls) == 1
    release = await client.post(
        f"{BASE}/changes/{candidate['id']}/release", headers=user["headers"]
    )
    assert release.status_code == 422
    current = (await client.get(f"{BASE}/graders/{g['id']}", headers=user["headers"])).json()
    assert current["grader"]["active_version_id"] == g["active_version_id"]


async def test_team_sharing_is_one_trace_and_does_not_grant_grader_or_release_permissions(
    client, pool, monkeypatch
):
    user, reviewer, outsider = (
        await account(client, pool),
        await account(client, pool),
        await account(client, pool),
    )
    g = await grader(client, user)
    shared = await upload(client, user, "shared")
    private = await upload(
        client, user, "private", [("user", "Private request."), ("assistant", "Private response.")]
    )

    async def grade(snapshot):
        return grade_response(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    await service.process_trace(shared)
    a = (await assessments(client, user, shared))["assessments"][0]
    feedback = await correction(client, user, shared, a["id"], monkeypatch)
    denied = await client.get(f"{BASE}/traces/{shared}/assessments", headers=reviewer["headers"])
    assert denied.status_code == 404
    added = await client.post(
        f"{BASE}/traces/{shared}/reviewers",
        headers=user["headers"],
        json={"email": reviewer["email"]},
    )
    assert added.status_code == 200, added.text
    shared_view = await assessments(client, reviewer, shared)
    assert shared_view["assessments"][0]["id"] == a["id"]
    # Sharing this trace's saved evidence must not expose current global grader
    # examples or configuration from unrelated later work.
    assert all("active_version" not in g for g in shared_view["graders"])
    assert "provider_request" not in shared_view["assessments"][0]["input_snapshot"]
    assert (
        await client.get(f"/api/v1/rm/traces/{shared}", headers=reviewer["headers"])
    ).status_code == 200
    assert (
        await client.delete(f"/api/v1/rm/traces/{shared}", headers=reviewer["headers"])
    ).status_code == 404
    reviewed = await client.get(f"{BASE}/feedback/{feedback['id']}", headers=reviewer["headers"])
    assert reviewed.status_code == 200
    assert all("content" not in c for c in reviewed.json()["changes"])
    assert "input_snapshot" not in reviewed.json()["interpretation"]
    for path in (f"/traces/{private}/assessments", f"/graders/{g['id']}"):
        assert (await client.get(BASE + path, headers=reviewer["headers"])).status_code == 404
    assert (
        await client.get(f"{BASE}/traces/{shared}/assessments", headers=outsider["headers"])
    ).status_code == 404
    comment = await client.post(
        f"{BASE}/feedback",
        headers=reviewer["headers"],
        json={"trace_id": str(shared), "comment": "Please verify the result."},
    )
    assert comment.status_code == 201, comment.text
    assert comment.json()["owner_user_id"] == user["id"]
    assert comment.json()["author_user_id"] == reviewer["id"]
    assert (
        await client.post(f"{BASE}/traces/{shared}/assess", headers=reviewer["headers"])
    ).status_code == 404
    for change in feedback["changes"]:
        for action in ("check", "release", "reject"):
            assert (
                await client.post(
                    f"{BASE}/changes/{change['id']}/{action}", headers=reviewer["headers"]
                )
            ).status_code == 404
    removed = await client.delete(
        f"{BASE}/traces/{shared}/reviewers/{reviewer['id']}", headers=user["headers"]
    )
    assert removed.status_code == 200
    assert (
        await client.get(f"{BASE}/feedback/{feedback['id']}", headers=reviewer["headers"])
    ).status_code == 404


async def test_read_only_recording_key_can_receive_released_context_but_cannot_release(
    client, pool
):
    user = await account(client)
    g = await grader(client, user)
    cid = await pool.fetchval(
        "INSERT INTO rm_wb_changes(owner_user_id,grader_id,kind,status,title,content,check_report) "
        "VALUES($1,$2,'instruction','checked','Read evidence',$3,$4) RETURNING id",
        user["uuid"],
        UUID(g["id"]),
        {"text": "Check the recorded test exit status."},
        {"passed": True, "quality_measured": False},
    )
    await instructions.release_instruction(user["uuid"], cid)
    await client.post(
        "/api/v1/me/sessions",
        headers=user["headers"],
        json={"session_id": "run", "agent_name": "codex", "cwd": "/repo"},
    )
    key = await auth.create_api_key(user["uuid"], "native recording", access="read")
    headers = {"Authorization": f"Bearer {key}"}
    delivered = await client.post(
        f"{BASE}/instruction-deliveries",
        headers=headers,
        json={"session_id": "run", "source_format": "codex", "repository": "/repo"},
    )
    assert delivered.status_code == 200, delivered.text
    assert len(delivered.json()["deliveries"]) == 1
    assert delivered.json()["deliveries"][0]["change_id"] == str(cid)
    assert delivered.json()["deliveries"][0]["content"] == "Check the recorded test exit status."
    blocked = await client.patch(
        f"{BASE}/graders/{g['id']}", headers=headers, json={"enabled": False}
    )
    assert blocked.status_code == 403
    assert (await client.post(f"{BASE}/changes/{cid}/release", headers=headers)).status_code == 403


async def test_reviewed_kind_change_retains_old_drafts_and_regenerates_only_requested_kind(
    client, pool, monkeypatch
):
    user = await account(client)
    await grader(client, user)
    tid = await upload(client, user)

    async def grade(snapshot):
        return grade_response(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    await service.process_trace(tid)
    assessment = (await assessments(client, user, tid))["assessments"][0]
    feedback = await correction(client, user, tid, assessment["id"], monkeypatch)
    old_ids = {c["id"] for c in feedback["changes"]}
    changed = await client.post(
        f"{BASE}/feedback/{feedback['id']}/review",
        headers=user["headers"],
        json={"decision": "accept", "change_kind": "agent_error"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "queued"
    await service.prepare_feedback(UUID(feedback["id"]))
    updated = (
        await client.get(f"{BASE}/feedback/{feedback['id']}", headers=user["headers"])
    ).json()
    assert updated["change_kind"] == "agent_error" and updated["status"] == "completed"
    assert all(c["status"] == "rejected" for c in updated["changes"] if c["id"] in old_ids)
    new = [c for c in updated["changes"] if c["id"] not in old_ids]
    assert len(new) == 1 and new[0]["kind"] == "instruction" and new[0]["status"] == "draft"


async def test_failed_correction_can_retry_without_erasing_failure_history(
    client, pool, monkeypatch
):
    user = await account(client)
    await grader(client, user)
    tid = await upload(client, user)

    async def unavailable(**kwargs):
        raise RuntimeError("Draft provider unavailable")

    monkeypatch.setattr(service.llm, "complete_structured", unavailable)
    response = await client.post(
        f"{BASE}/feedback",
        headers=user["headers"],
        json={
            "trace_id": str(tid),
            "comment": "Report the check that actually ran.",
            "change_kind": "agent_error",
        },
    )
    fid = response.json()["id"]
    await service.prepare_feedback(UUID(fid))
    failed = (await client.get(f"{BASE}/feedback/{fid}", headers=user["headers"])).json()
    assert failed["status"] == "failed" and "provider unavailable" in failed["error"]
    retried = await client.post(f"{BASE}/feedback/{fid}/retry", headers=user["headers"])
    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "queued" and retried.json()["error"] is None
    history = await pool.fetchval(
        "SELECT snapshot FROM rm_wb_history WHERE record_id=$1 AND action='retry'", UUID(fid)
    )
    assert history["error"] == failed["error"]

    async def recovered(**kwargs):
        return service.CorrectionDraft(
            change_kind="agent_error",
            proposed_verdict="violates",
            explanation="The report was unsupported.",
            instruction_text="Report only observed check results.",
            title="Report evidence",
        )

    monkeypatch.setattr(service.llm, "complete_structured", recovered)
    await service.prepare_feedback(UUID(fid))
    finished = (await client.get(f"{BASE}/feedback/{fid}", headers=user["headers"])).json()
    assert finished["status"] == "completed" and len(finished["changes"]) == 1
    assert (
        await client.post(f"{BASE}/feedback/{fid}/retry", headers=user["headers"])
    ).status_code == 422
