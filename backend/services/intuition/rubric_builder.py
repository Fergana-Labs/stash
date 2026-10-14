"""Rubric Builder: refine an eval's criteria pass by pass until the gains run out.

Each pass:
1. Evaluate. Cross-validate the current rubric on the labeled calibration
   examples and keep the out-of-fold mistakes: false positives and negatives
   per label, with the reviewers' notes.
2. Calibrate. Bring in the other signals that disagree with the judge:
   production calls whose human, outcome or downstream feedback overturned
   the decision, and claims the Agent Judge found contradicted when it checked
   the environment.
3. Refine. An analysis model looks across those gaps and proposes a few
   focused edits: add a missing criterion, tighten vague wording, fix what
   causes false positives or negatives, or point the judge at the evidence it
   should check.
4. Iterate. The edited rubric is graded (unchanged questions hit the answer
   cache) and kept only when cross-validated log loss improves; the loop stops
   after PATIENCE passes without a gain.

Held-out examples are never used to choose, so the regression gate at the end
still measures the result honestly, and the per-pass curve shows where the
gains plateaued. The result is a new draft version: applying it is a promotion
like any other.
"""

from __future__ import annotations

import json
import logging
import math
import random
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from ...database import get_pool
from .. import llm
from . import head as heads
from . import improve, providers, service
from .spec import MAX_QUESTIONS, classes, feature_names

log = logging.getLogger(__name__)

MAX_PASSES = 5
PATIENCE = 2
MAX_ERRORS_SHOWN = 12
MAX_DISAGREEMENTS = 10
ITEM_CHARS = 1_200


async def start(owner_id: UUID, model_id: UUID) -> dict:
    model = await service._model(owner_id, model_id)
    active = await service._load_version(model["active_version_id"])
    if active is None or active["head_stale"] or not active["rubric"]:
        raise service.Conflict("Save the eval first; refining starts from its saved criteria")
    await improve._expire(model_id)
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT 1 FROM intuition_models WHERE id = $1 FOR UPDATE", model_id)
        if await conn.fetchval(
            "SELECT 1 FROM intuition_jobs WHERE model_id = $1 AND status IN ('queued', 'running')",
            model_id,
        ):
            raise service.Conflict("An improvement is already running for this eval")
        job = await conn.fetchrow(
            f"""INSERT INTO intuition_jobs (model_id, kind, progress, lease_until)
               VALUES ($1, 'refine', $2, now() + interval '{improve.LEASE}') RETURNING *""",
            model_id,
            {"stage": "queued", "message": "Waiting to start…", "curve": []},
        )
    from ...tasks import intuitions as tasks

    tasks.refine.delay(str(job["id"]))
    return dict(job)


async def latest(owner_id: UUID, model_id: UUID) -> dict | None:
    await service._model(owner_id, model_id)
    await improve._expire(model_id)
    row = await get_pool().fetchrow(
        "SELECT * FROM intuition_jobs WHERE model_id = $1 AND kind = 'refine' ORDER BY created_at DESC LIMIT 1",
        model_id,
    )
    return dict(row) if row else None


