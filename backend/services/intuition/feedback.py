"""Feedback on served predictions: corrections, delayed outcomes, downstream verdicts.

A prediction collects feedback over time from three sources. `human` is a person
correcting the call; `outcome` is what actually happened later (the customer
escalated, the deploy rolled back); `downstream` is another system's verdict.
Rows are append-only, so the history of every signal is kept.

The label a prediction is measured against is its "truth": the newest human
label, else the newest outcome label, else the newest downstream label.
Feedback only becomes training data when the caller asks (`learn`), because
outcome and downstream signals can be noisy.
"""

from __future__ import annotations

import math
from uuid import UUID

from ...database import get_pool
from . import service
from .spec import valid_example_labels

SOURCES = ("human", "outcome", "downstream")
TRUTH_ORDER_SQL = "CASE f.source WHEN 'human' THEN 0 WHEN 'outcome' THEN 1 ELSE 2 END"
# Examples learned from feedback keep where they came from.
EXAMPLE_SOURCE = {"human": "production", "outcome": "production", "downstream": "agent"}


async def _prediction(model_id: UUID, prediction_id: UUID | None, ref: str | None) -> dict:
    if prediction_id is not None:
        row = await get_pool().fetchrow(
            """SELECT p.*, v.labels FROM intuition_predictions p
                 JOIN intuition_versions v ON v.id = p.version_id
                WHERE p.id = $1 AND p.model_id = $2""",
            prediction_id,
            model_id,
        )
    else:
        # A reference can be reused; feedback applies to its newest call.
        row = await get_pool().fetchrow(
            """SELECT p.*, v.labels FROM intuition_predictions p
                 JOIN intuition_versions v ON v.id = p.version_id
                WHERE p.model_id = $1 AND p.ref = $2
                ORDER BY p.created_at DESC, p.id DESC LIMIT 1""",
            model_id,
            ref,
        )
    if row is None:
        raise service.NotFound("Prediction not found")
    return dict(row)


async def record(
    owner_id: UUID,
    model_id: UUID,
    *,
    prediction_id: UUID | None = None,
    ref: str | None = None,
    label: str | None = None,
    value: float | None = None,
    source: str = "human",
    note: str = "",
    learn: bool = False,
    example_source: str | None = None,
) -> dict:
    model = await service._model(owner_id, model_id)
    if (prediction_id is None) == (ref is None):
        raise ValueError("Identify the prediction by prediction_id or ref, not both")
    if source not in SOURCES:
        raise ValueError(f"Feedback source must be one of {', '.join(SOURCES)}")
    if label is None and value is None:
        raise ValueError("Feedback needs a label, a value, or both")
    if value is not None and not math.isfinite(value):
        raise ValueError("Feedback value must be a finite number")
    if learn and label is None:
        raise ValueError("Only labeled feedback can become a training example")
    prediction = await _prediction(model_id, prediction_id, ref)
    if "error" in prediction["output"]:
        raise service.Conflict("This call failed, so there is no decision to give feedback on")
    if label is not None:
        kind = "pair" if prediction["kind"] == "compare" else "item"
        allowed = valid_example_labels(model["output_type"], kind, prediction["labels"])
        if label not in allowed:
            raise ValueError(f"Label must be one of {', '.join(allowed)}")
    row = await get_pool().fetchrow(
        """INSERT INTO intuition_feedback (model_id, prediction_id, label, value, source, note)
           VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
        model_id,
        prediction["id"],
        label,
        value,
        source,
        note,
    )
    example = (
        await _learn(owner_id, model_id, prediction, label, note, source, example_source)
        if learn
        else None
    )
    if source == "human" and prediction["status"] in ("unreviewed", "escalated"):
        await get_pool().execute(
            "UPDATE intuition_predictions SET status = 'labeled' WHERE id = $1", prediction["id"]
        )
    return {"feedback": dict(row), "prediction_id": str(prediction["id"]), "example": example}


async def _learn(owner_id, model_id, prediction, label, note, source, example_source) -> dict:
    """Make (or relabel) the training example for this call."""
    if prediction["example_id"] is not None:
        try:
            return await service.update_example(
                owner_id,
                model_id,
                prediction["example_id"],
                {"label": label, "needs_review": False},
            )
        except service.NotFound:
            pass  # The example was deleted; learn it again.
    payload = prediction["input"]
    (example,) = await service.add_examples(
        owner_id,
        model_id,
        [
            {
                "item": payload["item"],
                "item_b": payload.get("item_b"),
                "label": label,
                "note": note or f"From prediction {prediction['id']} by {prediction['caller']}",
                "split": "train",
                "source": example_source or EXAMPLE_SOURCE[source],
            }
        ],
        example_source or EXAMPLE_SOURCE[source],
    )
    await get_pool().execute(
        "UPDATE intuition_predictions SET status = 'labeled', example_id = $2 WHERE id = $1",
        prediction["id"],
        UUID(example["id"]),
    )
    return example


async def history(prediction_ids: list[UUID]) -> dict[str, list[dict]]:
    rows = await get_pool().fetch(
        """SELECT id, prediction_id, label, value, source, note, created_at
             FROM intuition_feedback WHERE prediction_id = ANY($1::uuid[])
            ORDER BY created_at DESC, id DESC""",
        prediction_ids,
    )
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r["prediction_id"]), []).append(dict(r))
    return out
