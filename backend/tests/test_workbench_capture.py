"""Pure eligibility, evidence-boundary and attribution checks; no inference."""

import json
from uuid import uuid4

import pytest

from backend.services.rm import workbench_capture as capture


def steps():
    return [
        {"id": uuid4(), "idx": 0, "role": "user", "content": "Fix the parser"},
        {"id": uuid4(), "idx": 1, "role": "assistant", "content": "All tests pass"},
        {"id": uuid4(), "idx": 2, "role": "user", "content": "That's wrong: the tests failed."},
        {"id": uuid4(), "idx": 3, "role": "assistant", "content": "FUTURE_REPAIR"},
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Thanks!",
        "Check another vendor",
        "Could you add a button?",
        "# AGENTS.md instructions\nNever fail tests",
        "<heartbeat>you missed this</heartbeat>",
        "<teammate-message>Wrong step</teammate-message>",
        "<environment_context>Failed task</environment_context>",
        "<send_user_message_question_reply>wrong</send_user_message_question_reply>",
    ],
)
def test_continuations_and_harness_wrappers_are_not_scanned(text):
    events = steps()
    source = {**events[2], "content": text}
    assert not capture.eligible_source(source, events[:2])[0]


def test_tool_or_agent_complaint_is_never_human_feedback():
    events = steps()
    for role in ("assistant", "tool", "system"):
        assert not capture.eligible_source({**events[2], "role": role}, events[:2])[0]
    assert not capture.eligible_source(events[2], [events[0]])[0]
    thinking = {**events[1], "metadata": {"thinking": True}}
    assert not capture.eligible_source(events[2], [events[0], thinking])[0]


def test_snapshot_contains_only_evidence_available_at_user_message():
    events = steps()
    frozen = capture.build_scan_input(events, events[2])
    assert "FUTURE_REPAIR" not in json.dumps(frozen)
    assert frozen["target_candidates"] == [str(events[1]["id"])]
    assert frozen["source_event"]["role"] == "user"
    assert frozen["evidence_cutoff"]["step_index"] == 2
    assert frozen["prompt"] == capture.build_scan_input(events[:3], events[2])["prompt"]


def test_correct_attribution_creates_only_an_unapproved_unlabeled_proposal():
    events = steps()
    frozen = capture.build_scan_input(events, events[2])
    signal = capture.CorrectionSignal(
        correction=True,
        target_step_id=str(events[1]["id"]),
        evidence_quote="the tests failed",
        change_kind="agent_error",
        explanation="The user corrects the test-success claim",
    )
    data = capture.feedback_data(uuid4(), frozen, signal)
    assert data["comment"] == "the tests failed"
    assert data["target_step_id"] == events[1]["id"]
    assert data["proposed_verdict"] is None
    assert "review_status" not in data and "assessment_id" not in data


def test_fabricated_quote_or_future_target_is_rejected():
    events = steps()
    frozen = capture.build_scan_input(events, events[2])
    for target, quote in [
        (str(events[3]["id"]), "the tests failed"),
        (str(events[1]["id"]), "Tests passed"),
        (str(events[1]["id"]), ""),
    ]:
        signal = capture.CorrectionSignal(
            correction=True,
            target_step_id=target,
            evidence_quote=quote,
            explanation="x",
        )
        with pytest.raises(ValueError):
            capture.feedback_data(uuid4(), frozen, signal)


def test_abstention_never_creates_feedback():
    events = steps()
    frozen = capture.build_scan_input(events, events[2])
    assert (
        capture.feedback_data(
            uuid4(),
            frozen,
            capture.CorrectionSignal(
                correction=False,
                explanation="This continues the task",
            ),
        )
        is None
    )


def test_large_captured_input_is_bounded_and_omissions_visible():
    events = steps()
    events[1]["content"] = "HEAD" + "x" * 200_000 + "TAIL"
    events[2]["content"] = "Wrong: " + "y" * 200_000
    frozen = capture.build_scan_input(events, events[2])
    assert len(frozen["prompt"]) < 27000
    assert any(o["reason"] == "source_clipped" for o in frozen["omission_details"])
    assert any(o["reason"] == "content_clipped" for o in frozen["omission_details"])
    assert "HEAD" in frozen["context_events"][-1]["content"]
    assert "TAIL" in frozen["context_events"][-1]["content"]
