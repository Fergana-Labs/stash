"""Automatic step labels: say what each step of a trace is, and show it.

The labeling model is mocked. These tests pin how a trace is cut into
chunks, what is stored, how it reaches the API, and when a trace is labeled.
"""

import json
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.services.rm import step_labeler, step_labeling

from .conftest import unique_name

pytestmark = pytest.mark.usefixtures("rm_title_generator")

TRACE = {
    "id": "parts-1",
    "title": "Find a part",
    "steps": [
        {"role": "user", "content": "Need a filter for unit 12"},
        {"role": "user", "content": "Need a filter for unit 12"},
        {
            "role": "assistant",
            "content": "",
            "tool_name": "search",
            "tool_input": {"q": "filter"},
            "tool_call_id": "c1",
        },
        {"role": "tool", "content": "LF3000", "tool_name": "search", "tool_call_id": "c1"},
        {
            "role": "assistant",
            "content": "",
            "tool_name": "search",
            "tool_input": {"q": "filter"},
            "tool_call_id": "c2",
        },
        {"role": "tool", "content": "error: timeout", "tool_name": "search", "tool_call_id": "c2"},
        {"role": "assistant", "content": "Use LF3000."},
        {"role": "user", "content": "No, that is the wrong one"},
    ],
}


def _label(actor, **fields):
    base = dict.fromkeys(
        ("intent", "verdict", "verdict_target", "sentiment", "type", "effect", "result", "outcome", "stance", "coverage", "note"))  # fmt: skip
    return {**base, "actor": actor, "is_output": False, "evidence": "", **fields}


LABELS = {
    "u1": _label("user", intent="new_request", verdict="none", sentiment="neutral"),
    "a1": _label("agent", type="tool_call", effect="read", result="data"),
    "a2": _label("agent", type="tool_call", effect="read", result="error"),
    "a3": _label(
        "agent", type="output", is_output=True, outcome="answer", stance="asserted", coverage="1/1"
    ),
    "u2": _label(
        "user", intent="correction", verdict="rejected", verdict_target="a3", sentiment="negative"
    ),
}


