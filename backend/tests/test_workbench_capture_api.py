"""Capture persistence/idempotency tests. Run against an isolated test database."""

import asyncio
from uuid import UUID

from backend.services.rm import workbench as service
from backend.services.rm import workbench_capture as capture
from backend.services.rm import workbench_grader as engine
from backend.tasks import workbench as tasks

from .test_rm_api import _import, _register


async def setup_trace(client, pool, monkeypatch, name="capture", corrections=1):
    auth = await _register(client)
    monkeypatch.setattr(tasks.prepare_feedback, "delay", lambda *a: None)
    messages = [{"role": "user", "content": "Fix the parser"}]
    for i in range(corrections):
        messages.extend(
            [
                {"role": "assistant", "content": f"All tests pass, revision {i}"},
                {"role": "user", "content": f"Wrong: tests failed in revision {i}"},
            ]
        )
    ids = await _import(client, auth, {"id": name, "steps": messages})
    trace = dict(await pool.fetchrow("SELECT * FROM rm_traces WHERE id=$1", UUID(ids[0])))
    steps = [
        dict(s)
        for s in await pool.fetch(
            "SELECT * FROM rm_trace_steps WHERE trace_id=$1 ORDER BY idx", trace["id"]
        )
    ]
    return trace, steps


def signal(snapshot):
    return capture.CorrectionSignal(
        correction=True,
        target_step_id=snapshot["target_candidates"][-1],
        evidence_quote=snapshot["source_event"]["content"],
        change_kind="agent_error",
        explanation="Explicit user correction",
    )


async def test_input_saved_before_classification_and_one_pending_feedback(
    client, pool, monkeypatch, rm_title_generator
):
    trace, steps = await setup_trace(client, pool, monkeypatch)
    calls = []

    async def classify(snapshot):
        saved = await pool.fetchrow(
            "SELECT * FROM rm_wb_feedback_scans WHERE source_event_id=$1", steps[2]["id"]
        )
        assert saved["input_snapshot"] == snapshot
        assert saved["status"] == "running"
        calls.append(snapshot)
        return signal(snapshot)

    monkeypatch.setattr(capture, "classify", classify)
    first = await capture.scan_trace(trace, steps)
    second = await capture.scan_trace(trace, steps)
    assert first["feedback_created"] == 1 and second["calls"] == 0
    assert len(calls) == 1
    feedback = await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE trace_id=$1", trace["id"])
    assert feedback["source"] == "trace_extraction"
    assert feedback["source_event_id"] == steps[2]["id"]
    assert feedback["target_step_id"] == steps[1]["id"]
    assert feedback["review_status"] == "pending" and feedback["reviewed_by"] is None
    assert feedback["proposed_verdict"] is None


async def test_scan_pass_is_bounded_then_continues(client, pool, monkeypatch, rm_title_generator):
    trace, steps = await setup_trace(client, pool, monkeypatch, corrections=6)

    async def classify(snapshot):
        return capture.CorrectionSignal(correction=False, explanation="No defensible attribution")

    monkeypatch.setattr(capture, "classify", classify)
    first = await capture.scan_trace(trace, steps)
    second = await capture.scan_trace(trace, steps)
    assert first["calls"] == capture.MAX_CALLS_PER_PASS
    assert first["more"]
    assert second["calls"] == 2 and not second["more"]
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_feedback") == 0


async def test_concurrent_scans_do_not_duplicate_paid_classification(
    client, pool, monkeypatch, rm_title_generator
):
    trace, steps = await setup_trace(client, pool, monkeypatch)
    calls = 0

    async def classify(snapshot):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.03)
        return signal(snapshot)

    monkeypatch.setattr(capture, "classify", classify)
    await asyncio.gather(capture.scan_trace(trace, steps), capture.scan_trace(trace, steps))
    assert calls == 1
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_feedback") == 1


async def test_owner_daily_budget_is_enforced(client, pool, monkeypatch, rm_title_generator):
    trace, steps = await setup_trace(client, pool, monkeypatch, corrections=3)
    monkeypatch.setattr(capture, "MAX_CALLS_PER_OWNER_DAY", 1)

    async def classify(snapshot):
        return capture.CorrectionSignal(correction=False, explanation="Not a correction")

    monkeypatch.setattr(capture, "classify", classify)
    first = await capture.scan_trace(trace, steps)
    second = await capture.scan_trace(trace, steps)
    assert first["calls"] == 1 and first["budget_limited"]
    assert second["calls"] == 0 and second["budget_limited"]


