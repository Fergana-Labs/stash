"""Grader activations affect new captured events; comments remain durable."""

from uuid import UUID

import pytest

from backend.services.rm import workbench as service
from backend.services.rm import workbench_grader as engine

from .test_rm_workbench import (
    BASE,
    CONFIG,
    account,
    assessments,
    grade_response,
    grader,
    upload,
)
from .test_rm_workbench import (
    model_and_queue_boundaries as model_and_queue_boundaries,
)


async def checked_candidate(client, pool, user, g):
    response = await client.post(
        f"{BASE}/graders/{g['id']}/versions",
        headers=user["headers"],
        json={"config": {**CONFIG, "prompt": "Candidate reporting rubric."}},
    )
    assert response.status_code == 201, response.text
    candidate = response.json()
    # Simulate an already completed comparison. Quality gates are tested
    # separately; this test is specifically about activation's event boundary.
    await pool.execute(
        "UPDATE rm_wb_changes SET status='checked',check_report=$2 WHERE id=$1",
        UUID(candidate["id"]),
        {"passed": True, "content_hash": service.digest(candidate["content"]), "cases": []},
    )
    return candidate


async def test_release_and_rollback_grade_only_future_events_without_rewriting_history(
    client, pool, monkeypatch
):
    user = await account(client)
    tid = await upload(client, user)
    g = await grader(client, user)
    calls = []

    async def grade(snapshot):
        calls.append(snapshot)
        return grade_response(snapshot)

    monkeypatch.setattr(engine, "grade", grade)
    await service.process_trace(tid)
    original = (await assessments(client, user, tid))["assessments"][0]
    candidate = await checked_candidate(client, pool, user, g)
    released = await client.post(
        f"{BASE}/changes/{candidate['id']}/release", headers=user["headers"]
    )
    assert released.status_code == 200, released.text
    v2 = released.json()["version_id"]
    activation = await pool.fetchval(
        "SELECT snapshot FROM rm_wb_history WHERE record_id=$1 AND action='released'",
        UUID(g["id"]),
    )
    assert activation["activation_fences"][str(tid)] == 1
    assert (
        await pool.fetchval("SELECT status FROM rm_wb_queue WHERE trace_id=$1", tid) == "completed"
    )
    await client.post(f"{BASE}/traces/{tid}/assess", headers=user["headers"])
    await service.process_trace(tid)
    assert len(calls) == 1

    messages = [
        ("user", "Fix the count parser. Zero must remain valid."),
        ("assistant", "All tests pass."),
        ("user", "Now check empty input."),
        ("assistant", "The empty input check passes."),
    ]
    await upload(client, user, messages=messages)
    await service.process_trace(tid)
    rows = (await assessments(client, user, tid))["assessments"]
    assert len(rows) == 2 and len(calls) == 2
    assert next(r for r in rows if r["id"] == original["id"]) == original
    assert next(r for r in rows if r["target_index"] == 3)["grader_version_id"] == v2

    rolled_back = await client.post(
        f"{BASE}/graders/{g['id']}/rollback",
        headers=user["headers"],
        json={"version_id": g["active_version_id"]},
    )
    assert rolled_back.status_code == 200, rolled_back.text
    assert (
        await pool.fetchval("SELECT status FROM rm_wb_queue WHERE trace_id=$1", tid) == "completed"
    )
    await client.post(f"{BASE}/traces/{tid}/assess", headers=user["headers"])
    await service.process_trace(tid)
    assert len(calls) == 2
    messages += [("user", "Now check whitespace."), ("assistant", "The whitespace check passes.")]
    await upload(client, user, messages=messages)
    await service.process_trace(tid)
    rows = (await assessments(client, user, tid))["assessments"]
    assert len(rows) == 3 and len(calls) == 3
    assert (
        next(r for r in rows if r["target_index"] == 5)["grader_version_id"]
        == g["active_version_id"]
    )
    new_trace = await upload(client, user, "later-run")
    await service.process_trace(new_trace)
    assert len(calls) == 4


@pytest.mark.parametrize("mode", ["enabled", "paused", "different_scope", "failure"])
async def test_existing_annotation_comment_prepares_feedback_only_when_enabled_and_survives_failure(
    client, pool, monkeypatch, mode
):
    user = await account(client)
    g = await grader(client, user)
    if mode == "paused":
        await client.patch(
            f"{BASE}/graders/{g['id']}", headers=user["headers"], json={"enabled": False}
        )
    elif mode == "different_scope":
        await client.patch(
            f"{BASE}/graders/{g['id']}",
            headers=user["headers"],
            json={"scope": {"repository": "/elsewhere"}},
        )
    if mode == "failure":

        async def unavailable(*args, **kwargs):
            raise RuntimeError("Temporary workbench failure")

        monkeypatch.setattr(service, "create_feedback", unavailable)
    tid = await upload(client, user)
    step = await pool.fetchval(
        "SELECT id FROM rm_trace_steps WHERE trace_id=$1 AND role='assistant'", tid
    )
    comment = "The zero test failed; this success report is incorrect."
    response = await client.post(
        f"/api/v1/rm/traces/{tid}/annotations",
        headers=user["headers"],
        json={"step_id": str(step), "comment": comment},
    )
    assert response.status_code == 200, response.text
    assert (
        await pool.fetchval(
            "SELECT comment FROM rm_annotations WHERE id=$1", UUID(response.json()["id"])
        )
        == comment
    )
    rows = await pool.fetch("SELECT * FROM rm_wb_feedback WHERE trace_id=$1", tid)
    if mode == "enabled":
        assert len(rows) == 1
        assert rows[0]["comment"] == comment and rows[0]["target_step_id"] == step
        assert rows[0]["source_event_id"] == UUID(response.json()["id"])
        assert rows[0]["review_status"] == "pending" and rows[0]["source"] == "human_comment"
    else:
        assert rows == []
