"""Improve an eval's criteria: try alternatives, keep what predicts the labels best.

The search starts from the saved version and tries a few alternative rubrics:
the current one, one with a question aimed at its mistakes, one with its weakest
questions rewritten, one with near-unused questions removed, and a fresh draft.
Each is graded on the calibration examples (answers are cached per question, so
unchanged questions cost nothing) and scored by cross-validated log loss on
those examples only. Held-out examples are never used to choose, so the gate
that follows still measures the winner honestly.

The winner becomes the draft and is fitted; applying it goes through the normal
regression gate. Runs as a Celery job because grading takes minutes.
"""

from __future__ import annotations

import json
import logging
import math
import random
from uuid import UUID

from pydantic import BaseModel, Field

from ...database import get_pool
from .. import llm
from . import head as heads
from . import providers, service
from .spec import MAX_QUESTIONS, classes, feature_names

log = logging.getLogger(__name__)

MAX_ITEMS = 200
FOLDS = 4
MIN_ROWS = 4
PRUNE_SHARE = 0.05
TIE = 0.005
GRADE_BATCH = 12
LEASE = "30 minutes"


async def _expire(model_id: UUID) -> None:
    await get_pool().execute(
        """UPDATE intuition_jobs SET status = 'failed', finished_at = now(),
                  error = 'The improvement stopped responding; start it again'
            WHERE model_id = $1 AND status IN ('queued', 'running') AND lease_until < now()""",
        model_id,
    )


async def start(owner_id: UUID, model_id: UUID) -> dict:
    model = await service._model(owner_id, model_id)
    active = await service._load_version(model["active_version_id"])
    if active is None or active["head_stale"] or not active["rubric"]:
        raise service.Conflict("Save the eval first; improving starts from its saved criteria")
    await _expire(model_id)
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT 1 FROM intuition_models WHERE id = $1 FOR UPDATE", model_id)
        if await conn.fetchval(
            "SELECT 1 FROM intuition_jobs WHERE model_id = $1 AND status IN ('queued', 'running')",
            model_id,
        ):
            raise service.Conflict("An improvement is already running for this eval")
        job = await conn.fetchrow(
            f"""INSERT INTO intuition_jobs (model_id, kind, progress, lease_until)
               VALUES ($1, 'improve', $2, now() + interval '{LEASE}') RETURNING *""",
            model_id,
            {"stage": "queued", "message": "Waiting to start…"},
        )
    from ...tasks import intuitions as tasks

    tasks.improve.delay(str(job["id"]))
    return dict(job)


async def latest(owner_id: UUID, model_id: UUID) -> dict | None:
    await service._model(owner_id, model_id)
    await _expire(model_id)
    row = await get_pool().fetchrow(
        "SELECT * FROM intuition_jobs WHERE model_id = $1 AND kind = 'improve' "
        "ORDER BY created_at DESC LIMIT 1",
        model_id,
    )
    return dict(row) if row else None


async def _progress(job_id: UUID, stage: str, message: str, completed=0, total=0) -> None:
    await get_pool().execute(
        f"""UPDATE intuition_jobs SET progress = $2, lease_until = now() + interval '{LEASE}'
            WHERE id = $1""",
        job_id,
        {"stage": stage, "message": message, "completed": completed, "total": total},
    )


async def run(job_id: UUID) -> None:
    row = await get_pool().fetchrow(
        """UPDATE intuition_jobs j SET status = 'running', started_at = now()
             FROM intuition_models m
            WHERE j.id = $1 AND j.status = 'queued' AND m.id = j.model_id
        RETURNING j.model_id, m.owner_user_id""",
        job_id,
    )
    if row is None:
        return
    try:
        result = await _search(job_id, row["owner_user_id"], row["model_id"])
    except Exception as exc:
        log.exception("Eval improvement %s failed", job_id)
        message = str(exc) if isinstance(exc, ValueError | providers.ProviderError) else ""
        await get_pool().execute(
            """UPDATE intuition_jobs SET status = 'failed', finished_at = now(), error = $2
                WHERE id = $1""",
            job_id,
            (message or "The improvement failed; try again")[:500],
        )
        return
    await get_pool().execute(
        """UPDATE intuition_jobs SET status = 'succeeded', finished_at = now(), result = $2,
                  progress = progress || '{"stage": "done"}'::jsonb
            WHERE id = $1""",
        job_id,
        result,
    )


# ── Candidates ───────────────────────────────────────────────────────────


def _question_weights(version: dict) -> dict[str, float]:
    """Share of the head's total absolute weight carried by each question."""
    head = version["head"]
    totals = {q["id"]: 0.0 for q in version["rubric"]}
    for j, name in enumerate(head["feature_names"]):
        qid = name.split("=", 1)[0]
        totals[qid] = totals.get(qid, 0.0) + sum(abs(row[j]) for row in head["weights"])
    whole = sum(totals.values()) or 1.0
    return {q: w / whole for q, w in totals.items()}


