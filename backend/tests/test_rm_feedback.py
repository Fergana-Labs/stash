"""Feedback must ground preferences without leaking later answers into the context."""

import json
from uuid import UUID, uuid4

import pytest

from backend.database import get_pool
from backend.services.rm import feedback
from backend.tasks import reward_models as tasks

from .test_rm_api import _annotate, _detail, _import, _register
from .test_rm_datasets import _create_model, _fake_worker, _trace, artifact_dir  # noqa: F401

pytestmark = pytest.mark.usefixtures("rm_title_generator")


def extraction(**changes):
    item = dict(
        step_index=1,
        source="user_feedback",
        revision="Please provide the order number first.",
        label="negative",
        confidence="high",
        evidence_id="step:2",
        evidence_quote="ask for the order number",
        reason="Verify the order before refunding",
    )
    item.update(changes)
    return feedback.Extraction(feedback=[feedback.Feedback(**item)])


def conversation():
    return [
        dict(idx=i, role=role, content=text, tool_name=None, tool_input=None)
        for i, (role, text) in enumerate(
            [
                ("user", "Refund my order"),
                ("assistant", "Refund issued"),
                ("user", "You need to ask for the order number first."),
            ]
        )
    ]


def evidence():
    return {"step:2": dict(kind="user", step_index=2, text=conversation()[2]["content"])}


def test_eligible_evidence_cannot_reverse_time_or_reassign_step_comments():
    steps = conversation() + [
        dict(idx=3, role="assistant", content="What is the order number?", tool_name=None),
        dict(idx=4, role="assistant", content="", tool_name="lookup_order"),
    ]
    sources = {
        **evidence(),
        "initial": dict(kind="user", step_index=0, text="Refund my order"),
        "comment:1": dict(kind="comment", step_index=1, text="Check first"),
        "comment:trace": dict(kind="comment", step_index=None, text="Check first"),
    }
    links = [
        {"step_index": step["idx"], "evidence_id": key}
        for step in steps
        for key in feedback.eligible_evidence(step, sources)
    ]
    assert links == [
        {"step_index": 1, "evidence_id": "step:2"},
        {"step_index": 1, "evidence_id": "comment:1"},
        {"step_index": 1, "evidence_id": "comment:trace"},
        {"step_index": 3, "evidence_id": "comment:trace"},
    ]


async def test_classifier_sees_only_eligible_evidence_and_code_assigns_the_target(monkeypatch):
    async def complete(**kwargs):
        payload = json.loads(kwargs["prompt"])
        assert payload["target_response"]["idx"] == 1
        assert set(payload["eligible_evidence"]) == {"step:2"}
        item = extraction().feedback[0].model_dump(exclude={"step_index"})
        return feedback.ResponseExtraction.model_validate(
            {"reason": item.pop("reason"), "feedback": item}
        )

    monkeypatch.setattr(feedback.llm, "complete_structured", complete)
    sources = {**evidence(), "initial": dict(kind="user", step_index=0, text="Refund my order")}
    result = await feedback.extract_preferences(conversation(), sources)
    assert result == extraction(evidence_quote=evidence()["step:2"]["text"])


async def test_no_reaction_still_receives_ai_assessment(monkeypatch):
    steps = conversation()[:2]

    async def complete(**kwargs):
        payload = json.loads(kwargs["prompt"])
        assert payload["eligible_evidence"] == {}
        parsed = feedback.ResponseExtraction(
            reason="Unsupported refund claim",
            feedback=feedback.Judgment(
                source="ai_judgment",
                evidence_id=None,
                evidence_quote=None,
                label="negative",
                confidence="high",
                revision="What is your order number?",
            ),
        )

        return kwargs["output_model"].model_validate(parsed.model_dump())

    async def review(*args):
        return feedback.ComparisonReview(preferred="revision", grounded=True, reason="Verify first")

    monkeypatch.setattr(feedback.llm, "complete_structured", complete)
    monkeypatch.setattr(feedback, "review_comparison", review)
    result = await feedback.extract_preferences(steps, {})
    [pair] = feedback.render_preferences(uuid4(), steps, {}, result)
    assert pair["evidence"]["source"] == "ai_judgment"
    assert pair["chosen"].endswith("What is your order number?")


async def test_classifier_cannot_cite_an_earlier_request(monkeypatch):
    async def complete(**kwargs):
        item = extraction(evidence_id="step:0").feedback[0].model_dump(exclude={"step_index"})
        return feedback.ResponseExtraction.model_validate(
            {"reason": item.pop("reason"), "feedback": item}
        )

    monkeypatch.setattr(feedback.llm, "complete_structured", complete)
    with pytest.raises(ValueError, match="ineligible for this response"):
        await feedback.extract_preferences(conversation(), evidence())