async def _progress(job_id: UUID, stage: str, message: str, curve: list[dict]) -> None:
    await get_pool().execute(
        f"""UPDATE intuition_jobs SET progress = $2, lease_until = now() + interval '{improve.LEASE}'
            WHERE id = $1""",
        job_id,
        {"stage": stage, "message": message, "curve": curve},
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
        result = await refine(job_id, row["owner_user_id"], row["model_id"])
    except Exception as exc:
        log.exception("Rubric refinement %s failed", job_id)
        message = str(exc) if isinstance(exc, ValueError | providers.ProviderError) else ""
        await get_pool().execute(
            "UPDATE intuition_jobs SET status = 'failed', finished_at = now(), error = $2 WHERE id = $1",
            job_id,
            (message or "The refinement failed; try again")[:500],
        )
        return
    await get_pool().execute(
        """UPDATE intuition_jobs SET status = 'succeeded', finished_at = now(), result = $2,
                  progress = progress || '{"stage": "done"}'::jsonb
            WHERE id = $1""",
        job_id,
        result,
    )


# ── Evaluate ─────────────────────────────────────────────────────────────


def out_of_fold(output_type: str, rubric: list[dict], labels: list[dict], rows: list[dict]) -> dict:
    """Cross-validated predictions for every row, and the scores they add up to."""
    names, cls = feature_names(rubric), classes(output_type, labels)
    order = sorted(rows, key=lambda r: r["example_id"])
    folds = min(improve.FOLDS, len(order))
    predictions = []
    for k in range(folds):
        train = [r for i, r in enumerate(order) if i % folds != k]
        test = [r for i, r in enumerate(order) if i % folds == k]
        if output_type == "choice" and len({r["label"] for r in train}) < 2:
            continue
        head = heads.fit(output_type, names, cls, train, service.DEFAULT_L2)
        for r in test:
            p, predicted = heads.row_probability(head, output_type, r)
            predictions.append({"row": r, "p": p, "predicted": predicted})
    if not predictions:
        return {"cv_log_loss": None, "cv_accuracy": None, "macro_f1": None, "predictions": []}
    truth = [x["row"]["label"] for x in predictions]
    guessed = [x["predicted"] for x in predictions]
    labels_seen = cls if output_type == "choice" else sorted(set(truth) | set(guessed))
    return {
        "cv_log_loss": sum(-math.log(max(x["p"], 1e-9)) for x in predictions) / len(predictions),
        "cv_accuracy": sum(t == g for t, g in zip(truth, guessed)) / len(predictions),
        "macro_f1": heads.classification(truth, guessed, labels_seen)["macro_f1"],
        "predictions": predictions,
    }


async def _rows(model_id: UUID, version: dict, examples: list[dict], items: list) -> list[dict]:
    features = iter(await service._features(model_id, version, items, grade_missing=False))
    rows = []
    for e in examples:
        f = next(features)
        f_b = next(features) if e["kind"] == "pair" else None
        rows.append(
            {"example_id": e["id"], "kind": e["kind"], "f": f, "f_b": f_b, "label": e["label"]}
        )
    return rows


def _clip(item) -> str:
    text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=str)
    return text if len(text) <= ITEM_CHARS else text[: ITEM_CHARS - 1] + "…"


def mistakes(scored: dict, examples: list[dict]) -> list[dict]:
    """Out-of-fold errors, the most confidently wrong first."""
    by_id = {e["id"]: e for e in examples}
    wrong = [x for x in scored["predictions"] if x["predicted"] != x["row"]["label"]]
    wrong.sort(key=lambda x: x["p"])
    return [
        {
            "label": x["row"]["label"],
            "predicted": x["predicted"],
            "note": by_id[x["row"]["example_id"]].get("note") or "",
            "item": _clip(by_id[x["row"]["example_id"]]["item"]),
        }
        for x in wrong[:MAX_ERRORS_SHOWN]
    ]


# ── Calibrate ────────────────────────────────────────────────────────────


async def disagreements(model_id: UUID) -> list[dict]:
    """Production calls whose feedback overturned the judge's decision."""
    rows = await get_pool().fetch(
        """SELECT DISTINCT ON (p.id) p.input, p.output, f.label, f.source, f.note
           FROM intuition_feedback f JOIN intuition_predictions p ON p.id = f.prediction_id
           WHERE f.model_id = $1 AND f.label IS NOT NULL
           ORDER BY p.id, f.created_at DESC""",
        model_id,
    )
    out = []
    for r in rows:
        predicted = (r["output"] or {}).get("label") or (r["output"] or {}).get("winner")
        if predicted is not None and predicted != r["label"]:
            out.append(
                {
                    "source": r["source"],
                    "label": r["label"],
                    "predicted": predicted,
                    "note": r["note"],
                    "item": _clip(r["input"]),
                }
            )
    return out[:MAX_DISAGREEMENTS]


