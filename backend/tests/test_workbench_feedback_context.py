"""Correction drafting retains the dialogue through the actual human correction.

Sanitized regressions for a correction misattributed to an old summary and a
repeated request misread as criticism of an unfinished commentary statement.
Models are mocked; claims, targets, drafts, and provenance use real persistence.
"""

import json
from uuid import UUID, uuid4

import pytest

from backend.services.rm import workbench as service
from backend.tasks import workbench as tasks

from .conftest import unique_name


@pytest.fixture(autouse=True)
def isolated_model_boundary(monkeypatch):
    monkeypatch.setattr(tasks.prepare_feedback, "delay", lambda *args, **kwargs: None)

    async def unexpected(**kwargs):
        raise AssertionError("A test must provide its model response explicitly")

    monkeypatch.setattr(service.llm, "complete_structured", unexpected)


async def fixture_trace(client, pool, events):
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert response.status_code == 201, response.text
    owner = UUID(response.json()["id"])
    trace_id = await pool.fetchval(
        """INSERT INTO rm_traces(owner_user_id,title,source_format,metadata)
        VALUES($1,'Sanitized correction context','codex',$2) RETURNING id""",
        owner,
        {"cwd": "/test/repository"},
    )
    steps = []
    for index, (role, content) in enumerate(events):
        step = await pool.fetchrow(
            """INSERT INTO rm_trace_steps(trace_id,idx,role,content)
            VALUES($1,$2,$3,$4) RETURNING *""",
            trace_id,
            index,
            role,
            content,
        )
        steps.append(dict(step))
    return owner, trace_id, steps


async def extracted_feedback(owner, trace_id, steps, *, target=1, source=-2, comment=None):
    source_step = steps[source]
    return await service.create_feedback(
        owner,
        {
            "trace_id": trace_id,
            "target_step_id": steps[target]["id"],
            "comment": comment or source_step["content"],
            "change_kind": "agent_error",
            "proposed_verdict": "violates",
        },
        source="trace_extraction",
        source_event_id=source_step["id"],
    )


def model_draft(**overrides):
    return service.CorrectionDraft(
        **{
            "title": "Use precise research explanations",
            "change_kind": "requirement_change",
            "proposed_verdict": None,
            "explanation": "The user asks for precise inputs, outputs, and baselines.",
            "instruction_text": "Name model inputs, outputs, and the evaluation baseline.",
            **overrides,
        }
    )


async def test_extracted_correction_can_retarget_using_intervening_dialogue(
    client, pool, monkeypatch
):
    events = [
        ("user", "Write an HTML research proposal."),
        ("assistant", "Written: the proposal includes training and evaluation."),
        ("user", "Fewer labels compared with what baseline?"),
        ("assistant", "The comparison is against the same base model without prior training."),
        ("user", "Does judging a completed attempt mean assigning credit to each action?"),
        ("assistant", "A completed-attempt judgment and action-level credit are distinct."),
        (
            "user",
            "Please use precise language going forward. Name inputs, outputs, and baselines.",
        ),
        ("assistant", "FUTURE_RESPONSE_MUST_NOT_ENTER_DRAFT_CONTEXT"),
    ]
    owner, trace_id, steps = await fixture_trace(client, pool, events)
    feedback = await extracted_feedback(
        owner, trace_id, steps, comment="Please use precise language going forward."
    )
    seen = {}

    async def interpret(**kwargs):
        seen.update(kwargs)
        payload = json.loads(kwargs["prompt"])
        context = payload["input"]
        assert context["source_event"]["id"] == str(steps[6]["id"])
        assert context["source_event"]["content"] == events[6][1]
        assert context["target_step_id"] == str(steps[1]["id"])
        assert context["evidence_cutoff"]["step_index"] == 6
        assert context["context_policy_version"]
        by_id = {event["id"]: event for event in context["context_events"]}
        for step in steps[2:6]:
            assert by_id[str(step["id"])]["content"] == step["content"]
        assert str(steps[5]["id"]) in context["target_candidates"]
        assert "FUTURE_RESPONSE_MUST_NOT_ENTER_DRAFT_CONTEXT" not in kwargs["prompt"]
        return model_draft(target_step_id=str(steps[5]["id"]))

    monkeypatch.setattr(service.llm, "complete_structured", interpret)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "completed", result.get("error")
    assert result["review_status"] == "pending"
    assert result["target_step_id"] == steps[5]["id"]
    assert result["change_kind"] == "requirement_change"
    assert result["proposed_verdict"] is None
    interpretation = result["interpretation"]
    assert interpretation["draft_context_version"] == 2
    assert interpretation["drafting_input"] == json.loads(seen["prompt"])
    assert interpretation["drafting_system"] == seen["system"]
    assert len(result["changes"]) == 1
    assert result["changes"][0]["status"] == "draft"


