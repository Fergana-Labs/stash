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
        "<turn_aborted>The user interrupted the turn. Do not infer cancellation.</turn_aborted>",
        "[Request interrupted by user for tool use]",
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


def test_new_requirement_can_be_anchored_only_to_the_source_user_message():
    events = steps()
    events[2]["content"] = "Use precise language going forward."
    frozen = capture.build_scan_input(events, events[2])
    signal = capture.CorrectionSignal(
        correction=True,
        target_step_id=None,
        evidence_quote="Use precise language going forward.",
        change_kind="requirement_change",
        explanation="The user gives a new instruction without identifying a prior mistake.",
    )
    data = capture.feedback_data(uuid4(), frozen, signal)
    assert data["target_step_id"] is None
    assert data["change_kind"] == "requirement_change"
    assert data["proposed_verdict"] is None
    assert data["comment"] == events[2]["content"]
    assert "review_status" not in data


@pytest.mark.parametrize("kind", ["agent_error", "unclear"])
def test_missing_target_is_not_allowed_for_a_claim_about_earlier_behavior(kind):
    events = steps()
    frozen = capture.build_scan_input(events, events[2])
    signal = capture.CorrectionSignal(
        correction=True,
        target_step_id=None,
        evidence_quote="the tests failed",
        change_kind=kind,
        explanation="A claim about previous behavior needs a captured target.",
    )
    with pytest.raises(ValueError, match="Only a new requirement"):
        capture.feedback_data(uuid4(), frozen, signal)


def test_requirement_with_a_target_still_cannot_point_to_future_or_fabricated_events():
    events = steps()
    frozen = capture.build_scan_input(events, events[2])
    for target_id in (str(events[3]["id"]), str(uuid4())):
        signal = capture.CorrectionSignal(
            correction=True,
            target_step_id=target_id,
            evidence_quote="the tests failed",
            change_kind="requirement_change",
            explanation="This still needs a valid preceding target if one is supplied.",
        )
        with pytest.raises(ValueError, match="supplied preceding assistant"):
            capture.feedback_data(uuid4(), frozen, signal)


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


def event(index, role, content, **extra):
    return {"id": uuid4(), "idx": index, "role": role, "content": content, **extra}


def test_correction_keeps_ten_intervening_events_and_the_latest_user_question():
    events = [
        event(0, "user", "Check why the component test fails."),
        event(1, "assistant", "I will inspect the test output.", metadata={"phase": "commentary"}),
    ]
    for index in range(2, 10):
        events.append(event(index, "tool", f"Diagnostic result {index}", tool_name="read_file"))
    events.extend(
        [
            event(10, "user", "Which assertion actually failed?"),
            event(11, "assistant", "The count assertion failed.", metadata={"phase": "final"}),
            event(12, "user", "That's wrong: the parser assertion failed."),
            event(13, "assistant", "FUTURE_CHANGE_TO_THE_TEST"),
        ]
    )
    context = capture.build_correction_context(events, events[12], events[1]["id"])
    captured = {e["index"]: e for e in context["context_events"]}
    assert set(captured) == set(range(12))
    assert captured[10]["content"] == "Which assertion actually failed?"
    assert captured[11]["previous_event_id"] == str(events[10]["id"])
    assert captured[11]["next_event_id"] == str(events[12]["id"])
    assert context["source_event"]["previous_event_id"] == str(events[11]["id"])
    assert context["source_event"]["next_event_id"] is None
    assert context["target_step_id"] == str(events[1]["id"])
    assert "FUTURE_CHANGE" not in json.dumps(context)
    assert context == capture.build_correction_context(events[:13], events[12], events[1]["id"])


def test_commentary_preserves_later_tools_and_interruption_without_inventing_cancellation():
    events = [
        event(0, "user", "Run the parser tests."),
        event(1, "assistant", "I will run the tests.", metadata={"phase": "commentary"}),
        event(2, "assistant", "", tool_name="exec", tool_input={"command": "pytest parser"}),
        event(3, "tool", "8 tests passed", tool_name="exec"),
        event(4, "user", "<turn_aborted>User interrupted this turn.</turn_aborted>"),
        event(5, "user", "What did the test output say?"),
        event(6, "assistant", "Two tests failed.", metadata={"phase": "final", "channel": "final"}),
        event(7, "user", "That's wrong: all eight tests passed."),
    ]
    snapshot = capture.build_scan_input(events, events[7])
    captured = {e["index"]: e for e in snapshot["context_events"]}
    assert captured[1]["event_kind"] == "assistant_commentary"
    assert captured[1]["metadata"]["phase"] == "commentary"
    assert captured[2]["event_kind"] == "tool_call"
    assert "pytest parser" in captured[2]["content"]
    assert captured[3]["event_kind"] == "tool_result"
    assert captured[3]["content"] == "8 tests passed"
    assert captured[4]["event_kind"] == "user_interruption_marker"
    assert captured[6]["event_kind"] == "assistant_final_response"
    assert captured[6]["metadata"]["channel"] == "final"
    assert set(snapshot["target_candidates"]) == {str(events[i]["id"]) for i in (1, 2, 6)}
    assert "not cancellation" in snapshot["system"]
    assert "not proof of completion" in snapshot["system"]


