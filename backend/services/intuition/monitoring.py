"""Eval monitoring from logged calls and their feedback; never calls the judge.

Accuracy and calibration are measured only on calls that received a labeled
feedback "truth" (see feedback.py). Drift compares recent calls of the active
version with the labeled training examples that version was fitted on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np

from ...database import get_pool
from . import head as heads
from . import service
from .feedback import TRUTH_ORDER_SQL

MAX_CALLS = 20000
DRIFT_DAYS = 7
MAX_DISAGREEMENTS = 50
TOP_SHIFTS = 8


def _predicted(output: dict) -> str | None:
    return output.get("label") or output.get("winner")


def _top_feature(output: dict, predicted: str) -> dict | None:
    """The rubric answer that pushed hardest toward the wrong decision."""
    contributions = output.get("contributions") or {}
    if predicted in contributions:
        values = contributions[predicted]
    elif "score" in contributions:
        sign = 1 if predicted == "good" else -1
        values = {k: sign * v for k, v in contributions["score"].items()}
    elif contributions and all(isinstance(v, int | float) for v in contributions.values()):
        sign = 1 if predicted == "a" else -1
        values = {k: sign * v for k, v in contributions.items()}
    else:
        return None
    if not values:
        return None
    name = max(values, key=values.get)
    return {"feature": name, "contribution": values[name]}


def _preview(payload: dict) -> str:
    item = payload.get("item")
    text = item if isinstance(item, str) else (item or {}).get("title") or str(item)
    return text[:240]


def _summary(rows: list[dict]) -> dict:
    graded = [r for r in rows if r["truth"] is not None]
    correct = [r["predicted"] == r["truth"] for r in graded]
    ece, reliability = (
        heads.calibration([r["confidence"] for r in graded], correct) if graded else (None, [])
    )
    values = [r["value"] for r in rows if r["value"] is not None]
    return {
        "calls": len(rows),
        "errors": sum(r["error"] for r in rows),
        "with_feedback": len(graded),
        "accuracy": float(np.mean(correct)) if graded else None,
        "ece": ece,
        "reliability": reliability,
        "mean_confidence": (
            float(np.mean([r["confidence"] for r in rows if not r["error"]]))
            if any(not r["error"] for r in rows)
            else None
        ),
        "mean_value": float(np.mean(values)) if values else None,
    }


async def overview(owner_id: UUID, model_id: UUID, days: int = 30) -> dict:
    model = await service._model(owner_id, model_id)
    since = datetime.now(UTC) - timedelta(days=days)
    records = await get_pool().fetch(
        f"""SELECT p.id, p.kind, p.input, p.output, p.confidence, p.ref, p.created_at,
                   v.number AS version, p.version_id, t.label AS truth, t.source AS truth_source,
                   o.value
              FROM intuition_predictions p
              JOIN intuition_versions v ON v.id = p.version_id
              LEFT JOIN LATERAL (
                SELECT f.label, f.source FROM intuition_feedback f
                 WHERE f.prediction_id = p.id AND f.label IS NOT NULL
                 ORDER BY {TRUTH_ORDER_SQL}, f.created_at DESC LIMIT 1) t ON true
              LEFT JOIN LATERAL (
                SELECT f.value FROM intuition_feedback f
                 WHERE f.prediction_id = p.id AND f.value IS NOT NULL
                 ORDER BY f.created_at DESC LIMIT 1) o ON true
             WHERE p.model_id = $1 AND p.created_at >= $2
             ORDER BY p.created_at DESC LIMIT $3""",
        model_id,
        since,
        MAX_CALLS,
    )
    rows = []
    for r in records:
        error = "error" in r["output"]
        rows.append(
            {
                **dict(r),
                "error": error,
                "predicted": None if error else _predicted(r["output"]),
                # Failed calls have no decision to grade.
                "truth": None if error else r["truth"],
                "confidence": r["confidence"] or 0.0,
            }
        )

    by_day: dict[str, list[dict]] = {}
    by_version: dict[int, list[dict]] = {}
    for r in rows:
        by_day.setdefault(r["created_at"].date().isoformat(), []).append(r)
        by_version.setdefault(r["version"], []).append(r)
    daily = []
    for day in sorted(by_day):
        bucket = by_day[day]
        mix: dict[str, int] = {}
        for r in bucket:
            if r["predicted"]:
                mix[r["predicted"]] = mix.get(r["predicted"], 0) + 1
        summary = _summary(bucket)
        summary.pop("reliability")
        daily.append({"date": day, **summary, "labels": mix})

    disagreements = [
        {
            "prediction_id": str(r["id"]),
            "created_at": r["created_at"],
            "ref": r["ref"],
            "version": r["version"],
            "predicted": r["predicted"],
            "truth": r["truth"],
            "truth_source": r["truth_source"],
            "confidence": r["confidence"],
            "preview": _preview(r["input"]),
            "top_feature": _top_feature(r["output"], r["predicted"]),
        }
        for r in rows
        if r["truth"] is not None and r["predicted"] != r["truth"]
    ][:MAX_DISAGREEMENTS]

    return {
        "days": days,
        "truncated": len(rows) == MAX_CALLS,
        "summary": _summary(rows),
        "daily": daily,
        "versions": [
            {"version": number, **{k: v for k, v in _summary(group).items() if k != "reliability"}}
            for number, group in sorted(by_version.items(), reverse=True)
        ],
        "drift": (drift := await _drift(model, rows)),
        "disagreements": disagreements,
        **(await staleness(model, rows, drift)),
    }


async def _drift(model: dict, rows: list[dict]) -> dict | None:
    """Recent decisions and rubric answers of the active version vs its training data."""
    active = await service._load_version(model["active_version_id"])
    if active is None or active["head_stale"]:
        return None
    train, _ = await service._rows(model, active)
    train = [r for r in train if r["split"] == "train" and r["kind"] == "item"]
    cutoff = datetime.now(UTC) - timedelta(days=DRIFT_DAYS)
    recent = [
        r
        for r in rows
        if not r["error"]
        and r["kind"] == "predict"
        and r["version_id"] == active["id"]
        and r["created_at"] >= cutoff
    ]
    if not train or not recent:
        return {
            "window_days": DRIFT_DAYS,
            "recent_calls": len(recent),
            "labels": [],
            "features": [],
        }

    labels = sorted({r["label"] for r in train} | {r["predicted"] for r in recent})
    label_shift = [
        {
            "label": label,
            "train_share": sum(r["label"] == label for r in train) / len(train),
            "recent_share": sum(r["predicted"] == label for r in recent) / len(recent),
        }
        for label in labels
    ]

    recent_features = []
    for r in recent:
        answers = r["output"].get("rubric") or {}
        try:
            recent_features.append(
                heads.answers_to_features(
                    active["rubric"], {q: {"probabilities": p} for q, p in answers.items()}
                )
            )
        except KeyError:
            continue  # Logged before a rubric edit; not comparable.
    features = []
    if recent_features:
        train_mean = np.mean([r["f"] for r in train], axis=0)
        recent_mean = np.mean(recent_features, axis=0)
        for name, t, n in zip(active["feature_names"], train_mean, recent_mean):
            features.append(
                {
                    "feature": name,
                    "train_mean": float(t),
                    "recent_mean": float(n),
                    "shift": float(n - t),
                }
            )
        features.sort(key=lambda f: abs(f["shift"]), reverse=True)
    return {
        "window_days": DRIFT_DAYS,
        "version": active["number"],
        "recent_calls": len(recent),
        "train_examples": len(train),
        "labels": label_shift,
        "features": features[:TOP_SHIFTS],
    }


STALE_AGREEMENT_DROP = 0.10
STALE_LABEL_SHIFT = 0.25
STALE_FEATURE_SHIFT = 0.30
STALE_MIN_FEEDBACK = 8


async def staleness(model: dict, rows: list[dict], drift: dict | None) -> dict:
    """Whether production has moved away from what the rubric was built on, and why.

    The rubric stays still while the agent does not: agreement with production
    feedback falling below the held-out accuracy, the decision mix shifting,
    or rubric answers moving far from their training values all say the
    criteria were tuned for a different distribution and should be refined."""
    reasons = []
    active = await service._load_version(model["active_version_id"])
    held_out = (((active or {}).get("metrics") or {}).get("eval") or {}).get("accuracy")
    cutoff = datetime.now(UTC) - timedelta(days=DRIFT_DAYS)
    graded = [
        r for r in rows if r["truth"] is not None and r["created_at"] >= cutoff and not r["error"]
    ]
    if held_out is not None and len(graded) >= STALE_MIN_FEEDBACK:
        recent = float(np.mean([r["predicted"] == r["truth"] for r in graded]))
        if recent < held_out - STALE_AGREEMENT_DROP:
            reasons.append(
                f"agreement with production feedback is {recent:.0%} over the last {DRIFT_DAYS} days, "
                f"against {held_out:.0%} on held-out examples"
            )
    for shift in (drift or {}).get("labels", []):
        if abs(shift["recent_share"] - shift["train_share"]) >= STALE_LABEL_SHIFT:
            reasons.append(
                f"'{shift['label']}' is now {shift['recent_share']:.0%} of decisions, against {shift['train_share']:.0%} in its examples"
            )
            break
    for feature in (drift or {}).get("features", [])[:1]:
        if abs(feature["shift"]) >= STALE_FEATURE_SHIFT:
            reasons.append(
                f"answers to '{feature['feature']}' moved by {feature['shift']:+.2f} from its examples"
            )
    return {"refine_suggested": bool(reasons), "refine_reason": "; ".join(reasons) or None}
