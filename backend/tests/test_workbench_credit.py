"""Continuous credit derives from saved distributions, independently of confidence."""

import pytest

from backend.services.rm import workbench_evaluation as policy


def distribution(**weights):
    return {label: weights.get(label, 0.0) for label in policy.CREDIT_VALUES}


@pytest.mark.parametrize(
    "label,value",
    [
        ("strongly_negative", -1),
        ("negative", -0.5),
        ("neutral", 0),
        ("positive", 0.5),
        ("strongly_positive", 1),
    ],
)
def test_certain_judgments_preserve_scale_anchors(label, value):
    assert (
        policy.expected_credit({"verdict": label, "probabilities": distribution(**{label: 1})})
        == value
    )


def test_expected_credit_keeps_distribution_and_separates_uncertainty():
    probabilities = distribution(negative=0.1, neutral=0.2, positive=0.6, strongly_positive=0.1)
    answer = {"verdict": "positive", "confidence": 0.99, "probabilities": probabilities}
    assert policy.expected_credit(answer) == pytest.approx(0.35)
    answer["confidence"] = 0.01
    assert policy.expected_credit(answer) == pytest.approx(0.35)
    answer["probabilities"] = {label: p * 0.8 for label, p in probabilities.items()}
    answer["probabilities"]["insufficient_evidence"] = 0.2
    # Unknown credit is not fabricated as neutral credit.
    assert policy.expected_credit(answer) == pytest.approx(0.35)
    answer["verdict"] = "insufficient_evidence"
    assert policy.expected_credit(answer) is None


@pytest.mark.parametrize(
    "probabilities",
    [
        None,
        {},
        {"positive": 1},
        distribution(positive=float("nan")),
        distribution(positive=True),
        distribution(positive=0.2),
        distribution(positive=-0.1, neutral=1.1),
        distribution(insufficient_evidence=1),
    ],
)
def test_missing_or_invalid_saved_probabilities_do_not_invent_scores(probabilities):
    assert policy.expected_credit({"verdict": "positive", "probabilities": probabilities}) is None