def test_large_assistant_messages_cannot_starve_recent_user_and_tool_evidence():
    events = [event(0, "user", "Inspect the test results.")]
    for index in range(1, 17):
        events.append(event(index, "assistant", f"old response {index} " + "x" * 20000))
    events.extend(
        [
            event(17, "user", "Did you actually run the focused test?"),
            event(18, "assistant", "I will run it now.", metadata={"phase": "commentary"}),
            event(19, "assistant", "", tool_name="exec", tool_input={"command": "pytest focused"}),
            event(20, "tool", "Focused test failed: expected zero, got None."),
            event(21, "assistant", "The test passed."),
            event(22, "user", "That's wrong: the test failed."),
        ]
    )
    snapshot = capture.build_scan_input(events, events[-1])
    captured = {e["index"]: e for e in snapshot["context_events"]}
    assert set(range(17, 22)) <= captured.keys()
    assert captured[17]["content"] == events[17]["content"]
    assert captured[20]["content"] == events[20]["content"]
    assert captured[21]["content"] == events[21]["content"]
    serialized_events = json.dumps(
        {"source_event": snapshot["source_event"], "context_events": snapshot["context_events"]},
        ensure_ascii=False,
        sort_keys=True,
    )
    assert len(serialized_events) <= capture.CONTEXT_CHARS
    assert snapshot["omission_details"]
    assert snapshot["context_policy_version"] == capture.CORRECTION_CONTEXT_POLICY_VERSION


def test_explicit_older_target_is_reserved_but_is_not_assumed_correct_attribution():
    events = [
        event(0, "user", "Check all three files."),
        event(1, "assistant", "Checked two files."),
    ]
    events.extend(event(i, "tool", f"Result {i}") for i in range(2, 60))
    events.append(event(60, "user", "You missed the third file."))
    context = capture.build_correction_context(events, events[-1], events[1]["id"])
    assert str(events[1]["id"]) in context["target_candidates"]
    assert str(events[1]["id"]) in {e["id"] for e in context["context_events"]}
    assert any(o["reason"] == "context_budget" for o in context["omission_details"])
    assert "attribution hints, not proof" in capture.SYSTEM


def test_thinking_and_harness_metadata_survive_but_are_not_correction_targets():
    events = [
        event(0, "user", "Fix the parser."),
        event(1, "user", "# AGENTS.md instructions\nPreserve zero.", metadata={"isMeta": True}),
        event(2, "assistant", "Considering options", metadata={"thinking": True}),
        event(3, "assistant", "Fixed it.", metadata={"phase": "final", "type": "message"}),
        event(4, "user", "That's wrong: zero is still broken."),
    ]
    context = capture.build_correction_context(events, events[-1])
    assert context["context_events"][1]["event_kind"] == "harness_message"
    assert context["context_events"][1]["metadata"]["isMeta"] is True
    assert context["context_events"][2]["metadata"]["thinking"] is True
    assert context["target_candidates"] == [str(events[3]["id"])]
    for target in (events[0], events[2], events[4]):
        with pytest.raises(ValueError, match="preceding non-thinking assistant"):
            capture.build_correction_context(events, events[-1], target["id"])


def test_serialized_budget_also_counts_escaped_content_and_source_text():
    events = [
        event(0, "user", "Inspect the output."),
        event(1, "assistant", "HEAD" + "\x01" * 20000 + "TAIL"),
        event(2, "user", "Wrong: " + "\x02" * 20000),
    ]
    context = capture.build_correction_context(events, events[-1], events[1]["id"])
    payload = {k: context[k] for k in ("source_event", "context_events")}
    assert len(json.dumps(payload, ensure_ascii=False, sort_keys=True)) <= capture.CONTEXT_CHARS
    assert len(context["source_event"]["content"]) <= 6000
    assert str(events[1]["id"]) in context["target_candidates"]


def test_shared_context_helper_does_not_require_correction_keyword_eligibility():
    events = [
        event(0, "user", "Please inspect the parser."),
        event(1, "assistant", "The parser returns None for zero."),
        event(2, "user", "Zero is a valid value."),
    ]
    assert (
        capture.build_correction_context(events, events[-1])["source_event"]["content"]
        == events[-1]["content"]
    )
    with pytest.raises(ValueError, match="eligible"):
        capture.build_scan_input(events, events[-1])