@pytest.fixture
def labeler(monkeypatch):
    """Stand in for the labeling model; count the calls."""
    calls = {"label": 0}

    async def label_chunk(client, cache_key, transcript, chunk):
        calls["label"] += 1
        label = dict(LABELS[chunk["chunk_id"]], chunk_id=chunk["chunk_id"])
        if chunk["kind"] == "tool_call":
            label.update(tool=chunk["tool"], duplicate_of=chunk["duplicate_of"])
        return label

    monkeypatch.setattr(step_labeler, "label_chunk", label_chunk)
    monkeypatch.setattr(settings, "STEP_LABELING_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    return calls


async def _account(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("labels"), "password": "securepassword1"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['api_key']}"}


async def _import(client: AsyncClient, auth: dict, trace: dict) -> UUID:
    response = await client.post(
        "/api/v1/rm/traces/import",
        json={"format": "stash", "data": json.dumps(trace)},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    return UUID(response.json()["trace_ids"][0])


def test_chunks_pair_tool_results_merge_double_logged_messages_and_spot_repeats():
    steps = [
        {
            "idx": i,
            "metadata": None,
            "tool_name": None,
            "tool_input": None,
            "tool_call_id": None,
            **s,
        }
        for i, s in enumerate(TRACE["steps"])
    ]
    chunks = step_labeler.build_chunks(steps)
    assert [(c["chunk_id"], c["kind"], c["idx"]) for c in chunks] == [
        ("u1", "user_message", 0),
        ("a1", "tool_call", 2),
        ("a2", "tool_call", 4),
        ("a3", "agent_message", 6),
        ("u2", "user_message", 7),
    ]
    assert chunks[1]["result"] == "LF3000" and chunks[1]["duplicate_of"] is None
    assert chunks[2]["result"] == "error: timeout" and chunks[2]["duplicate_of"] == "a1"


async def test_labeling_a_trace_puts_a_label_on_each_step(client, labeler):
    auth = await _account(client)
    trace_id = await _import(client, auth, TRACE)

    assert await step_labeling.label_trace(trace_id) == "succeeded"
    assert labeler["label"] == 5  # one call per chunk

    detail = (await client.get(f"/api/v1/rm/traces/{trace_id}", headers=auth)).json()
    steps = detail["steps"]
    assert "step_labeling" not in detail
    assert (
        steps[0]["metadata"]["label"]["intent"] == "new_request"
        and steps[0]["metadata"]["label"]["task_id"] == "t1"
    )
    assert steps[1]["metadata"] is None  # the double-logged copy is not a chunk
    assert steps[3]["metadata"] is None  # a tool result is labeled with its call
    assert (
        steps[4]["metadata"]["label"]["duplicate_of"] == "a1"
        and steps[4]["metadata"]["label"]["result"] == "error"
    )
    assert steps[6]["metadata"]["label"]["is_output"] is True
    # The user's reaction names the answer it is about.
    assert (
        steps[7]["metadata"]["label"]["verdict"] == "rejected"
        and steps[7]["metadata"]["label"]["verdict_target"] == "a3"
    )


async def test_imported_labels_win_and_are_never_replaced(client, pool, labeler):
    auth = await _account(client)
    imported = {
        **TRACE,
        "steps": [
            {
                **TRACE["steps"][0],
                "metadata": {"label": {"chunk_id": "u1", "actor": "user", "intent": "follow_up"}},
            },
            *TRACE["steps"][1:],
        ],
    }
    trace_id = await _import(client, auth, imported)
    await pool.execute(
        "UPDATE rm_traces SET updated_at = now() - interval '1 hour' WHERE id = $1", trace_id
    )

    assert await step_labeling.claim_due() == []
    assert labeler["label"] == 0


async def test_a_trace_is_relabeled_only_when_its_steps_change(client, labeler):
    auth = await _account(client)
    trace_id = await _import(client, auth, TRACE)
    await step_labeling.label_trace(trace_id)

    assert await step_labeling.label_trace(trace_id) == "unchanged"
    assert labeler["label"] == 5

    # The user's last message is removed, so the trace's steps differ.
    assert await _import(client, auth, {**TRACE, "steps": TRACE["steps"][:-1]}) == trace_id
    labeler["label"] = 0
    assert await step_labeling.label_trace(trace_id) == "succeeded"
    assert labeler["label"] == 4


async def test_a_trace_over_the_limit_is_skipped_with_a_reason(client, labeler, monkeypatch):
    auth = await _account(client)
    trace_id = await _import(client, auth, TRACE)
    monkeypatch.setattr(settings, "STEP_LABELING_MAX_CHUNKS", 2)

    assert await step_labeling.label_trace(trace_id) == "skipped"
    assert labeler["label"] == 0
    detail = (await client.get(f"/api/v1/rm/traces/{trace_id}", headers=auth)).json()
    assert detail["step_labeling"] == {
        "status": "skipped",
        "error": "The trace has 5 steps; automatic labeling handles up to 2.",
    }
    assert all(step["metadata"] is None for step in detail["steps"])


async def test_a_provider_failure_is_retried_a_bounded_number_of_times(
    client, labeler, monkeypatch
):
    auth = await _account(client)
    trace_id = await _import(client, auth, TRACE)

    async def down(client, cache_key, transcript, chunk):
        labeler["label"] += 1
        raise step_labeler.LabelingError("label request returned 503")

    monkeypatch.setattr(step_labeler, "label_chunk", down)
    outcomes = [await step_labeling.label_trace(trace_id) for _ in range(5)]
    assert outcomes == ["failed", "failed", "failed", "unchanged", "unchanged"]
    assert labeler["label"] == step_labeling.MAX_ATTEMPTS


async def test_the_sweep_claims_quiet_traces_for_enabled_accounts_only(
    client, pool, labeler, monkeypatch
):
    auth = await _account(client)
    trace_id = await _import(client, auth, TRACE)

    # Still being written to: left alone.
    assert await step_labeling.claim_due() == []
    await pool.execute(
        "UPDATE rm_traces SET updated_at = now() - interval '1 hour' WHERE id = $1", trace_id
    )

    monkeypatch.setattr(settings, "STEP_LABELING_ENABLED", False)
    assert await step_labeling.claim_due() == []
    monkeypatch.setattr(settings, "STEP_LABELING_ENABLED", True)

    # A claim holds, so the next sweep does not repeat it.
    assert await step_labeling.claim_due() == [trace_id]
    assert await step_labeling.claim_due() == []
    detail = (await client.get(f"/api/v1/rm/traces/{trace_id}", headers=auth)).json()
    assert detail["step_labeling"] == {"status": "pending", "error": None}

    assert await step_labeling.label_trace(trace_id) == "succeeded"
    assert await step_labeling.claim_due() == []
    # A claim nobody finished is released.
    await pool.execute(
        "UPDATE rm_step_labels SET status = 'pending', fingerprint = '', checked_at = now() - interval '1 hour'"
    )
    assert await step_labeling.claim_due() == [trace_id]


def test_the_beat_task_only_dispatches(monkeypatch):
    import asyncio

    from backend.tasks import step_labeling as tasks

    ids = [UUID(int=1), UUID(int=2)]

    async def claim_due():
        return ids

    sent = []
    monkeypatch.setattr(step_labeling, "claim_due", claim_due)
    monkeypatch.setattr(tasks, "run_async", asyncio.run)
    monkeypatch.setattr(tasks.label_trace, "delay", sent.append)
    assert tasks.reconcile() == 2
    assert sent == [str(i) for i in ids]