async def environment_checks(model_id: UUID) -> list[str]:
    """Claims the Agent Judge found contradicted on this eval's items."""
    rows = await get_pool().fetch(
        "SELECT report FROM agent_judge_reports WHERE model_id = $1 AND status = 'done' ORDER BY created_at DESC LIMIT 30",
        model_id,
    )
    found = []
    for r in rows:
        for claim in (r["report"] or {}).get("claims", []):
            if claim.get("status") == "contradicted":
                found.append(f"{claim['text']} (step {claim.get('step_idx')})")
    return found[:MAX_DISAGREEMENTS]


# ── Refine ───────────────────────────────────────────────────────────────


class Edit(BaseModel):
    kind: Literal[
        "add_criterion",
        "tighten_wording",
        "fix_false_positives",
        "fix_false_negatives",
        "point_to_evidence",
        "remove",
    ]
    question_id: str = Field(
        description="The question edited or removed; the new question's id for add_criterion"
    )
    rationale: str


class Proposal(BaseModel):
    edits: list[Edit] = Field(min_length=1, max_length=3)
    questions: list[service._QuestionDraft] = Field(
        description="The full rubric after the edits, in order"
    )


SYSTEM = (
    "You refine the rubric of an evaluation judge. A judge model answers each rubric question about an item; "
    "a small logistic model learns how much each answer matters for the user's labels. You see the gaps: "
    "cross-validated mistakes on labeled examples, production calls where people or outcomes overturned the "
    "judge, and agent claims that turned out false when checked against the environment.\n\n"
    "Find the pattern behind the gaps and make at most three focused edits: add a criterion the rubric is "
    "missing, tighten a vague question so it separates the cases it now confuses, fix the wording that causes "
    "false positives or false negatives, or point a question at the evidence the judge should check (for example "
    "the tool results rather than the agent's own summary). Keep every question that is working unchanged, "
    "word for word, with its id, so its cached answers are reused.\n\n" + service.QUESTION_FORMAT
)


async def propose(
    version: dict,
    errors: list[dict],
    production: list[dict],
    contradicted: list[str],
    history: list[dict],
) -> Proposal:
    tried = (
        "\n".join(
            f"- pass {h['pass']}: {', '.join(e['kind'] + ' ' + e['question_id'] for e in h.get('edits', []))} → {'kept' if h.get('accepted') else 'rejected'}"
            for h in history
            if h.get("edits")
        )
        or "none"
    )
    prompt = (
        f"WHAT THE EVAL JUDGES:\n{version['description']}\n\n"
        f"LABELS: {json.dumps(version['labels'], ensure_ascii=False)}\n\n"
        f"CURRENT RUBRIC:\n{json.dumps(version['rubric'], ensure_ascii=False)}\n\n"
        f"CROSS-VALIDATED MISTAKES (true label, predicted, reviewer note, item):\n"
        + ("\n".join(json.dumps(e, ensure_ascii=False) for e in errors) or "none")
        + "\n\nPRODUCTION DISAGREEMENTS (feedback source, right label, judge said, note, item):\n"
        + ("\n".join(json.dumps(d, ensure_ascii=False) for d in production) or "none")
        + "\n\nCLAIMS CONTRADICTED BY ENVIRONMENT CHECKS:\n"
        + ("\n".join(f"- {c}" for c in contradicted) or "none")
        + f"\n\nEDITS ALREADY TRIED:\n{tried}\n\nPropose the next edits and return the full rubric."
    )
    return await llm.complete_structured(
        prompt=prompt,
        system=SYSTEM,
        output_model=Proposal,
        tier=llm.ModelTier.QUALITY,
        max_tokens=4000,
    )


def apply(current: list[dict], proposal: Proposal) -> list[dict]:
    """The proposed rubric, keeping unchanged questions identical so their answers stay cached.
    Composed and probe questions are signals, not judge questions: they are always kept."""
    signals = [q for q in current if q["type"] in ("eval", "probe")]
    by_id = {q["id"]: q for q in current}
    taken = {q["id"] for q in signals}
    out = []
    for draft in proposal.questions:
        q = service._question(draft, set(taken))
        old = by_id.get(draft.id)
        if (
            old is not None
            and old["type"] not in ("eval", "probe")
            and old["prompt"] == q["prompt"]
            and old["type"] == q["type"]
        ):
            q = old
        taken.add(q["id"])
        out.append(q)
    return (out + signals)[:MAX_QUESTIONS]