def test_preferences_share_context_and_exclude_later_correction():
    [pair] = feedback.render_preferences(uuid4(), conversation(), evidence(), extraction())
    assert (
        pair["chosen"]
        == "user: Refund my order\n\nassistant: Please provide the order number first."
    )
    assert pair["rejected"] == "user: Refund my order\n\nassistant: Refund issued"
    assert pair["evidence"]["evidence_quote"] == "ask for the order number"
    assert "You need to" not in pair["chosen"]


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_quote": "invented feedback"},
        {"evidence_id": "comment:invented"},
        {"step_index": 0},
        {"revision": "Refund issued"},
        {"revision": "   "},
        {"evidence_quote": " "},
        {"label": "unclear"},
        {"confidence": "low"},
    ],
)
def test_unsupported_preferences_fail_loud(changes):
    with pytest.raises(ValueError):
        feedback.render_preferences(uuid4(), conversation(), evidence(), extraction(**changes))


def test_earlier_request_is_not_evidence_of_a_later_answer_quality():
    sources = evidence()
    sources["step:2"]["step_index"] = 0
    with pytest.raises(ValueError, match="must follow"):
        feedback.render_preferences(uuid4(), conversation(), sources, extraction())


def test_step_comment_cannot_evaluate_another_step():
    sources = evidence()
    sources["step:2"].update(kind="comment", step_index=0)
    with pytest.raises(ValueError, match="different step"):
        feedback.render_preferences(uuid4(), conversation(), sources, extraction())


def test_positive_feedback_prefers_original_and_negative_prefers_revision():
    positive = extraction(label="positive", evidence_quote="ask for the order number")
    negative = extraction()
    [preferred] = feedback.render_preferences(uuid4(), conversation(), evidence(), positive)
    [corrected] = feedback.render_preferences(uuid4(), conversation(), evidence(), negative)
    assert preferred["chosen"] == corrected["rejected"]
    assert preferred["rejected"] == corrected["chosen"]


@pytest.mark.parametrize(
    "changes", [{"label": "unclear"}, {"confidence": "low"}, {"label": "negative"}]
)
def test_uncertainty_or_no_supported_alternative_contributes_no_pair(changes):
    result = extraction(revision=None, **changes)
    assert feedback.render_preferences(uuid4(), conversation(), evidence(), result) == []


def test_mixed_conversation_labels_do_not_spread_to_other_responses():
    steps = conversation() + [
        dict(idx=3, role="assistant", content="What is the order number?", tool_name=None),
        dict(idx=4, role="user", content="Yes, checking the order first is right.", tool_name=None),
    ]
    sources = {**evidence(), "step:4": dict(kind="user", step_index=4, text=steps[4]["content"])}
    result = feedback.Extraction(
        feedback=[
            extraction().feedback[0],
            extraction(
                step_index=3,
                label="positive",
                revision="Refund issued.",
                evidence_id="step:4",
                evidence_quote="checking the order first is right",
            ).feedback[0],
        ]
    )
    bad, good = feedback.render_preferences(uuid4(), steps, sources, result)
    assert bad["rejected"].endswith("assistant: Refund issued")
    assert good["chosen"].endswith("assistant: What is the order number?")
    assert "Yes, checking" not in good["chosen"]


@pytest.mark.usefixtures("artifact_dir")
async def test_comment_training_is_owned_selected_auditable_and_uses_no_ratings(
    client, monkeypatch
):
    auth = await _register(client)
    other = await _register(client)
    selected = await _import(
        client, auth, _trace("first", "Refund issued"), _trace("second", "Refund issued")
    )
    [outside] = await _import(client, auth, _trace("outside", "PRIVATE OUTSIDE"))
    [foreign] = await _import(client, other, _trace("foreign", "PRIVATE FOREIGN"))
    for trace_id in selected:
        steps = (await _detail(client, auth, trace_id))["steps"]
        await _annotate(
            client, auth, trace_id, step_id=steps[2]["id"], comment="ask for the order number"
        )
        wrong = await _annotate(client, auth, trace_id, comment="FLAGGED FEEDBACK")
        await client.patch(
            f"/api/v1/rm/annotations/{wrong['id']}", json={"label_error": True}, headers=auth
        )
    await _annotate(client, auth, outside, comment="PRIVATE OUTSIDE")
    await _annotate(client, other, foreign, comment="PRIVATE FOREIGN")
    seen = []

    async def extract(steps, sources):
        serialized = json.dumps([steps, sources], default=str)
        assert "PRIVATE" not in serialized and "FLAGGED" not in serialized
        seen.append(steps)
        comment_id = next(k for k in sources if k.startswith("comment:"))
        return extraction(step_index=2, evidence_id=comment_id)

    monkeypatch.setattr(feedback, "extract_preferences", extract)
    model_id = await _create_model(client, auth, monkeypatch, trace_ids=selected)

    def outputs(directory):
        (directory / "result.json").write_text('{"metrics": {}}')
        (directory / "scores.jsonl").write_text("")

    _fake_worker(monkeypatch, outputs)
    await tasks.train_reward_model_async(UUID(model_id))
    row = await get_pool().fetchrow(
        "SELECT status, num_pairs, training_pairs, artifact_key FROM rm_reward_models WHERE id=$1",
        UUID(model_id),
    )
    assert row["status"] == "succeeded" and row["num_pairs"] == 2
    assert {p["trace_id"] for p in row["training_pairs"]} == set(selected)
    assert all(
        p["evidence"]["evidence_quote"] == "ask for the order number" for p in row["training_pairs"]
    )
    assert row["artifact_key"].endswith(f"/{model_id}.tar.gz")
    assert len(seen) == 2
    detail = await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)
    assert len(detail.json()["feedback"]) == 2
    assert all(
        f["label"] == "negative" and f["included_in_training"] for f in detail.json()["feedback"]
    )
    assert (
        await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=other)
    ).status_code == 404


