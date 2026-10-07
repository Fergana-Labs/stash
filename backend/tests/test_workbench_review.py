"""Human review, audit sampling, privacy, and correction revision lifecycle."""

import json
from uuid import UUID

import pytest

from backend.services.rm import workbench as service
from backend.services.rm import workbench_capture as capture
from backend.services.rm import workbench_grader as engine
from backend.tasks import workbench as tasks

from .test_rm_workbench import BASE, CONFIG, account, grade_response, grader, upload


@pytest.fixture(autouse=True)
def model_and_queue_boundaries(monkeypatch):
    scheduled = []
    for name in ("reconcile", "assess_trace", "prepare_feedback", "check_change"):
        monkeypatch.setattr(
            getattr(tasks, name),
            "delay",
            lambda *a, _name=name, **k: scheduled.append((_name, a)),
        )

    async def unexpected(**kwargs):
        raise AssertionError("This operation must not call a drafting model")

    async def grade(snapshot):
        verdict = "violates" if snapshot["target_step_index"] == 1 else "insufficient_evidence"
        return grade_response(snapshot, verdict)

    async def abstain(snapshot):
        return capture.CorrectionSignal(correction=False, explanation="No correction in fixture")

    monkeypatch.setattr(engine, "grade", grade)
    monkeypatch.setattr(service.llm, "complete_structured", unexpected)
    monkeypatch.setattr(capture, "classify", abstain)
    return scheduled


async def recorded(client, pool, *, private_example=False):
    user = await account(client, pool)
    config = dict(CONFIG)
    if private_example:
        config["examples"] = [
            {
                "criterion_id": "test_reporting",
                "input": "PRIVATE_EXAMPLE_FROM_AN_UNSHARED_TRACE",
                "verdict": "violates",
            }
        ]
    g = await grader(client, user, config=config)
    tid = await upload(
        client,
        user,
        messages=[
            ("user", "Repair the parser and verify the result."),
            ("assistant", "All tests pass."),
            ("assistant", "The requested change is complete."),
        ],
    )
    await service.process_trace(tid)
    assessments = await pool.fetch(
        "SELECT * FROM rm_wb_assessments WHERE trace_id=$1 ORDER BY target_index", tid
    )
    assert len(assessments) == 2
    return user, g, tid, assessments