def better(candidate: dict, best: dict) -> bool:
    if candidate["cv_log_loss"] is None:
        return False
    return (
        best["cv_log_loss"] is None or candidate["cv_log_loss"] < best["cv_log_loss"] - improve.TIE
    )


def point(n: int, scored: dict, rubric: list[dict], edits: list[dict], accepted: bool) -> dict:
    return {
        "pass": n,
        "cv_accuracy": scored["cv_accuracy"],
        "cv_log_loss": scored["cv_log_loss"],
        "macro_f1": scored["macro_f1"],
        "questions": len(rubric),
        "edits": edits,
        "accepted": accepted,
    }


async def refine(job_id: UUID, owner_id: UUID, model_id: UUID) -> dict:
    model = await service._model(owner_id, model_id)
    active = await service._load_version(model["active_version_id"])
    if active is None or active["head_stale"]:
        raise service.Conflict("Save the eval first; refining starts from its saved criteria")
    examples = [
        e for e in await service._examples(model_id)
        if e["label"] is not None and not e["needs_review"] and e["split"] == "train"
    ]  # fmt: skip
    if len(examples) > improve.MAX_ITEMS:
        examples = random.Random(0).sample(examples, improve.MAX_ITEMS)
    if len(examples) < improve.MIN_ROWS:
        raise service.Conflict(
            f"Add at least {improve.MIN_ROWS} labeled calibration examples before refining"
        )
    items = [i for e in examples for i in service._items_of(e)]
    production = await disagreements(model_id)
    contradicted = await environment_checks(model_id)

    best_rubric = active["rubric"]
    best = out_of_fold(
        model["output_type"],
        best_rubric,
        active["labels"],
        await _rows(model_id, active, examples, items),
    )
    if best["cv_log_loss"] is None:
        raise service.Conflict("Add examples of more than one label before refining")
    curve = [point(0, best, best_rubric, [], True)]
    stale = 0
    for n in range(1, MAX_PASSES + 1):
        if stale >= PATIENCE:
            break
        await _progress(
            job_id, "refining", f"Pass {n}: analyzing mistakes and proposing edits…", curve
        )
        base = {**active, "rubric": best_rubric}
        proposal = await propose(base, mistakes(best, examples), production, contradicted, curve)
        rubric = apply(best_rubric, proposal)
        edits = [e.model_dump() for e in proposal.edits]
        if rubric == best_rubric:
            curve.append(
                {**point(n, best, rubric, edits, False), "note": "No change to the rubric"}
            )
            stale += 1
            continue
        version = {**active, "rubric": rubric}
        await _progress(job_id, "grading", f"Pass {n}: grading the edited criteria…", curve)
        await improve._grade(job_id, model_id, [version], items)
        scored = out_of_fold(
            model["output_type"],
            rubric,
            active["labels"],
            await _rows(model_id, version, examples, items),
        )
        accepted = better(scored, best)
        curve.append(point(n, scored, rubric, edits, accepted))
        if accepted:
            best, best_rubric, stale = scored, rubric, 0
        else:
            stale += 1

    await _progress(
        job_id, "fitting", "Fitting the refined criteria and checking held-out examples…", curve
    )
    changed = best_rubric != active["rubric"]
    fitted = None
    if changed:
        draft = await service.ensure_draft(owner_id, model_id)
        await service.update_draft(
            owner_id,
            model_id,
            {"rubric": best_rubric, "seed_example_ids": draft["seed_example_ids"]},
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
        "changed": changed,
        "passes": len(curve) - 1,
        "curve": curve,
        "rubric": best_rubric,
        "signals": {
            "examples": len(examples),
            "production_disagreements": len(production),
            "contradicted_claims": len(contradicted),
        },
        "gate": fitted["gate"] if fitted else None,
        "held_out": {k: fitted["metrics"]["eval"][k] for k in ("n", "accuracy", "log_loss")}
        if fitted
        else None,
    }