class _Rewrite(BaseModel):
    rationale: str
    questions: list[service._QuestionDraft] = Field(min_length=1)


async def _rewrite(version: dict, weakest: list[dict]) -> tuple[list[dict], str]:
    result = await llm.complete_structured(
        system=(
            "You improve a rubric used by a judge model. The listed questions carry almost no "
            "weight in the user's decisions: they are vague, redundant, or ask about the wrong "
            "property. Replace each with a sharper question about a different observable property "
            "that would explain the user's labels. " + service.QUESTION_FORMAT
        ),
        prompt=(
            f"WHAT THE MODEL JUDGES:\n{version['description']}\n\n"
            f"FULL RUBRIC:\n{json.dumps(version['rubric'], ensure_ascii=False)}\n\n"
            f"REPLACE THESE QUESTIONS:\n{json.dumps(weakest, ensure_ascii=False)}\n\n"
            f"Return {len(weakest)} replacement questions."
        ),
        output_model=_Rewrite,
        tier=llm.ModelTier.QUALITY,
        max_tokens=2048,
    )
    weak_ids = {q["id"] for q in weakest}
    kept = [q for q in version["rubric"] if q["id"] not in weak_ids]
    taken = {q["id"] for q in kept}
    new = [service._question(q, taken) for q in result.questions[: len(weakest)]]
    return kept + new, result.rationale