async def add_comment(client, user, tid, assessment):
    response = await client.post(
        f"{BASE}/feedback",
        headers=user["headers"],
        json={
            "trace_id": str(tid),
            "assessment_id": str(assessment["id"]),
            "comment": "The claim is unsupported; both agent behavior and judging need correction.",
            "change_kind": "both",
            "proposed_verdict": "violates",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def draft(**kwargs):
    return service.CorrectionDraft(
        change_kind="both",
        proposed_verdict="violates",
        explanation="No recorded passing tests.",
        title="Check test evidence",
        grader_prompt="Require actual recorded test output.",
        instruction_text="Read the test output before claiming the tests pass.",
    )


async def test_sample_authorization_redacts_private_configuration_and_audit_label_calls_no_llm(
    client, pool, monkeypatch, model_and_queue_boundaries
):
    owner, g, tid, rows = await recorded(client, pool, private_example=True)
    reviewer, outsider = await account(client, pool), await account(client, pool)
    shared = await client.post(
        f"{BASE}/traces/{tid}/reviewers",
        headers=owner["headers"],
        json={"email": reviewer["email"]},
    )
    assert shared.status_code == 200
    samples = await client.get(f"{BASE}/review-samples", headers=reviewer["headers"])
    assert samples.status_code == 200
    assert {s["assessment"]["id"] for s in samples.json()} == {str(r["id"]) for r in rows}
    assert "PRIVATE_EXAMPLE" not in samples.text
    assert all(
        s["assessment"]["input_snapshot"]["private_configuration_omitted"] for s in samples.json()
    )
    assert (await client.get(f"{BASE}/review-samples", headers=outsider["headers"])).json() == []
    forbidden = await client.post(
        f"{BASE}/assessments/{rows[0]['id']}/label",
        headers=outsider["headers"],
        json={"verdict": "violates"},
    )
    assert forbidden.status_code == 404
    before = list(model_and_queue_boundaries)
    response = await client.post(
        f"{BASE}/assessments/{rows[0]['id']}/label",
        headers=reviewer["headers"],
        json={"verdict": "violates", "comment": "I checked the captured evidence."},
    )
    assert response.status_code == 201, response.text
    label = response.json()
    assert label["change_kind"] == "label_only" and label["status"] == "completed"
    assert label["review_status"] == "accepted" and label["reviewed_by"] == reviewer["id"]
    assert label["owner_user_id"] == owner["id"] and label["author_user_id"] == reviewer["id"]
    assert model_and_queue_boundaries == before
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_changes") == 0
    remaining = (await client.get(f"{BASE}/review-samples", headers=reviewer["headers"])).json()
    assert len(remaining) == 1 and remaining[0]["assessment"]["id"] == str(rows[1]["id"])
    audit = await client.get(f"{BASE}/feedback/{label['id']}", headers=outsider["headers"])
    assert audit.status_code == 404


async def test_revising_label_only_stays_human_only_and_preserves_review_history(
    client, pool, model_and_queue_boundaries
):
    owner, g, tid, rows = await recorded(client, pool)
    label = await service.label_assessment(owner["uuid"], rows[0]["id"], "meets")
    before = list(model_and_queue_boundaries)
    response = await client.post(
        f"{BASE}/feedback/{label['id']}/review",
        headers=owner["headers"],
        json={"decision": "accept", "proposed_verdict": "violates"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["change_kind"] == "label_only"
    await service.reconcile()
    assert model_and_queue_boundaries == before
    history = await pool.fetchval(
        "SELECT snapshot FROM rm_wb_history WHERE record_id=$1 AND action='accept'", label["id"]
    )
    assert history["proposed_verdict"] == "meets"
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_changes") == 0


async def test_changing_correction_kind_archives_old_drafts_and_regenerates_only_requested_kind(
    client, pool, monkeypatch
):
    owner, g, tid, rows = await recorded(client, pool)
    monkeypatch.setattr(service.llm, "complete_structured", draft)
    fid = await add_comment(client, owner, tid, rows[0])
    await service.prepare_feedback(fid)
    first = await service.feedback_detail(owner["uuid"], fid)
    originals = {c["id"]: c["content"] for c in first["changes"]}
    assert len(originals) == 2
    response = await client.post(
        f"{BASE}/feedback/{fid}/review",
        headers=owner["headers"],
        json={"decision": "accept", "change_kind": "agent_error"},
    )
    assert response.status_code == 200 and response.json()["status"] == "queued"
    await service.prepare_feedback(fid)
    revised = await service.feedback_detail(owner["uuid"], fid)
    assert revised["change_kind"] == "agent_error" and revised["status"] == "completed"
    for change in revised["changes"]:
        if change["id"] in originals:
            assert change["status"] == "rejected" and change["content"] == originals[change["id"]]
    fresh = [c for c in revised["changes"] if c["id"] not in originals]
    assert len(fresh) == 1 and fresh[0]["kind"] == "instruction"
    history = await pool.fetchval(
        "SELECT snapshot FROM rm_wb_history WHERE record_id=$1 AND action='accept'", fid
    )
    assert history["change_kind"] == "both" and history["interpretation"]["grader_prompt"]
    await service.reconcile()
    assert (
        await pool.fetchval("SELECT status FROM rm_wb_changes WHERE id=$1", fresh[0]["id"])
        == "checking"
    )


async def test_failed_interpretation_retry_keeps_previous_error_and_rejected_failure_cannot_retry(
    client, pool, monkeypatch
):
    owner, g, tid, rows = await recorded(client, pool)

    async def fail(**kwargs):
        raise RuntimeError("Provider temporarily unavailable")

    monkeypatch.setattr(service.llm, "complete_structured", fail)
    fid = await add_comment(client, owner, tid, rows[0])
    await service.prepare_feedback(fid)
    failed = await service.feedback_detail(owner["uuid"], fid)
    assert failed["status"] == "failed"
    retry = await client.post(f"{BASE}/feedback/{fid}/retry", headers=owner["headers"])
    assert retry.status_code == 202 and retry.json()["status"] == "queued"
    history = await pool.fetchval(
        "SELECT snapshot FROM rm_wb_history WHERE record_id=$1 AND action='retry'", fid
    )
    assert history["status"] == "failed" and history["error"] == failed["error"]
    monkeypatch.setattr(service.llm, "complete_structured", draft)
    await service.prepare_feedback(fid)
    assert (await service.feedback_detail(owner["uuid"], fid))["status"] == "completed"
    monkeypatch.setattr(service.llm, "complete_structured", fail)
    other = await add_comment(client, owner, tid, rows[1])
    await service.prepare_feedback(other)
    rejected = await client.post(
        f"{BASE}/feedback/{other}/review", headers=owner["headers"], json={"decision": "reject"}
    )
    assert rejected.status_code == 200 and rejected.json()["review_status"] == "rejected"
    blocked = await client.post(f"{BASE}/feedback/{other}/retry", headers=owner["headers"])
    assert blocked.status_code == 422
    assert (
        await pool.fetchval("SELECT count(*) FROM rm_wb_changes WHERE feedback_id=$1", other) == 0
    )


async def test_shared_feedback_hides_private_drafting_inputs_and_comparison_reports(
    client, pool, monkeypatch
):
    owner, g, tid, rows = await recorded(client, pool, private_example=True)
    reviewer = await account(client, pool)
    await client.post(
        f"{BASE}/traces/{tid}/reviewers",
        headers=owner["headers"],
        json={"email": reviewer["email"]},
    )
    monkeypatch.setattr(service.llm, "complete_structured", draft)
    fid = await add_comment(client, owner, tid, rows[0])
    await service.prepare_feedback(fid)
    await pool.execute(
        "UPDATE rm_wb_changes SET check_report=$2 WHERE feedback_id=$1",
        fid,
        {"cases": [{"private_other_trace": "PRIVATE_COMPARISON_TRACE"}]},
    )
    for path in (f"/feedback/{fid}", "/feedback", f"/traces/{tid}/assessments"):
        response = await client.get(BASE + path, headers=reviewer["headers"])
        assert response.status_code == 200
        assert (
            "PRIVATE_EXAMPLE" not in response.text
            and "PRIVATE_COMPARISON_TRACE" not in response.text
        )
    owner_view = await service.feedback_detail(owner["uuid"], fid)
    assert "PRIVATE_EXAMPLE" in json.dumps(service.serial(owner_view))
