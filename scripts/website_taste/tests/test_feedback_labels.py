"""Observed human feedback is usable without another labeling pass."""

import copy

import pytest

from scripts.website_taste import activation_head, preferences, protocol


def proposal(**changes):
    source = {
        "id": "output",
        "session_id": "session",
        "line": 9,
        "image_index": 1,
        "image_count": 1,
        "render_inspected": True,
        "sha256": "pixels",
        "feedback": "This screen looks terrible. Make the rows thinner.",
    }
    label = {
        "id": "output",
        "label": "disliked",
        "scope": "overall",
        "quote": "This screen looks terrible",
        "explicit": True,
        "image_role": "output",
        "target": "single",
        "preference": "Avoid the current visual treatment",
        "reason": "Direct visual criticism of the single attached screenshot",
    }
    label.update(changes)
    row = preferences.validate_proposals([source], {"proposals": [label]})[0]
    return {**row, "label_source": "explicit_feedback_auto", "human_reviewed": False}


def test_explicit_feedback_supplies_label_without_manual_review():
    row = proposal()
    assert preferences.source_label(row, pixel_sha="pixels")
    assert not row["needs_review"] and not row["human_reviewed"]
    assert not preferences.source_label(row, pixel_sha="other-output")
    assert preferences.usable_label(proposal(scope="aspect", quote="Make the rows thinner"))


@pytest.mark.parametrize(
    "changes",
    [
        {"explicit": False},
        {"target": "ambiguous"},
        {"quote": "It is beautiful"},
        {"scope": "functional"},
        {"image_role": "comparison"},
        {"image_role": "reference"},
        {"scope": "unrelated"},
        {"label": "unknown"},
        {"label": "liked", "scope": "aspect"},
    ],
)
def test_uncertainty_functionality_or_unsupported_approval_abstains(changes):
    row = proposal(**changes)
    assert not preferences.usable_label(row)
    assert row["needs_review"]


def test_multi_image_feedback_requires_explicit_target_not_confidence():
    row = proposal()
    row["feedback_evidence"].update(image_count=2, image_index=2)
    assert not preferences.source_label(row)
    row["feedback_evidence"]["target"] = "explicit"
    assert preferences.source_label(row)
    row["label_source"] = "teacher_inferred"
    assert not preferences.usable_label(row)


def test_deictic_pointer_alone_is_not_an_explicit_visual_preference():
    row = proposal()
    for quote in ("and these", "and thesae", "this"):
        row["quote"] = quote
        row["feedback_evidence"].update(quote=quote, feedback=quote)
        assert not preferences.source_label(row)


def test_source_policy_and_release_keep_grounding_freshness_and_accuracy_separate():
    rows = []
    for part in ("train", "dev", "test"):
        for label in ("liked", "disliked"):
            row = copy.deepcopy(proposal(label=label))
            row.update(id=f"{part}:{label}", partition=part, group=part, sha256=f"{part}:{label}")
            row["feedback_evidence"]["sha256"] = row["sha256"]
            rows.append(row)
    protocol.validate_dataset(rows, protocol.tasks(), label_policy="source_grounded")
    dataset = {
        "heldout_status": "untouched_source_feedback_test",
        "examples": [
            {"supervision": r, "input": {"render": {"sha256": r["sha256"]}}} for r in rows
        ],
    }
    good = {
        "n": 10,
        "accuracy": 1,
        "per_class": {label: {"n": 5, "recall": 1} for label in ("liked", "disliked")},
    }
    assert activation_head.release_gate(dataset, {"dev": good, "test": good})["passed"]
    assert not activation_head.release_gate(
        dataset, {"dev": {**good, "accuracy": 0.5}, "test": good}
    )["passed"]
    dataset["heldout_status"] = "previously_inspected_test"
    assert not activation_head.release_gate(dataset, {"dev": good, "test": good})["passed"]
    rows[0]["label_source"] = "teacher_inferred"
    with pytest.raises(ValueError, match="clear human feedback"):
        protocol.validate_dataset(rows, protocol.tasks(), label_policy="source_grounded")