async def _candidates(owner_id: UUID, model_id: UUID, active: dict) -> list[dict]:
    rubric = active["rubric"]
    out = [
        {
            "name": "current",
            "title": "Current criteria",
            "rationale": "The saved version's criteria, unchanged.",
            "rubric": rubric,
        }
    ]
    shares = _question_weights(active)
    if len(rubric) < MAX_QUESTIONS:
        try:
            suggestion = await service.suggest_question(owner_id, model_id)
            out.append(
                {
                    "name": "add_question",
                    "title": "Add a question for its mistakes",
                    "rationale": suggestion["rationale"],
                    "rubric": rubric + [suggestion["question"]],
                }
            )
        except service.Conflict:
            pass  # No mistakes to learn from.
    # Questions answered by other evals or by a fitted probe are kept as they
    # are; only judge questions are rewritten or redrafted.
    signals = [q for q in rubric if q["type"] in ("eval", "probe")]
    judged = [q for q in rubric if q["type"] not in ("eval", "probe")]
    if len(judged) >= 2:
        weakest = sorted(judged, key=lambda q: shares.get(q["id"], 0))[: max(1, len(judged) // 4)]
        rewritten, why = await _rewrite(active, weakest)
        out.append(
            {
                "name": "rewrite_weakest",
                "title": "Rewrite the weakest questions",
                "rationale": why,
                "rubric": rewritten,
            }
        )
    pruned = [q for q in rubric if shares.get(q["id"], 0) >= PRUNE_SHARE]
    if 1 <= len(pruned) < len(rubric):
        out.append(
            {
                "name": "prune",
                "title": "Remove unused questions",
                "rationale": "Drops questions carrying under 5% of the decision weight.",
                "rubric": pruned,
            }
        )
    fresh = await service.draft_rubric(owner_id, model_id, max(3, len(judged)), "")
    taken = {q["id"] for q in signals}
    fresh["rubric"] = [q for q in fresh["rubric"] if q["id"] not in taken][
        : MAX_QUESTIONS - len(signals)
    ] + signals
    out.append(
        {
            "name": "fresh",
            "title": "Draft new criteria",
            "rationale": fresh["rationale"],
            "rubric": fresh["rubric"],
        }
    )
    return out


# ── Search ───────────────────────────────────────────────────────────────


def _cv(output_type: str, rubric: list[dict], labels: list[dict], rows: list[dict]) -> dict:
    names, cls = feature_names(rubric), classes(output_type, labels)
    order = sorted(rows, key=lambda r: r["example_id"])
    folds = min(FOLDS, len(order))
    losses, correct = [], []
    for k in range(folds):
        train = [r for i, r in enumerate(order) if i % folds != k]
        test = [r for i, r in enumerate(order) if i % folds == k]
        if output_type == "choice" and len({r["label"] for r in train}) < 2:
            continue
        head = heads.fit(output_type, names, cls, train, service.DEFAULT_L2)
        for r in test:
            p, predicted = heads.row_probability(head, output_type, r)
            losses.append(-math.log(max(p, 1e-9)))
            correct.append(predicted == r["label"])
    if not losses:
        return {"cv_log_loss": None, "cv_accuracy": None, "rows": len(rows)}
    return {
        "cv_log_loss": sum(losses) / len(losses),
        "cv_accuracy": sum(correct) / len(correct),
        "rows": len(rows),
    }


async def _grade(job_id: UUID, model_id: UUID, versions: list[dict], items: list) -> None:
    jobs = []
    for version in versions:
        jobs.extend(await service._pending_jobs({"id": model_id}, [version], items))
    for start in range(0, len(jobs), GRADE_BATCH):
        await _progress(
            job_id,
            "grading",
            f"Answering criteria for {len(jobs)} example evaluations…",
            start,
            len(jobs),
        )
        batch = jobs[start : start + GRADE_BATCH]
        results = await providers.grade_many(batch)
        failed = [i for i, r in enumerate(results) if isinstance(r, Exception)]
        if failed:  # One retry for transient judge errors.
            for i, result in zip(failed, await providers.grade_many([batch[i] for i in failed])):
                if isinstance(result, Exception):
                    raise result
                results[i] = result
        for (version, _q, seeds, item), result in zip(batch, results):
            await service._store_answers(model_id, version, seeds, item, result)


async def _search(job_id: UUID, owner_id: UUID, model_id: UUID) -> dict:
    model = await service._model(owner_id, model_id)
    active = await service._load_version(model["active_version_id"])
    if active is None or active["head_stale"]:
        raise service.Conflict("Save the eval first; improving starts from its saved criteria")
    examples = [
        e
        for e in await service._examples(model_id)
        if e["label"] is not None and not e["needs_review"] and e["split"] == "train"
    ]
    if len(examples) > MAX_ITEMS:
        examples = random.Random(0).sample(examples, MAX_ITEMS)
    if len(examples) < MIN_ROWS:
        raise service.Conflict(
            f"Add at least {MIN_ROWS} labeled calibration examples before improving"
        )
    await _progress(job_id, "proposing", "Proposing alternative criteria…")
    candidates = await _candidates(owner_id, model_id, active)
    # Candidates share the saved version's description, seeds and judge, so every
    # question is asked in the same context and unchanged questions hit the cache.
    versions = [{**active, "rubric": c["rubric"]} for c in candidates]
    items = [i for e in examples for i in service._items_of(e)]
    await _grade(job_id, model_id, versions, items)

    await _progress(job_id, "scoring", "Comparing criteria by cross-validation…")
    current = {q["id"]: q for q in active["rubric"]}
    for candidate, version in zip(candidates, versions):
        features = iter(await service._features(model_id, version, items, grade_missing=False))
        rows = []
        for e in examples:
            f = next(features)
            f_b = next(features) if e["kind"] == "pair" else None
            rows.append(
                {"example_id": e["id"], "kind": e["kind"], "f": f, "f_b": f_b, "label": e["label"]}
            )
        candidate.update(_cv(model["output_type"], candidate["rubric"], active["labels"], rows))
        candidate["questions"] = len(candidate["rubric"])
        candidate["new_questions"] = [
            q["prompt"] for q in candidate["rubric"] if current.get(q["id"]) != q
        ]
    scored = [c for c in candidates if c["cv_log_loss"] is not None]
    if not scored:
        raise service.Conflict("Add examples of more than one label before improving")
    baseline = next((c for c in scored if c["name"] == "current"), None)
    winner = min(scored, key=lambda c: (c["cv_log_loss"], c["questions"]))
    if baseline is not None and winner["cv_log_loss"] > baseline["cv_log_loss"] - TIE:
        winner = baseline  # Only switch for a real improvement.

    await _progress(job_id, "fitting", "Fitting the best criteria and checking held-out examples…")
    draft = await service.ensure_draft(owner_id, model_id)
    await service.update_draft(
        owner_id,
        model_id,
        {"rubric": winner["rubric"], "seed_example_ids": draft["seed_example_ids"]},
    )
    for _ in range(200):
        graded = await service.grade_pending(owner_id, model_id, service.GRADE_BATCH)
        if graded["failed"]:
            raise providers.ProviderError("; ".join(graded["errors"]) or "Grading failed")
        if not graded["remaining"]:
            break
    fitted = await service.fit(owner_id, model_id, train_on="train", calibrate=True)
    return {
        "base_version": active["number"],
        "winner": winner["name"],
        "changed": winner["name"] != "current",
        "candidates": [
            {
                k: c[k]
                for k in (
                    "name",
                    "title",
                    "rationale",
                    "questions",
                    "new_questions",
                    "rubric",
                    "cv_log_loss",
                    "cv_accuracy",
                    "rows",
                )
            }
            for c in candidates
        ],
        "gate": fitted["gate"],
        "held_out": {k: fitted["metrics"]["eval"][k] for k in ("n", "accuracy", "log_loss")},
    }
