"""Which data is worth a human's attention: the label queue and seed examples.

The label queue ranks unreviewed calls by how much a label would teach the eval:
calls it was unsure about, calls unlike anything it was trained on, and calls
where an outcome or downstream verdict already disagrees with the decision.
Nothing here labels data automatically.
"""

from __future__ import annotations

import json
import math
from uuid import UUID

import numpy as np

from ...database import get_pool
from . import head as heads
from . import service
from .feedback import TRUTH_ORDER_SQL
from .spec import MAX_SEEDS

CANDIDATES = 500
QUEUE_SIZE = 20
# Weights of each reason in the ranking; a conflicting outcome outranks both.
UNCERTAINTY_WEIGHT = 0.5
NOVELTY_WEIGHT = 0.3
CONFLICT_BONUS = 1.0
RUN_CREDIT_BONUS = 0.6


def _uncertainty(output: dict) -> float:
    """0 when certain, 1 at a uniform guess across the eval's labels."""
    probabilities = output.get("probabilities") or {}
    if "p_a_wins" in output:
        probabilities = {"a": output["p_a_wins"], "b": 1 - output["p_a_wins"]}
    if len(probabilities) < 2:
        return 0.0
    top = max(probabilities.values())
    floor = 1 / len(probabilities)
    return float(min(1.0, max(0.0, (1 - top) / (1 - floor))))


def _features(rubric: list[dict], answers: dict) -> list[float] | None:
    try:
        return heads.answers_to_features(
            rubric, {q: {"probabilities": p} for q, p in answers.items()}
        )
    except KeyError:
        return None  # Logged under a different rubric.


async def label_queue(owner_id: UUID, model_id: UUID, limit: int = QUEUE_SIZE) -> list[dict]:
    model = await service._model(owner_id, model_id)
    active = await service._load_version(model["active_version_id"])
    records = await get_pool().fetch(
        f"""SELECT p.id, p.kind, p.input, p.output, p.confidence, p.ref, p.caller, p.created_at,
                   p.version_id, v.number AS version, c.label AS conflict_label, c.source AS conflict_source
              FROM intuition_predictions p
              JOIN intuition_versions v ON v.id = p.version_id
              LEFT JOIN LATERAL (
                SELECT f.label, f.source FROM intuition_feedback f
                 WHERE f.prediction_id = p.id AND f.label IS NOT NULL
                 ORDER BY {TRUTH_ORDER_SQL}, f.created_at DESC LIMIT 1) c ON true
             WHERE p.model_id = $1 AND p.status = 'unreviewed' AND NOT (p.output ? 'error')
             ORDER BY p.created_at DESC LIMIT $2""",
        model_id,
        CANDIDATES,
    )
    labeled = []
    if active is not None and not active["head_stale"]:
        rows, _ = await service._rows(model, active)
        labeled = [r["f"] for r in rows if r["kind"] == "item"]
    labeled_matrix = np.asarray(labeled, dtype=float) if labeled else None
    from . import runs

    linked = await runs.credit(owner_id, model_id)
    suspects = {
        c["prediction_id"]: c for c in (linked.get("calls_by_credit") or []) if c["suspect"]
    }

    ranked, seen = [], set()
    for r in records:
        key = json.dumps(r["input"], sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        output = r["output"]
        predicted = output.get("label") or output.get("winner")
        uncertainty = _uncertainty(output)
        novelty = None
        if (
            labeled_matrix is not None
            and r["kind"] == "predict"
            and r["version_id"] == active["id"]
        ):
            f = _features(active["rubric"], output.get("rubric") or {})
            if f is not None:
                distance = np.min(np.linalg.norm(labeled_matrix - np.asarray(f), axis=1))
                novelty = float(min(1.0, distance / math.sqrt(len(f))))
        conflict = r["conflict_label"] is not None and r["conflict_label"] != predicted
        score = UNCERTAINTY_WEIGHT * uncertainty + NOVELTY_WEIGHT * (novelty or 0.0)
        if conflict:
            score += CONFLICT_BONUS
        suspect = suspects.get(str(r["id"]))
        if suspect:
            score += RUN_CREDIT_BONUS
        reasons = []
        if conflict:
            reasons.append(f"{r['conflict_source']} feedback says {r['conflict_label']}")
        if suspect:
            reasons.append(
                "its run failed after this decision"
                if suspect["outcome"] < 0.5
                else "its run succeeded despite this decision"
            )
        if uncertainty >= 0.5:
            reasons.append("the eval was unsure")
        if novelty is not None and novelty >= 0.35:
            reasons.append("unlike its training examples")
        if not reasons:
            reasons.append(
                "among its least certain calls"
                if UNCERTAINTY_WEIGHT * uncertainty >= NOVELTY_WEIGHT * (novelty or 0.0)
                else "among its least familiar inputs"
            )
        ranked.append(
            {
                "prediction_id": str(r["id"]),
                "kind": r["kind"],
                "input": r["input"],
                "predicted": predicted,
                "confidence": r["confidence"],
                "ref": r["ref"],
                "caller": r["caller"],
                "version": r["version"],
                "created_at": r["created_at"],
                "uncertainty": uncertainty,
                "novelty": novelty,
                "conflict": conflict,
                "score": score,
                "reasons": reasons,
            }
        )
    ranked.sort(key=lambda x: (-x["score"], -x["created_at"].timestamp()))
    return ranked[:limit]


def seeds(train: list[dict], limit: int = MAX_SEEDS) -> list[dict]:
    """Label-balanced reference examples, preferring corrected calls, then the newest."""
    by_label: dict[str, list[dict]] = {}
    for e in sorted(
        train,
        key=lambda e: (e["source"] != "production", -e["created_at"].timestamp(), e["id"]),
    ):
        by_label.setdefault(e["label"], []).append(e)
    picked: list[dict] = []
    while len(picked) < limit and any(by_label.values()):
        for label in sorted(by_label):
            if by_label[label] and len(picked) < limit:
                picked.append(by_label[label].pop(0))
    return picked
