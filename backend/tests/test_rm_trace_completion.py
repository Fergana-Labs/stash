"""Completion is an optional, private estimate, independent of stored rewards."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from backend.services.rm import trace_completion as completion

from .test_rm_api import _register
from .test_rm_trace_sections import setup_trace

pytestmark = pytest.mark.usefixtures("rm_title_generator")


def estimate():
    return completion.Estimate(
        tasks=[
            completion.Task(
                first_step=2,
                last_step=5,
                objective="Refund the order",
                checkpoints=[
                    completion.Checkpoint(step=2, completion=0, reason="Request received"),
                    completion.Checkpoint(step=4, completion=0.2, reason="Order located"),
                    completion.Checkpoint(
                        step=5, completion=None, reason="Refund claim is unverified"
                    ),
                ],
            )
        ]
    )


async def test_completion_cache_invalidates_with_evidence_and_does_not_change_grades(
    client, pool, monkeypatch
):
    auth, trace_id, _, steps = await setup_trace(client)
    complete = AsyncMock(return_value=estimate())
    monkeypatch.setattr(completion.llm, "complete_structured", complete)
    url = f"/api/v1/rm/traces/{trace_id}/completion"
    before = await pool.fetch(
        "SELECT metadata FROM rm_trace_steps WHERE trace_id=$1 ORDER BY idx", UUID(trace_id)
    )
    first = await client.post(url, headers=auth)
    assert first.status_code == 200, first.text
    task = first.json()["tasks"][0]
    assert task["first_step_id"] == steps[1]["id"]
    assert task["checkpoints"][1]["step_id"] == steps[3]["id"]
    assert task["checkpoints"][-1]["completion"] is None
    assert (await client.post(url, headers=auth)).json() == first.json()
    assert complete.await_count == 1
    assert json.loads(complete.call_args.kwargs["prompt"])["events"][-1]["step"] == 5
    assert (
        await pool.fetch(
            "SELECT metadata FROM rm_trace_steps WHERE trace_id=$1 ORDER BY idx", UUID(trace_id)
        )
        == before
    )
    await pool.execute(
        "UPDATE rm_trace_steps SET content='Refund failed' WHERE id=$1", UUID(steps[-1]["id"])
    )
    await client.post(url, headers=auth)
    assert complete.await_count == 2


async def test_authorization_precedes_reading_cached_completion(client, pool, monkeypatch):
    auth, trace_id, _, _ = await setup_trace(client)
    complete = AsyncMock(return_value=estimate())
    monkeypatch.setattr(completion.llm, "complete_structured", complete)
    url = f"/api/v1/rm/traces/{trace_id}/completion"
    await client.post(url, headers=auth)
    stranger = await _register(client)
    assert (await client.post(url, headers=stranger)).status_code == 404
    reviewer = await pool.fetchval("SELECT id FROM users ORDER BY created_at DESC LIMIT 1")
    await pool.execute(
        "INSERT INTO rm_wb_trace_reviewers(trace_id,user_id) VALUES($1,$2)",
        UUID(trace_id),
        reviewer,
    )
    assert (await client.post(url, headers=stranger)).json()["tasks"]
    await pool.execute("DELETE FROM rm_wb_trace_reviewers WHERE trace_id=$1", UUID(trace_id))
    assert (await client.post(url, headers=stranger)).status_code == 404
    assert complete.await_count == 1


async def test_concurrent_requests_share_work_and_provider_failure_does_not_break_browsing(
    client, pool, monkeypatch
):
    auth, trace_id, _, _ = await setup_trace(client)
    started, finish = asyncio.Event(), asyncio.Event()

    async def slow(**kwargs):
        started.set()
        await finish.wait()
        return estimate()

    complete = AsyncMock(side_effect=slow)
    monkeypatch.setattr(completion.llm, "complete_structured", complete)
    url = f"/api/v1/rm/traces/{trace_id}/completion"
    first = asyncio.create_task(client.post(url, headers=auth))
    await started.wait()
    assert (await client.post(url, headers=auth)).json()["pending"]
    finish.set()
    assert (await first).json()["tasks"]
    assert complete.await_count == 1
    await pool.execute("DELETE FROM rm_trace_completion WHERE trace_id=$1", UUID(trace_id))
    monkeypatch.setattr(
        completion.llm,
        "complete_structured",
        AsyncMock(side_effect=RuntimeError("private credentials")),
    )
    failed = await client.post(url, headers=auth)
    assert failed.status_code == 200
    assert failed.json() == {"tasks": [], "pending": False, "unavailable": True}
    await pool.execute("UPDATE rm_trace_completion SET retry_after=now() - interval '1 second'")
    monkeypatch.setattr(completion.llm, "complete_structured", AsyncMock(return_value=estimate()))
    assert (await client.post(url, headers=auth)).json()["tasks"]


def test_checkpoint_references_are_validated_and_unknowns_preserved():
    steps = [{"id": str(i), "role": "user" if i == 1 else "assistant"} for i in range(5)]
    valid = estimate()
    valid.tasks[0].checkpoints[0].completion = 0.3
    assert (
        completion._resolve(valid, steps, set(range(1, 6)))["tasks"][0]["checkpoints"][0][
            "completion"
        ]
        == 0
    )
    assert (
        completion._resolve(valid, steps, set(range(1, 6)))["tasks"][0]["checkpoints"][-1][
            "completion"
        ]
        is None
    )
    for changes in [
        {"first_step": 1},
        {"last_step": 10},
        {"checkpoints": list(reversed(valid.tasks[0].checkpoints))},
    ]:
        with pytest.raises(ValueError):
            completion._resolve(
                completion.Estimate(tasks=[valid.tasks[0].model_copy(update=changes)]),
                steps,
                set(range(1, 6)),
            )
    with pytest.raises(ValueError):
        completion._resolve(completion.Estimate(tasks=valid.tasks * 2), steps, set(range(1, 6)))
    with pytest.raises(ValueError):
        completion._resolve(valid, steps, {1, 2, 5})


@pytest.mark.parametrize("value", [-0.01, 1.1, float("nan")])
def test_invalid_percentages_are_rejected(value):
    with pytest.raises(ValueError):
        completion.Checkpoint(step=1, completion=value, reason="Invalid")


def test_sampling_is_bounded_and_preserves_ends_and_short_requests():
    steps = [
        {
            "role": "tool",
            "content": "x" * 10000,
            "tool_name": "read",
            "tool_input": {"value": "y" * 10000},
        }
        for _ in range(1000)
    ]
    steps[703] = {**steps[703], "role": "user", "content": "Now do a different task"}
    sample = completion._sample(steps)
    assert len(sample) <= 104
    assert sample[0]["step"] == 1 and sample[-1]["step"] == 1000
    assert any(event["step"] == 704 for event in sample)
    assert len(json.dumps(sample)) < 170000
