"""Runs: eval calls made during one task, and the outcome that task had later.

A caller tags calls with a run id (an agent episode, a conversation, a pipeline
execution) and reports one outcome in [0, 1] when the task is done. Credit
assignment then asks, per eval: do this eval's decisions inside a run predict
how the run ended?

That link is learned, not assumed. For each eval, the runs with an outcome
become rows of (mean decision probabilities in the run, succeeded?) and an L2
logistic regression is fitted over them, with bootstrap intervals and
cross-validated accuracy, so a weak or noisy link says so. A single call's
credit is its contribution to the predicted outcome relative to the average
call. Credit never becomes training data on its own: it only nominates calls
for a human to label (selection.py), since a run can fail for reasons no
single decision caused.
"""

from __future__ import annotations

import math
import random
from uuid import UUID

import numpy as np

from ...database import get_pool
from . import head as heads
from . import service

MIN_RUNS = 6
BOOTSTRAP = 200
L2 = service.DEFAULT_L2
FOLDS = 4
SUSPECT_CREDIT = 0.1


async def ensure(owner_id: UUID, external_id: str) -> UUID:
    if not external_id or len(external_id) > 200:
        raise ValueError("Run ids are 1-200 characters")
    return await get_pool().fetchval(
        """INSERT INTO intuition_runs (owner_user_id, external_id) VALUES ($1, $2)
           ON CONFLICT (owner_user_id, external_id) DO UPDATE SET external_id = EXCLUDED.external_id
           RETURNING id""",
        owner_id,
        external_id,
    )


async def record_outcome(
    owner_id: UUID, external_id: str, value: float, source: str, note: str
) -> dict:
    if not (math.isfinite(value) and 0 <= value <= 1):
        raise ValueError("A run outcome is a number from 0 (failed) to 1 (succeeded)")
    run_id = await ensure(owner_id, external_id)
    await get_pool().execute(
        """UPDATE intuition_runs SET outcome = $2, outcome_source = $3, note = $4, outcome_at = now()
            WHERE id = $1""",
        run_id,
        value,
        source,
        note,
    )
    return await get(owner_id, external_id)


async def get(owner_id: UUID, external_id: str) -> dict:
    run = await get_pool().fetchrow(
        "SELECT * FROM intuition_runs WHERE owner_user_id = $1 AND external_id = $2",
        owner_id,
        external_id,
    )
    if run is None:
        raise service.NotFound("Run not found")
    calls = await get_pool().fetch(
        """SELECT p.id, p.model_id, m.name AS eval_name, p.kind, p.output, p.confidence, p.step,
                  p.ref, p.created_at, v.number AS version
             FROM intuition_predictions p
             JOIN intuition_models m ON m.id = p.model_id
             JOIN intuition_versions v ON v.id = p.version_id
            WHERE p.run_id = $1 ORDER BY p.step NULLS LAST, p.created_at""",
        run["id"],
    )
    return {
        **dict(run),
        "calls": [
            {
                **{
                    k: c[k]
                    for k in (
                        "id",
                        "model_id",
                        "eval_name",
                        "kind",
                        "confidence",
                        "step",
                        "ref",
                        "created_at",
                        "version",
                    )
                },
                "decision": c["output"].get("label") or c["output"].get("winner"),
                "failed": "error" in c["output"],
            }
            for c in calls
        ],
    }


