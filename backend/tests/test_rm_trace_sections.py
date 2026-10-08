"""Section copy is cached by evidence, private to the trace, and optional for browsing."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from backend.services.rm import trace_sections

from .test_rm_api import REFUND_TRACE, _detail, _import, _register

pytestmark = pytest.mark.usefixtures("rm_title_generator")


def generated(title="Looking up an order"):
    return trace_sections._response_model(1)(
        section_0=trace_sections.SectionCopy(
            title=title,
            summary="Looks up the order and responds to the refund request.",
            objective="Look up the order",
            score=0.83,
            score_reason="The tool returns the requested order.",
        )
    )


async def setup_trace(client):
    auth = await _register(client)
    trace_id = (await _import(client, auth, REFUND_TRACE))[0]
    steps = (await _detail(client, auth, trace_id))["steps"]
    body = {"sections": [{"first_step_id": steps[1]["id"], "last_step_id": steps[-1]["id"]}]}
    return auth, trace_id, body, steps


async def test_generated_copy_reused_and_invalidated_by_changed_evidence(client, pool, monkeypatch):
    auth, trace_id, body, steps = await setup_trace(client)
    complete = AsyncMock(return_value=generated())
    monkeypatch.setattr(trace_sections.llm, "complete_structured", complete)
    url = f"/api/v1/rm/traces/{trace_id}/section-summaries"
    first = await client.post(url, headers=auth, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["sections"][0]["title"] == "Looking up an order"
    assert first.json()["sections"][0]["score"] == 0.83
    assert "NO assumed overall task" in complete.call_args.kwargs["system"]
    assert not first.json()["pending"]
    assert (await client.post(url, headers=auth, json=body)).json() == first.json()
    assert complete.await_count == 1
    source = json.loads(complete.call_args.kwargs["prompt"])["section_0"]["events"]
    assert any(s["tool"] == "lookup_order" for s in source)
    assert any("refund" in s["content"] for s in source)
    await pool.execute(
        "UPDATE rm_trace_steps SET content='Refund attempt failed' WHERE id=$1",
        UUID(steps[-1]["id"]),
    )
    await client.post(url, headers=auth, json=body)
    assert complete.await_count == 2


async def test_authorization_and_range_validation_precede_cache_or_inference(
    client, pool, monkeypatch
):
    auth, trace_id, body, steps = await setup_trace(client)
    complete = AsyncMock(return_value=generated())
    monkeypatch.setattr(trace_sections.llm, "complete_structured", complete)
    url = f"/api/v1/rm/traces/{trace_id}/section-summaries"
    await client.post(url, headers=auth, json=body)
    stranger = await _register(client)
    assert (await client.post(url, headers=stranger, json=body)).status_code == 404
    reverse = {"sections": [{"first_step_id": steps[-1]["id"], "last_step_id": steps[1]["id"]}]}
    assert (await client.post(url, headers=auth, json=reverse)).status_code == 422
    assert (
        await client.post(url, headers=auth, json={"sections": body["sections"] * 5})
    ).status_code == 422
    other_trace = (await _import(client, auth, {**REFUND_TRACE, "id": "another-trace"}))[0]
    assert (
        await client.post(
            f"/api/v1/rm/traces/{other_trace}/section-summaries", headers=auth, json=body
        )
    ).status_code == 422
    assert complete.await_count == 1
    reviewer = await pool.fetchval("SELECT id FROM users ORDER BY created_at DESC LIMIT 1")
    await pool.execute(
        "INSERT INTO rm_wb_trace_reviewers(trace_id,user_id) VALUES($1,$2)",
        UUID(trace_id),
        reviewer,
    )
    assert (await client.post(url, headers=stranger, json=body)).status_code == 200
    assert complete.await_count == 1
    await pool.execute("DELETE FROM rm_wb_trace_reviewers WHERE trace_id=$1", UUID(trace_id))
    assert (await client.post(url, headers=stranger, json=body)).status_code == 404


async def test_concurrent_requests_share_work_and_failed_generation_is_retryable(
    client, pool, monkeypatch
):
    auth, trace_id, body, _ = await setup_trace(client)
    started, finish = asyncio.Event(), asyncio.Event()

    async def slow(**kwargs):
        started.set()
        await finish.wait()
        return generated()

    complete = AsyncMock(side_effect=slow)
    monkeypatch.setattr(trace_sections.llm, "complete_structured", complete)
    url = f"/api/v1/rm/traces/{trace_id}/section-summaries"
    first = asyncio.create_task(client.post(url, headers=auth, json=body))
    await started.wait()
    concurrent = await client.post(url, headers=auth, json=body)
    assert concurrent.json()["pending"]
    finish.set()
    assert (await first).json()["sections"]
    assert complete.await_count == 1
    await pool.execute("DELETE FROM rm_trace_section_summaries WHERE trace_id=$1", UUID(trace_id))
    monkeypatch.setattr(
        trace_sections.llm,
        "complete_structured",
        AsyncMock(side_effect=RuntimeError("private provider details")),
    )
    failed = await client.post(url, headers=auth, json=body)
    assert failed.status_code == 200
    assert failed.json()["unavailable"]
    assert "private provider" not in failed.text
    await pool.execute(
        "UPDATE rm_trace_section_summaries SET retry_after=now() - interval '1 second'"
    )
    monkeypatch.setattr(
        trace_sections.llm, "complete_structured", AsyncMock(return_value=generated())
    )
    assert (await client.post(url, headers=auth, json=body)).json()["sections"]


def test_sampling_is_bounded_and_includes_both_ends():
    steps = [
        {
            "role": "assistant",
            "content": str(i) + "x" * 10000,
            "tool_name": "browser",
            "tool_input": {"url": "y" * 10000},
        }
        for i in range(1000)
    ]
    sample = trace_sections._sample(steps)
    assert len(sample) <= 32
    assert sample[0]["content"].startswith("0x")
    assert sample[-1]["content"].startswith("999x")
    assert len(json.dumps(sample)) < 43000


def test_provider_copy_is_bounded_without_failing_on_a_long_sentence():
    response = trace_sections._response_model(1).model_validate(
        {
            "section_0": {
                "title": "Searching\n supplier sites",
                "summary": "Checking supplier catalogs. " * 20,
                "objective": "Find a piston kit",
                "score": None,
                "score_reason": "The result is not recorded",
            }
        }
    )
    assert response.section_0.title == "Searching supplier sites"
    assert len(response.section_0.summary) <= 180
    assert response.section_0.summary.endswith("…")
    with pytest.raises(ValueError):
        trace_sections._response_model(1).model_validate(
            {"section_1": {"title": "Wrong section", "summary": "Wrong key"}}
        )


@pytest.mark.parametrize("score", [-0.1, 1.1, float("nan")])
def test_section_success_scores_reject_invalid_numbers(score):
    with pytest.raises(ValueError):
        trace_sections.SectionCopy(
            title="Checking order",
            summary="Checked the order.",
            objective="Find order",
            score=score,
            score_reason="Returned order",
        )


async def test_local_context_changes_invalidate_only_dependent_assessment(
    client, pool, monkeypatch
):
    auth, trace_id, _, steps = await setup_trace(client)
    body = {"sections": [{"first_step_id": steps[2]["id"], "last_step_id": steps[-1]["id"]}]}
    complete = AsyncMock(return_value=generated())
    monkeypatch.setattr(trace_sections.llm, "complete_structured", complete)
    url = f"/api/v1/rm/traces/{trace_id}/section-summaries"
    await client.post(url, headers=auth, json=body)
    context = json.loads(complete.call_args.kwargs["prompt"])["section_0"]["preceding_context"]
    assert any("refund" in step["content"] for step in context)
    await pool.execute(
        "UPDATE rm_trace_steps SET content='Check delivery only, do not refund' WHERE id=$1",
        UUID(steps[1]["id"]),
    )
    await client.post(url, headers=auth, json=body)
    assert complete.await_count == 2