async def test_repeated_request_keeps_intervening_tool_result_and_can_abstain(
    client, pool, monkeypatch
):
    events = [
        ("user", "Remove the oversized status panel."),
        ("assistant", "I will update the status panel."),
        ("user", "<turn_aborted>The previous turn was interrupted.</turn_aborted>"),
        ("user", "Add a demo trace without customer data. See the attached screenshot."),
        ("assistant", "I will add the demo trace and finish the panel change."),
        ("tool", "Panel change saved; demo trace preparation has started."),
        (
            "user",
            "Please add a demo trace, not a customer trace. The screenshot shows the format.",
        ),
        ("assistant", "FUTURE_DEMO_TRACE_RESULT"),
    ]
    owner, trace_id, steps = await fixture_trace(client, pool, events)
    feedback = await extracted_feedback(owner, trace_id, steps, target=4)

    async def interpret(**kwargs):
        payload = json.loads(kwargs["prompt"])
        context = payload["input"]
        assert context["source_event"]["content"] == events[6][1]
        assert any(
            event["id"] == str(steps[5]["id"]) and event["content"] == events[5][1]
            for event in context["context_events"]
        )
        assert "FUTURE_DEMO_TRACE_RESULT" not in kwargs["prompt"]
        return model_draft(
            change_kind="unclear",
            proposed_verdict=None,
            instruction_text=None,
            target_step_id=None,
            explanation="The user repeats a request; no specific agent failure is established.",
        )

    monkeypatch.setattr(service.llm, "complete_structured", interpret)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "completed", result.get("error")
    assert result["change_kind"] == "unclear"
    assert result["proposed_verdict"] is None
    assert not result["changes"]


@pytest.mark.parametrize("invalid_target", ["future", "user", "foreign"])
async def test_extracted_feedback_rejects_unsupported_model_attribution(
    client, pool, monkeypatch, invalid_target
):
    events = [
        ("user", "Check the recorded test result."),
        ("assistant", "The tests passed."),
        ("user", "That is wrong: the recorded check failed."),
        ("assistant", "I will correct the report."),
    ]
    owner, trace_id, steps = await fixture_trace(client, pool, events)
    feedback = await extracted_feedback(owner, trace_id, steps)
    target = {
        "future": str(steps[3]["id"]),
        "user": str(steps[0]["id"]),
        "foreign": str(uuid4()),
    }[invalid_target]

    async def interpret(**kwargs):
        return model_draft(target_step_id=target)

    monkeypatch.setattr(service.llm, "complete_structured", interpret)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "failed"
    assert result["error"]
    assert result["review_status"] == "pending"
    assert not result["changes"]


async def test_missing_model_target_abstains_instead_of_reusing_old_attribution(
    client, pool, monkeypatch
):
    owner, trace_id, steps = await fixture_trace(
        client,
        pool,
        [("user", "Check tests."), ("assistant", "Tests passed."), ("user", "That is wrong.")],
    )
    feedback = await extracted_feedback(owner, trace_id, steps, source=2)

    async def interpret(**kwargs):
        return model_draft(change_kind="agent_error", target_step_id=None)

    monkeypatch.setattr(service.llm, "complete_structured", interpret)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "completed", result.get("error")
    assert result["change_kind"] == "unclear"
    assert result["proposed_verdict"] is None
    assert not result["changes"]


async def test_new_requirement_needs_no_invented_prior_action_or_violation(
    client, pool, monkeypatch
):
    owner, trace_id, steps = await fixture_trace(
        client,
        pool,
        [
            ("user", "Explain the research proposal."),
            ("assistant", "The proposal evaluates completed attempts."),
            ("user", "Going forward, name each model's input, output, and evaluation baseline."),
        ],
    )
    feedback = await extracted_feedback(owner, trace_id, steps, source=2)

    async def interpret(**kwargs):
        return model_draft(
            target_step_id=None,
            change_kind="requirement_change",
            proposed_verdict="violates",
            grader_prompt="Treat every earlier explanation as wrong.",
        )

    monkeypatch.setattr(service.llm, "complete_structured", interpret)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "completed", result.get("error")
    assert result["review_status"] == "pending"
    assert result["source_event_id"] == steps[2]["id"]
    assert result["target_step_id"] is None
    assert result["change_kind"] == "requirement_change"
    assert result["proposed_verdict"] is None
    assert result["interpretation"]["target_step_id"] is None
    assert result["interpretation"]["proposed_verdict"] is None
    assert result["interpretation"]["grader_prompt"] is None
    assert len(result["changes"]) == 1
    change = result["changes"][0]
    assert change["kind"] == "instruction"
    assert change["status"] == "draft"
    assert change["feedback_id"] == feedback["id"]
    assert change["content"]["text"] == "Name model inputs, outputs, and the evaluation baseline."