@pytest.mark.parametrize("label", ["negative", "unclear"])
async def test_unannotated_conversations_extract_feedback_and_fail_before_compute(
    client, monkeypatch, label
):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, {"steps": conversation()})

    async def extract(steps, sources):
        assert all(s["kind"] == "user" for s in sources.values())
        return extraction(label=label, revision=None)

    async def no_compute(*args):
        pytest.fail("Insufficient feedback must not launch training compute")

    monkeypatch.setattr(feedback, "extract_preferences", extract)
    from backend.services.rm import jobs

    monkeypatch.setattr(jobs, "run_worker", no_compute)
    model_id = await _create_model(client, auth, monkeypatch, trace_ids=[trace_id])
    with pytest.raises(ValueError, match="need at least 2"):
        await tasks.train_reward_model_async(UUID(model_id))
    detail = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert detail["status"] == "failed"
    assert detail["feedback"][0]["label"] == label
    assert not detail["feedback"][0]["included_in_training"]
    assert (await _detail(client, auth, trace_id))["annotations"] == []


@pytest.mark.usefixtures("artifact_dir")
async def test_user_feedback_alone_builds_a_training_dataset(client, monkeypatch):
    auth = await _register(client)
    selected = await _import(
        client,
        auth,
        {"id": "first", "steps": conversation()},
        {"id": "second", "steps": conversation()},
    )

    async def extract(steps, sources):
        assert all(source["kind"] == "user" for source in sources.values())
        return extraction()

    monkeypatch.setattr(feedback, "extract_preferences", extract)
    model_id = await _create_model(client, auth, monkeypatch, trace_ids=selected)

    def outputs(directory):
        pairs = [json.loads(line) for line in (directory / "pairs.jsonl").read_text().splitlines()]
        assert len(pairs) == 2
        assert all(pair["evidence"]["label"] == "negative" for pair in pairs)
        (directory / "result.json").write_text('{"metrics": {}}')
        (directory / "scores.jsonl").write_text("")

    _fake_worker(monkeypatch, outputs)
    await tasks.train_reward_model_async(UUID(model_id))
    detail = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert detail["status"] == "succeeded"
    assert all(f["included_in_training"] for f in detail["feedback"])
    for trace_id in selected:
        assert (await _detail(client, auth, trace_id))["annotations"] == []


@pytest.mark.parametrize(
    "preferred,grounded", [("tie", True), ("original", True), ("revision", False)]
)
async def test_ai_comparison_must_pass_independent_review(monkeypatch, preferred, grounded):
    async def complete(**kwargs):
        return feedback.ResponseExtraction(
            reason="Check the order",
            feedback=feedback.Judgment(
                source="ai_judgment",
                evidence_id=None,
                evidence_quote=None,
                label="negative",
                confidence="high",
                revision="What is the order number?",
            ),
        )

    async def review(*args):
        return feedback.ComparisonReview(
            preferred=preferred, grounded=grounded, reason="Review decision"
        )

    monkeypatch.setattr(feedback.llm, "complete_structured", complete)
    monkeypatch.setattr(feedback, "review_comparison", review)
    result = await feedback.extract_preferences(conversation()[:2], {})
    assert result.feedback[0].revision is None
    assert "Review decision" in result.feedback[0].reason
    assert feedback.render_preferences(uuid4(), conversation()[:2], {}, result) == []