async def test_failure_retries_are_bounded_and_never_create_labels(
    client, pool, monkeypatch, rm_title_generator
):
    trace, steps = await setup_trace(client, pool, monkeypatch)

    async def classify(snapshot):
        raise RuntimeError("PRIVATE PROVIDER BODY")

    monkeypatch.setattr(capture, "classify", classify)
    for i in range(3):
        result = await capture.scan_trace(trace, steps)
        assert result["calls"] == 1
        await pool.execute(
            "UPDATE rm_wb_feedback_scans SET due_at=now() WHERE trace_id=$1", trace["id"]
        )
    result = await capture.scan_trace(trace, steps)
    assert result["calls"] == 0
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_feedback") == 0
    error = await pool.fetchval(
        "SELECT error FROM rm_wb_feedback_scans WHERE source_event_id=$1", steps[2]["id"]
    )
    assert "PRIVATE" not in error


async def test_harness_message_creates_skip_marker_without_inference(
    client, pool, monkeypatch, rm_title_generator
):
    trace, steps = await setup_trace(client, pool, monkeypatch)
    await pool.execute(
        "UPDATE rm_trace_steps SET content=$2 WHERE id=$1",
        steps[2]["id"],
        "<teammate-message>Wrong tests</teammate-message>",
    )
    steps[2]["content"] = "<teammate-message>Wrong tests</teammate-message>"

    async def classify(snapshot):
        raise AssertionError("Must not classify harness text")

    monkeypatch.setattr(capture, "classify", classify)
    result = await capture.scan_trace(trace, steps)
    assert result["calls"] == 0
    assert (
        await pool.fetchval(
            "SELECT status FROM rm_wb_feedback_scans WHERE source_event_id=$1", steps[2]["id"]
        )
        == "skipped"
    )


async def test_final_running_lease_recovers_without_a_fourth_call(
    client, pool, monkeypatch, rm_title_generator
):
    trace, steps = await setup_trace(client, pool, monkeypatch)
    snapshot = capture.build_scan_input(steps, steps[2])
    await capture._reserve(trace, steps[2], snapshot)
    await pool.execute(
        "UPDATE rm_wb_feedback_scans SET attempts=3 WHERE source_event_id=$1", steps[2]["id"]
    )

    async def classify(snapshot):
        raise AssertionError("A fourth paid attempt is forbidden")

    monkeypatch.setattr(capture, "classify", classify)
    live = await capture.scan_trace(trace, steps)
    assert live["more"] and not live["calls"]
    await pool.execute(
        "UPDATE rm_wb_feedback_scans SET last_attempt_at=now()-interval '6 minutes' WHERE source_event_id=$1",
        steps[2]["id"],
    )
    expired = await capture.scan_trace(trace, steps)
    assert not expired["more"] and not expired["calls"]
    assert (
        await pool.fetchval(
            "SELECT status FROM rm_wb_feedback_scans WHERE source_event_id=$1", steps[2]["id"]
        )
        == "failed"
    )


async def test_grading_continues_when_capture_budget_is_exhausted(
    client, pool, monkeypatch, rm_title_generator
):
    trace, steps = await setup_trace(client, pool, monkeypatch, corrections=3)
    monkeypatch.setattr(capture, "MAX_CALLS_PER_OWNER_DAY", 1)
    monkeypatch.setattr(service, "MAX_ACTIONS_PER_PASS", 1)
    await service.create_grader(
        trace["owner_user_id"],
        "Test capture scheduling",
        {},
        {"criteria": engine.DEFAULT_CRITERIA},
    )
    assessed = []

    async def grade(snapshot):
        assessed.append(snapshot)
        return {
            "results": [
                {"criterion_id": c["id"], "verdict": "meets"} for c in snapshot["criteria"]
            ],
            "raw_output": {},
        }

    async def classify(snapshot):
        return capture.CorrectionSignal(correction=False, explanation="Not a correction")

    monkeypatch.setattr(engine, "grade", grade)
    monkeypatch.setattr(capture, "classify", classify)
    await service.process_trace(trace["id"])
    first_queue = await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", trace["id"])
    assert len(assessed) == 1
    assert first_queue["status"] == "queued"
    assert (first_queue["due_at"] - first_queue["processed_at"]).total_seconds() < 20
    await service.process_trace(trace["id"])
    await service.process_trace(trace["id"])
    final_queue = await pool.fetchrow("SELECT * FROM rm_wb_queue WHERE trace_id=$1", trace["id"])
    assert len(assessed) == 3 and final_queue["status"] == "queued"
    assert final_queue["due_at"].hour == 0 and final_queue["due_at"].minute == 0
    assert final_queue["due_at"].date() > final_queue["processed_at"].date()
