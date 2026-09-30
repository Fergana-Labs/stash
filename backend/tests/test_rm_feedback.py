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
        revision="Please provide the order number first.",
        revision_preferred=True,
        evidence_id="step:2",
        evidence_quote="ask for the order number",
        reason="Verify the order before refunding",
    )
    item.update(changes)
    return feedback.Extraction(preferences=[feedback.Preference(**item)])


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