async def test_comparison_review_cannot_see_future_facts(monkeypatch):
    steps = conversation() + [dict(idx=3, role="user", content="FUTURE SECRET")]

    async def complete(**kwargs):
        assert "FUTURE SECRET" not in kwargs["prompt"]
        assert "You need to" not in kwargs["prompt"]
        return feedback.ComparisonReview(preferred="revision", grounded=True, reason="Verify first")

    monkeypatch.setattr(feedback.llm, "complete_structured", complete)
    await feedback.review_comparison(steps, steps[1], extraction().feedback[0])


@pytest.mark.usefixtures("artifact_dir")
async def test_no_annotations_or_user_reactions_can_complete_training(client, monkeypatch):
    auth = await _register(client)
    selected = await _import(
        client, auth, _trace("first", "Refund issued"), _trace("second", "Refund issued")
    )

    async def extract(steps, sources):
        assert not any(source["step_index"] > 2 for source in sources.values())
        return extraction(
            step_index=2,
            source="ai_judgment",
            evidence_id="response:2",
            evidence_quote="Refund issued",
        )

    monkeypatch.setattr(feedback, "extract_preferences", extract)
    model_id = await _create_model(client, auth, monkeypatch, trace_ids=selected)

    def outputs(directory):
        pairs = [json.loads(line) for line in (directory / "pairs.jsonl").read_text().splitlines()]
        assert len(pairs) == 2
        assert all(pair["evidence"]["source"] == "ai_judgment" for pair in pairs)
        (directory / "result.json").write_text('{"metrics": {}}')
        (directory / "scores.jsonl").write_text("")

    _fake_worker(monkeypatch, outputs)
    await tasks.train_reward_model_async(UUID(model_id))
    detail = (await client.get(f"/api/v1/rm/reward-models/{model_id}", headers=auth)).json()
    assert detail["status"] == "succeeded"
    assert all(
        f["source"] == "ai_judgment" and f["included_in_training"] for f in detail["feedback"]
    )
    for trace_id in selected:
        assert (await _detail(client, auth, trace_id))["annotations"] == []


async def test_human_rating_prevents_conflicting_ai_supervision(client, monkeypatch):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, _trace("rated", "Refund issued"))
    await _annotate(client, auth, trace_id, rating=1)

    async def extract(steps, sources):
        return extraction(
            step_index=2,
            source="ai_judgment",
            evidence_id="response:2",
            evidence_quote="Refund issued",
        )

    monkeypatch.setattr(feedback, "extract_preferences", extract)
    from backend.services.rm.datasets import all_trace_ids

    owner = UUID((await client.get("/api/v1/users/me", headers=auth)).json()["id"])
    pairs, findings = await feedback.build_feedback_pairs(owner, await all_trace_ids(owner), 10)
    assert pairs == []
    assert "human rating takes precedence" in findings[0]["reason"]


@pytest.mark.parametrize("evidence_id", ["step:0", "response:1", None])
def test_schema_prevents_ineligible_human_citations(evidence_id):
    from pydantic import ValidationError

    schema = feedback.extraction_schema(evidence())
    finding = (
        extraction(evidence_id="step:2").feedback[0].model_dump(exclude={"reason", "step_index"})
    )
    finding["evidence_id"] = evidence_id
    finding["evidence_quote"] = None
    with pytest.raises(ValidationError):
        schema.model_validate({"reason": "Assessment", "feedback": finding})


def test_schema_without_reactions_only_allows_ai_judgments():
    from pydantic import ValidationError

    schema = feedback.extraction_schema({})
    finding = extraction().feedback[0].model_dump(exclude={"reason", "step_index"})
    with pytest.raises(ValidationError):
        schema.model_validate({"reason": "Assessment", "feedback": finding})
    finding.update(source="ai_judgment", evidence_id=None, evidence_quote=None)
    assert (
        schema.model_validate({"reason": "Assessment", "feedback": finding}).feedback.source
        == "ai_judgment"
    )


async def test_duplicate_alternative_is_reported_without_aborting_other_learning(monkeypatch):
    async def complete(**kwargs):
        finding = (
            extraction(revision="Refund issued")
            .feedback[0]
            .model_dump(exclude={"reason", "step_index"})
        )
        finding["evidence_quote"] = None
        return kwargs["output_model"].model_validate({"reason": "Evaluation", "feedback": finding})

    monkeypatch.setattr(feedback.llm, "complete_structured", complete)
    result = await feedback.extract_preferences(conversation(), evidence())
    assert result.feedback[0].revision is None
    assert "excluded from training" in result.feedback[0].reason
    assert feedback.render_preferences(uuid4(), conversation(), evidence(), result) == []
