"""Step labels and rule scores: what each step of a trace is, and what it earned.

The labeling model is mocked. These tests pin how a trace is cut into
chunks, what is stored, how it reaches the API, and when a trace is labeled.
"""

import json
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.services.rm import step_labeler, step_labeling, step_scoring, workbench_auto

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
        # A trace is annotated once the agent has responded.
        {"role": "assistant", "content": "Let me look again."},
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
    "a4": _label("agent", type="status_update"),
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
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "TYPESAFE_API_KEY", None)
    return calls


@pytest.fixture
def checks(monkeypatch):
    """Stand in for the grading model: every quality check picks the top level."""
    asked = []

    async def quality_check(client, chunks, chunk, label, rubric):
        asked.append((chunk["chunk_id"], rubric))
        top = len(step_scoring.CHECKS[rubric][1]) - 1
        return {"rubric": rubric, "grader": "the grading model", "probabilities": {top: 1.0}}

    monkeypatch.setattr(step_labeling, "quality_check", quality_check)
    monkeypatch.setattr(settings, "TYPESAFE_API_KEY", "ts-test")
    return asked


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


async def _detail(client: AsyncClient, auth: dict, trace_id: UUID) -> dict:
    return (await client.get(f"/api/v1/rm/traces/{trace_id}", headers=auth)).json()


async def _evaluation(client: AsyncClient, auth: dict, trace_id: UUID) -> dict:
    response = await client.get(f"/api/v1/rm/workbench/traces/{trace_id}/evaluation", headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


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
        ("a4", "agent_message", 8),
    ]
    assert chunks[1]["result"] == "LF3000" and chunks[1]["duplicate_of"] is None
    assert chunks[2]["result"] == "error: timeout" and chunks[2]["duplicate_of"] == "a1"


def test_score_numbers_keep_their_order():
    answer = _label(
        "agent", type="output", is_output=True, outcome="answer", stance="asserted", coverage="1/1"
    )
    not_found = dict(answer, outcome="not_found")
    best_unconfirmed = step_scoring.score_step(
        answer, None, {"rubric": "answer_unconfirmed", "probabilities": {3: 1.0}}
    )["outcome"]
    worst_not_found = step_scoring.score_step(
        not_found, None, {"rubric": "not_found_unconfirmed", "probabilities": {0: 1.0}}
    )["outcome"]
    # An answer nobody confirmed never beats one the user accepted; an honest "not found" always beats a rejected answer.
    assert (
        best_unconfirmed == pytest.approx(0.40)
        and best_unconfirmed < step_scoring.ANSWER["implicit_positive"][1]
    )
    assert (
        worst_not_found == pytest.approx(-0.35)
        and worst_not_found > step_scoring.ANSWER["rejected"][1]
    )
    # Work is never rewarded: a lookup that was relied on becomes free, not positive.
    lookup = _label("agent", type="tool_call", effect="read", result="data")
    assert (
        step_scoring.score_step(lookup, None, {"rubric": "tool", "probabilities": {4: 1.0}})["cost"]
        == 0.0
    )
    # A verdict is ground truth; no quality check is asked.
    assert step_scoring.check_for(answer, "rejected") is None
    assert step_scoring.check_for(answer, None) == "answer_unconfirmed"