async def list_runs(owner_id: UUID, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT r.*, count(p.id)::int AS calls, count(DISTINCT p.model_id)::int AS evals
             FROM intuition_runs r LEFT JOIN intuition_predictions p ON p.run_id = r.id
            WHERE r.owner_user_id = $1 GROUP BY r.id
            ORDER BY r.created_at DESC LIMIT $2 OFFSET $3""",
        owner_id,
        limit,
        offset,
    )
    return [dict(r) for r in rows]


# ── Credit assignment ────────────────────────────────────────────────────


def _decision_vector(output: dict, classes: list[str]) -> list[float] | None:
    probabilities = output.get("probabilities")
    if not probabilities or any(c not in probabilities for c in classes):
        return None
    return [float(probabilities[c]) for c in classes]


async def _observations(model: dict, classes: list[str]):
    records = await get_pool().fetch(
        """SELECT p.id, p.run_id, p.output, p.created_at, r.external_id, r.outcome
             FROM intuition_predictions p JOIN intuition_runs r ON r.id = p.run_id
            WHERE p.model_id = $1 AND p.kind = 'predict' AND r.outcome IS NOT NULL
              AND NOT (p.output ? 'error')
            ORDER BY r.external_id, p.created_at, p.id""",
        model["id"],
    )
    calls, by_run = [], {}
    for r in records:
        f = _decision_vector(r["output"], classes)
        if f is None:
            continue
        calls.append({**dict(r), "f": f})
        by_run.setdefault(r["run_id"], []).append(f)
    outcomes = {r["run_id"]: r["outcome"] for r in records}
    names = {r["run_id"]: r["external_id"] for r in records}
    rows = [
        {
            "run_id": run_id,
            "run": names[run_id],
            "kind": "item",
            "f": list(np.mean(vectors, axis=0)),
            "label": "good" if outcomes[run_id] >= 0.5 else "bad",
        }
        for run_id, vectors in by_run.items()
    ]
    return calls, rows


def _fit(classes: list[str], rows: list[dict]) -> dict:
    return heads.fit("preference", classes, ["score"], rows, L2)


def _cv_accuracy(classes: list[str], rows: list[dict]) -> float | None:
    order = sorted(rows, key=lambda r: r["run"])
    correct = []
    for k in range(FOLDS):
        train = [r for i, r in enumerate(order) if i % FOLDS != k]
        test = [r for i, r in enumerate(order) if i % FOLDS == k]
        if len({r["label"] for r in train}) < 2 or not test:
            continue
        head = _fit(classes, train)
        correct.extend(
            heads.predict_preference_item(head, r["f"])["label"] == r["label"] for r in test
        )
    return sum(correct) / len(correct) if correct else None


async def credit(owner_id: UUID, model_id: UUID) -> dict:
    model = await service._model(owner_id, model_id)
    version = await service._load_version(model["active_version_id"] or model["draft_version_id"])
    classes = (
        [label["id"] for label in version["labels"]]
        if model["output_type"] == "choice"
        else ["good", "bad"]
    )
    calls, rows = await _observations(model, classes)
    successes = sum(r["label"] == "good" for r in rows)
    base = {
        "decisions": classes,
        "runs": len(rows),
        "calls": len(calls),
        "success_rate": successes / len(rows) if rows else None,
        "minimum_runs": MIN_RUNS,
    }
    by_decision = []
    for i, c in enumerate(classes):
        group = [r for r in rows if int(np.argmax(r["f"])) == i]
        by_decision.append(
            {
                "decision": c,
                "runs": len(group),
                "success_rate": sum(r["label"] == "good" for r in group) / len(group)
                if group
                else None,
            }
        )
    base["by_decision"] = by_decision
    if len(rows) < MIN_RUNS or successes in (0, len(rows)):
        return {
            **base,
            "ready": False,
            "reason": f"Needs at least {MIN_RUNS} runs with outcomes, including successes and failures",
        }

    head = _fit(classes, rows)
    weights = head["weights"][0]
    rng = random.Random(0)
    samples = []
    for _ in range(BOOTSTRAP):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        if len({r["label"] for r in sample}) == 2:
            samples.append(_fit(classes, sample)["weights"][0])
    intervals = (
        [
            {"low": float(np.percentile(column, 2.5)), "high": float(np.percentile(column, 97.5))}
            for column in np.asarray(samples).T
        ]
        if samples
        else [{"low": None, "high": None} for _ in classes]
    )
    mean_f = np.mean([c["f"] for c in calls], axis=0)
    scored = []
    for c in calls:
        contribution = float(np.dot(weights, np.asarray(c["f"]) - mean_f))
        succeeded = c["outcome"] >= 0.5
        scored.append(
            {
                "prediction_id": str(c["id"]),
                "run": c["external_id"],
                "outcome": c["outcome"],
                "decision": c["output"].get("label"),
                "credit": contribution,
                # The call pushed toward the opposite of what happened.
                "suspect": (contribution > SUSPECT_CREDIT and not succeeded)
                or (contribution < -SUSPECT_CREDIT and succeeded),
            }
        )
    scored.sort(key=lambda c: abs(c["credit"]), reverse=True)
    return {
        **base,
        "ready": True,
        "weights": [
            {"decision": c, "weight": float(w), **interval}
            for c, w, interval in zip(classes, weights, intervals)
        ],
        "cv_accuracy": _cv_accuracy(classes, rows),
        "mean_decision": [float(v) for v in mean_f],
        "calls_by_credit": scored[:50],
    }