async def test_failed_provider_preserves_exact_request_before_inference(client, pool, monkeypatch):
    owner, trace_id, steps = await fixture_trace(
        client,
        pool,
        [("user", "Check tests."), ("assistant", "Tests passed."), ("user", "That is wrong.")],
    )
    feedback = await extracted_feedback(owner, trace_id, steps, source=2)
    seen = {}

    async def unavailable(**kwargs):
        seen.update(kwargs)
        saved = await pool.fetchrow(
            "SELECT status,interpretation FROM rm_wb_feedback WHERE id=$1", feedback["id"]
        )
        assert saved["status"] == "running"
        assert saved["interpretation"]["draft_context_version"] == 2
        assert saved["interpretation"]["drafting_input"] == json.loads(kwargs["prompt"])
        assert saved["interpretation"]["drafting_system"] == kwargs["system"]
        raise RuntimeError("Synthetic drafting provider outage")

    monkeypatch.setattr(service.llm, "complete_structured", unavailable)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "failed"
    assert result["error"] == "Synthetic drafting provider outage"
    assert result["interpretation"]["draft_context_version"] == 2
    assert result["interpretation"]["drafting_input"] == json.loads(seen["prompt"])
    assert result["interpretation"]["drafting_system"] == seen["system"]
    assert not result["changes"]


@pytest.mark.parametrize("source_id", [None, "deleted"])
async def test_missing_captured_correction_fails_before_model_call(
    client, pool, monkeypatch, source_id
):
    owner, trace_id, steps = await fixture_trace(
        client,
        pool,
        [("user", "Check tests."), ("assistant", "Tests passed."), ("user", "That is wrong.")],
    )
    feedback = await extracted_feedback(owner, trace_id, steps, source=2)
    await pool.execute(
        "UPDATE rm_wb_feedback SET source_event_id=$2 WHERE id=$1",
        feedback["id"],
        uuid4() if source_id else None,
    )
    calls = []

    async def interpret(**kwargs):
        calls.append(kwargs)
        return model_draft(target_step_id=str(steps[1]["id"]))

    monkeypatch.setattr(service.llm, "complete_structured", interpret)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "failed"
    assert result["error"]
    assert not calls
    assert not result["changes"]


async def test_manual_feedback_keeps_human_selected_target_kind_and_verdict(
    client, pool, monkeypatch
):
    owner, trace_id, steps = await fixture_trace(
        client,
        pool,
        [
            ("user", "Check the parser."),
            ("assistant", "The tests passed."),
            ("assistant", "A different follow-up action."),
        ],
    )
    feedback = await service.create_feedback(
        owner,
        {
            "trace_id": trace_id,
            "target_step_id": steps[1]["id"],
            "comment": "The report is unsupported by the recorded check.",
            "change_kind": "agent_error",
            "proposed_verdict": "violates",
        },
    )

    async def interpret(**kwargs):
        return model_draft(target_step_id=str(steps[2]["id"]))

    monkeypatch.setattr(service.llm, "complete_structured", interpret)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "completed", result.get("error")
    assert result["target_step_id"] == steps[1]["id"]
    assert result["change_kind"] == "agent_error"
    assert result["proposed_verdict"] == "violates"
    assert result["interpretation"]["proposed_verdict"] == "violates"


async def test_source_changed_during_drafting_cannot_publish_candidate(client, pool, monkeypatch):
    owner, trace_id, steps = await fixture_trace(
        client,
        pool,
        [("user", "Check tests."), ("assistant", "Tests passed."), ("user", "That is wrong.")],
    )
    feedback = await extracted_feedback(owner, trace_id, steps, source=2)

    async def interpret(**kwargs):
        await pool.execute(
            "UPDATE rm_trace_steps SET content='A replacement correction.' WHERE id=$1",
            steps[2]["id"],
        )
        return model_draft(target_step_id=str(steps[1]["id"]))

    monkeypatch.setattr(service.llm, "complete_structured", interpret)
    await service.prepare_feedback(feedback["id"])
    result = await service.feedback_detail(owner, feedback["id"])
    assert result["status"] == "failed"
    assert result["error"]
    assert not result["changes"]