async def test_annotating_a_trace_labels_and_scores_each_step(client, labeler, checks):
    auth = await _account(client)
    trace_id = await _import(client, auth, TRACE)

    await workbench_auto.process_trace(trace_id)
    assert labeler["label"] == 6  # one call per chunk
    # Quality checks only where the labels give no ground truth.
    assert sorted(checks) == [("a1", "tool"), ("a2", "tool")]

    detail = await _detail(client, auth, trace_id)
    steps = detail["steps"]
    assert (
        steps[0]["metadata"]["label"]["intent"] == "new_request"
        and steps[0]["metadata"]["label"]["task_id"] == "t1"
    )
    assert "reward" not in steps[0]["metadata"]  # user steps are labeled, not scored
    assert steps[1]["metadata"] is None  # the double-logged copy is not a chunk
    assert steps[3]["metadata"] is None  # a tool result is labeled with its call
    # The user's reaction names the answer it is about.
    assert (
        steps[7]["metadata"]["label"]["verdict"] == "rejected"
        and steps[7]["metadata"]["label"]["verdict_target"] == "a3"
    )
    answer = steps[6]["metadata"]["reward"]
    assert answer["is_answer"] and answer["score"] == -1.0  # asserted answer the user rejected
    # Blame from the rejected answer: 0.3 x -1.0 x 0.8^k for the step k places back.
    repeated = steps[4]["metadata"]["reward"]
    assert repeated["shared"] == [{"from": "a3", "verdict": "rejected", "value": -0.24}]
    assert steps[2]["metadata"]["reward"]["shared"][0]["value"] == pytest.approx(-0.192)
    # Lookup -0.03, error -0.10, repeat -0.10, quality check +0.03.
    assert repeated["base"] == pytest.approx(-0.23) and repeated["score"] == pytest.approx(-0.20)
    assert repeated["jev"]["short"] == "its result was used later"
    assert detail["step_scores"]["episodes"] == [
        {
            "task": "t1",
            "score": -1.0,
            "rubric_b_only": -1.0,
            "answer": -1.0,
            "costs": -0.2,
            "has_answer": True,
        }
    ]

    # The same numbers are the trace's automatic annotation: an action's credit is its total.
    current = (await _evaluation(client, auth, trace_id))["current"]
    assert current["status"] == "completed" and current["outcome"] == "failure"
    credits = {c["index"]: c["expected_credit"] for c in current["credits"]}
    assert credits[6] == -1.0
    assert credits[4] == pytest.approx(repeated["score"] + repeated["shared_total"])


async def test_without_the_grading_model_the_fixed_points_stand(client, labeler):
    auth = await _account(client)
    trace_id = await _import(client, auth, TRACE)

    await workbench_auto.process_trace(trace_id)
    detail = await _detail(client, auth, trace_id)
    repeated = detail["steps"][4]["metadata"]["reward"]
    assert repeated["jev"] is None and repeated["score"] == pytest.approx(-0.23)
    assert detail["step_scores"]["episodes"][0]["answer"] == -1.0


async def test_a_trace_that_arrives_labeled_is_never_sent_to_a_model(client, labeler, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    auth = await _account(client)
    ids = {0: "u1", 2: "a1", 4: "a2", 6: "a3", 7: "u2", 8: "a4"}
    labeled = {
        **TRACE,
        "steps": [
            {**step, "metadata": {"label": dict(LABELS[ids[i]], chunk_id=ids[i], task_id="t1")}}
            if i in ids
            else step
            for i, step in enumerate(TRACE["steps"])
        ],
    }
    trace_id = await _import(client, auth, labeled)

    await workbench_auto.process_trace(trace_id)
    assert labeler["label"] == 0
    evaluation = await _evaluation(client, auth, trace_id)
    assert evaluation["configured"] is True
    current = evaluation["current"]
    # Scored from the labels it came with: the rejected answer makes it a failure.
    assert current["status"] == "completed" and current["outcome"] == "failure"
    assert {c["index"]: c["expected_credit"] for c in current["credits"]}[6] == -1.0
    detail = await _detail(client, auth, trace_id)
    assert detail["steps"][6]["metadata"]["label"]["outcome"] == "answer"


async def test_scores_a_trace_arrived_with_are_shown_as_they_are(client, labeler, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    auth = await _account(client)
    summary = {
        "score": 0.9,
        "episodes": [{"task": "t1", "score": 0.9, "rubric_b_only": 0.9, "answer": 1.0, "costs": -0.1, "has_answer": True}],
        "signals": {"rejections": 0, "confirmations": 1, "tool_errors": 0, "answers": 1},
    }  # fmt: skip
    scored = {
        "id": "scored-1",
        "title": "Scored elsewhere",
        "metadata": {"rubric_summary": summary},
        "steps": [
            {"role": "user", "content": "Find it", "metadata": {"label": dict(LABELS["u1"], chunk_id="u1", task_id="t1")}},
            {"role": "assistant", "content": "Here it is.", "metadata": {
                "label": dict(LABELS["a3"], chunk_id="a1", task_id="t1"),
                "reward": {"base": 1.0, "score": 1.0, "total": 1.0, "is_answer": True},
            }},
        ],
    }  # fmt: skip
    trace_id = await _import(client, auth, scored)

    await workbench_auto.process_trace(trace_id)
    current = (await _evaluation(client, auth, trace_id))["current"]
    assert current["outcome"] == "success" and current["outcome_probabilities"] == {"score": 0.9}
    assert current["credits"][0]["expected_credit"] == 1.0
    assert (await _detail(client, auth, trace_id))["step_scores"] == summary
