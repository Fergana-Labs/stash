"""Intuition models: owner-scoped storage, grading, fitting, promotion, serving.

Lifecycle. A model has at most one active version (served) and one draft
(edited). Every edit -- description, labels, rubric, seed examples, judge,
head weights -- lands on the draft. The draft is graded (judge answers are
cached per question context, so only changed questions are re-asked), fit, and
evaluated against the active version on the same held-out examples. Promotion
requires the gate to pass unless the caller explicitly forces it.

Data. Examples belong to the model, not a version, so every version can be
trained and compared on the same collected data. Served predictions are
logged; reviewing one turns it into a 'production' example.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from ...config import settings
from ...database import get_pool
from .. import llm
from . import head as heads
from . import providers
from .spec import (
    MAX_QUESTIONS,
    MAX_SEEDS,
    Question,
    VersionSpec,
    classes,
    feature_names,
    valid_example_labels,
)

DEFAULT_L2 = 0.005
GRADE_BATCH = 12
CV_FOLDS = 4


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    """The request is valid but the model is not in a state that allows it."""


# ── Loading ──────────────────────────────────────────────────────────────

VERSION_COLUMNS = (
    "v.id, v.model_id, v.number, v.status, v.description, v.labels, v.rubric, "
    "v.seed_example_ids, v.seed_snapshot, v.provider, v.provider_model, v.head, v.metrics, v.gate, "
    "v.parent_version_id, v.promoted_at, v.created_at, m.output_type"
)


def _version(row) -> dict | None:
    if row is None:
        return None
    v = dict(row)
    v["seed_example_ids"] = [str(i) for i in v["seed_example_ids"]]
    v["feature_names"] = feature_names(v["rubric"])
    v["classes"] = classes(v["output_type"], v["labels"])
    v["head_stale"] = heads.is_stale(v["head"], v["feature_names"], v["classes"])
    return v


async def _model(owner_id: UUID, model_id: UUID) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM intuition_models WHERE id = $1 AND owner_user_id = $2", model_id, owner_id
    )
    if row is None:
        raise NotFound("Intuition model not found")
    return dict(row)


async def _load_version(version_id: UUID | None) -> dict | None:
    if version_id is None:
        return None
    row = await get_pool().fetchrow(
        f"SELECT {VERSION_COLUMNS} FROM intuition_versions v "
        "JOIN intuition_models m ON m.id = v.model_id WHERE v.id = $1",
        version_id,
    )
    return _version(row)


async def _examples(model_id: UUID, ids: list[str] | None = None) -> list[dict]:
    if ids is None:
        rows = await get_pool().fetch(
            "SELECT * FROM intuition_examples WHERE model_id = $1 ORDER BY created_at, id", model_id
        )
    else:
        rows = await get_pool().fetch(
            "SELECT * FROM intuition_examples WHERE model_id = $1 AND id = ANY($2::uuid[])",
            model_id,
            [UUID(i) for i in ids],
        )
    return [_example(r) for r in rows]


def _example(row) -> dict:
    e = dict(row)
    e["id"] = str(e["id"])
    return e


async def _seeds(version: dict) -> list[dict]:
    if version.get("seed_snapshot") is not None and version["status"] != "draft":
        return version["seed_snapshot"]
    by_id = {e["id"]: e for e in await _examples(version["model_id"], version["seed_example_ids"])}
    return [by_id[i] for i in version["seed_example_ids"] if i in by_id]


# ── Models and drafts ────────────────────────────────────────────────────


def _validate(output_type: str, description: str, labels: list, rubric: list) -> dict:
    spec = VersionSpec.model_validate(
        {"output_type": output_type, "description": description, "labels": labels, "rubric": rubric}
    )
    return spec.model_dump(mode="json")


async def list_models(owner_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT m.id, m.name, m.output_type, m.active_version_id, m.draft_version_id,
                  m.created_at, m.updated_at,
                  av.number AS active_number, av.metrics AS active_metrics,
                  av.description AS active_description, dv.description AS draft_description,
                  (SELECT count(*) FROM intuition_examples e WHERE e.model_id = m.id) AS examples,
                  (SELECT count(*) FROM intuition_predictions p
                    WHERE p.model_id = m.id AND p.status = 'unreviewed') AS inbox
             FROM intuition_models m
             LEFT JOIN intuition_versions av ON av.id = m.active_version_id
             LEFT JOIN intuition_versions dv ON dv.id = m.draft_version_id
            WHERE m.owner_user_id = $1
            ORDER BY m.updated_at DESC""",
        owner_id,
    )
    return [dict(r) for r in rows]


async def create_model(
    owner_id: UUID,
    *,
    name: str,
    output_type: str,
    description: str,
    labels: list,
    rubric: list,
) -> dict:
    spec = _validate(output_type, description, labels, rubric)
    provider, model_name = "jev", settings.JEV_MODEL
    async with get_pool().acquire() as conn, conn.transaction():
        model_id = await conn.fetchval(
            "INSERT INTO intuition_models (owner_user_id, name, output_type) VALUES ($1, $2, $3) RETURNING id",
            owner_id,
            name,
            output_type,
        )
        version_id = await conn.fetchval(
            """INSERT INTO intuition_versions
                 (model_id, number, status, description, labels, rubric, provider, provider_model)
               VALUES ($1, 1, 'draft', $2, $3, $4, $5, $6) RETURNING id""",
            model_id,
            spec["description"],
            spec["labels"],
            spec["rubric"],
            provider,
            model_name,
        )
        await conn.execute(
            "UPDATE intuition_models SET draft_version_id = $2 WHERE id = $1", model_id, version_id
        )
    return await get_detail(owner_id, model_id)


async def rename_model(owner_id: UUID, model_id: UUID, name: str) -> dict:
    await _model(owner_id, model_id)
    await get_pool().execute(
        "UPDATE intuition_models SET name = $2, updated_at = now() WHERE id = $1", model_id, name
    )
    return await get_detail(owner_id, model_id)


async def delete_model(owner_id: UUID, model_id: UUID) -> None:
    await _model(owner_id, model_id)
    await get_pool().execute("DELETE FROM intuition_models WHERE id = $1", model_id)


async def get_detail(owner_id: UUID, model_id: UUID) -> dict:
    model = await _model(owner_id, model_id)
    versions = await get_pool().fetch(
        """SELECT id, number, status, provider, provider_model, metrics, gate, promoted_at, created_at,
                  parent_version_id, head IS NOT NULL AS has_head
             FROM intuition_versions WHERE model_id = $1 ORDER BY number DESC""",
        model_id,
    )
    counts = await get_pool().fetchrow(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE label IS NOT NULL AND NOT needs_review) AS labeled,
                  count(*) FILTER (WHERE needs_review) AS needs_review,
                  count(*) FILTER (WHERE split = 'eval') AS eval,
                  (SELECT count(*) FROM intuition_predictions p
                    WHERE p.model_id = $1 AND p.status = 'unreviewed') AS inbox
             FROM intuition_examples WHERE model_id = $1""",
        model_id,
    )
    active = await _load_version(model["active_version_id"])
    draft = await _load_version(model["draft_version_id"])
    # `ungraded`: items the draft (or, without one, the active version) still needs
    # before fitting. `ungraded_total` also counts active-version answers the gate needs.
    primary = await _pending_jobs(model, [draft or active] if (draft or active) else [])
    total = await _pending_jobs(model, [v for v in (draft, active) if v])
    return {
        "model": model,
        "active": active,
        "draft": draft,
        "versions": [dict(v) for v in versions],
        "counts": {**dict(counts), "ungraded": len(primary), "ungraded_total": len(total)},
        "judge": providers.status(),
    }


async def ensure_draft(owner_id: UUID, model_id: UUID) -> dict:
    model = await _model(owner_id, model_id)
    if model["draft_version_id"]:
        return await _load_version(model["draft_version_id"])
    async with get_pool().acquire() as conn, conn.transaction():
        locked = await conn.fetchrow(
            "SELECT draft_version_id, active_version_id FROM intuition_models WHERE id = $1 FOR UPDATE",
            model_id,
        )
        if locked["draft_version_id"]:
            return await _load_version(locked["draft_version_id"])
        number = await conn.fetchval(
            "SELECT coalesce(max(number), 0) + 1 FROM intuition_versions WHERE model_id = $1",
            model_id,
        )
        draft_id = await conn.fetchval(
            """INSERT INTO intuition_versions
                 (model_id, number, status, description, labels, rubric, seed_example_ids,
                  provider, provider_model, head, parent_version_id)
               SELECT model_id, $1, 'draft', description, labels, rubric, seed_example_ids,
                      provider, provider_model, head, id
                 FROM intuition_versions WHERE id = $2
               RETURNING id""",
            number,
            locked["active_version_id"],
        )
        await conn.execute(
            "UPDATE intuition_models SET draft_version_id = $2, updated_at = now() WHERE id = $1",
            model_id,
            draft_id,
        )
    return await _load_version(draft_id)


async def update_draft(owner_id: UUID, model_id: UUID, changes: dict) -> dict:
    """Edit any of description, labels, rubric, seed_example_ids on the draft."""
    model = await _model(owner_id, model_id)
    draft = await ensure_draft(owner_id, model_id)
    merged = {k: changes.get(k, draft[k]) for k in ("description", "labels", "rubric")}
    spec = _validate(
        model["output_type"], merged["description"], merged["labels"], merged["rubric"]
    )
    seeds = changes.get("seed_example_ids", draft["seed_example_ids"])
    if len(seeds) > MAX_SEEDS or len(set(seeds)) != len(seeds):
        raise ValueError(f"Choose at most {MAX_SEEDS} distinct seed examples")
    found = await _examples(model_id, seeds)
    if len(found) != len(seeds) or any(e["label"] is None or e["needs_review"] for e in found):
        raise ValueError("Seed examples must be labeled, reviewed examples of this model")
    await get_pool().execute(
        """UPDATE intuition_versions
              SET description = $2, labels = $3, rubric = $4, seed_example_ids = $5::uuid[],
                  metrics = NULL, gate = NULL
            WHERE id = $1""",
        draft["id"],
        spec["description"],
        spec["labels"],
        spec["rubric"],
        [UUID(s) for s in seeds],
    )
    await _touch(model_id)
    return await get_detail(owner_id, model_id)


async def discard_draft(owner_id: UUID, model_id: UUID) -> dict:
    model = await _model(owner_id, model_id)
    if model["draft_version_id"] is None:
        raise Conflict("There is no draft to discard")
    if model["active_version_id"] is None:
        raise Conflict("The first version cannot be discarded; delete the model instead")
    await get_pool().execute(
        "DELETE FROM intuition_versions WHERE id = $1", model["draft_version_id"]
    )
    return await get_detail(owner_id, model_id)


async def _touch(model_id: UUID) -> None:
    await get_pool().execute(
        "UPDATE intuition_models SET updated_at = now() WHERE id = $1", model_id
    )


# ── Examples ─────────────────────────────────────────────────────────────


def _split_for(item, item_b) -> str:
    """Deterministic ~25% held-out split so re-imports land in the same split."""
    digest = hashlib.sha256(json.dumps([item, item_b], sort_keys=True).encode()).digest()
    return "eval" if digest[0] % 4 == 0 else "train"


def _check_label(
    model: dict, labels: list[dict], kind: str, label: str | None, needs_review: bool
) -> None:
    allowed = valid_example_labels(model["output_type"], kind, labels)
    if label is None:
        if not needs_review:
            raise ValueError("Unlabeled examples must be marked needs_review")
        return
    if label not in allowed:
        raise ValueError(f"Label must be one of {', '.join(allowed)}")


async def _current_labels(model: dict) -> list[dict]:
    version = await _load_version(model["draft_version_id"] or model["active_version_id"])
    return version["labels"]


async def add_examples(
    owner_id: UUID, model_id: UUID, examples: list[dict], source: str
) -> list[dict]:
    model = await _model(owner_id, model_id)
    labels = await _current_labels(model)
    rows = []
    for e in examples:
        kind = "pair" if e.get("item_b") is not None else "item"
        needs_review = bool(e.get("needs_review", False))
        _check_label(model, labels, kind, e.get("label"), needs_review)
        rows.append(
            (
                model_id,
                kind,
                e["item"],
                e.get("item_b"),
                e.get("label"),
                e.get("source", source),
                e.get("split") or _split_for(e["item"], e.get("item_b")),
                needs_review,
                e.get("note", ""),
            )
        )
    async with get_pool().acquire() as conn, conn.transaction():
        created = [
            await conn.fetchrow(
                """INSERT INTO intuition_examples
                     (model_id, kind, item, item_b, label, source, split, needs_review, note)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *""",
                *row,
            )
            for row in rows
        ]
    await _invalidate_draft(model_id)
    await _touch(model_id)
    return [_example(r) for r in created]


async def list_examples(owner_id: UUID, model_id: UUID) -> list[dict]:
    await _model(owner_id, model_id)
    return await _examples(model_id)


async def update_example(owner_id: UUID, model_id: UUID, example_id: UUID, changes: dict) -> dict:
    model = await _model(owner_id, model_id)
    row = await get_pool().fetchrow(
        "SELECT * FROM intuition_examples WHERE id = $1 AND model_id = $2", example_id, model_id
    )
    if row is None:
        raise NotFound("Example not found")
    merged = {**dict(row), **changes}
    _check_label(
        model, await _current_labels(model), merged["kind"], merged["label"], merged["needs_review"]
    )
    updated = await get_pool().fetchrow(
        """UPDATE intuition_examples SET label = $3, split = $4, needs_review = $5, note = $6
            WHERE id = $1 AND model_id = $2 RETURNING *""",
        example_id,
        model_id,
        merged["label"],
        merged["split"],
        merged["needs_review"],
        merged["note"],
    )
    await _invalidate_draft(model_id, example_id)
    await _touch(model_id)
    return _example(updated)


async def delete_example(owner_id: UUID, model_id: UUID, example_id: UUID) -> None:
    await _model(owner_id, model_id)
    in_use = await get_pool().fetchval(
        "SELECT number FROM intuition_versions WHERE model_id = $1 AND $2 = ANY(seed_example_ids) "
        "AND status <> 'retired' LIMIT 1",
        model_id,
        example_id,
    )
    if in_use is not None:
        raise Conflict(
            f"This example is a seed of version {in_use}; remove it from the seeds first"
        )
    deleted = await get_pool().execute(
        "DELETE FROM intuition_examples WHERE id = $1 AND model_id = $2", example_id, model_id
    )
    if deleted == "DELETE 0":
        raise NotFound("Example not found")
    await _invalidate_draft(model_id)


async def _invalidate_draft(model_id: UUID, changed_example: UUID | None = None) -> None:
    # Label changes invalidate the gate. Changing a seed also changes judge inputs,
    # so an existing draft head must be refitted before it can serve predictions.
    await get_pool().execute(
        """UPDATE intuition_versions SET metrics = NULL, gate = NULL,
        head = CASE WHEN $2::uuid = ANY(seed_example_ids) THEN NULL ELSE head END
        WHERE model_id = $1 AND status = 'draft'""",
        model_id,
        changed_example,
    )


# ── Grading (judge answers -> cached features) ───────────────────────────


def _items_of(example: dict) -> list:
    return [example["item"]] + ([example["item_b"]] if example["kind"] == "pair" else [])


async def _contexts(version: dict) -> list[tuple[dict, dict]]:
    seeds = await _seeds(version)
    return [(q, providers.question_context(version, q, seeds)) for q in version["rubric"]]


async def _cached(model_id: UUID, keys: list[str]) -> dict[str, dict]:
    rows = await get_pool().fetch(
        "SELECT grade_key, answer FROM intuition_grades WHERE model_id = $1 AND grade_key = ANY($2::text[])",
        model_id,
        keys,
    )
    return {r["grade_key"]: r["answer"] for r in rows}


async def _pending_jobs(
    model: dict, versions: list[dict], items: list | None = None
) -> list[tuple]:
    """(version, missing questions, seeds, item) for every item lacking an answer."""
    if items is None:
        items = [i for e in await _examples(model["id"]) for i in _items_of(e)]
    jobs, seen = [], set()
    for version in versions:
        contexts = await _contexts(version)
        seeds = await _seeds(version)
        keys = {
            (json.dumps(item, sort_keys=True), q["id"]): providers.grade_key(ctx, item)
            for item in items
            for q, ctx in contexts
        }
        cached = await _cached(model["id"], list(set(keys.values())))
        for item in items:
            marker = json.dumps(item, sort_keys=True)
            missing = [q for q, _ in contexts if keys[(marker, q["id"])] not in cached]
            dedupe = (tuple(keys[(marker, q["id"])] for q in missing), marker)
            if missing and dedupe not in seen:
                seen.add(dedupe)
                jobs.append((version, missing, seeds, item))
    return jobs


async def _store_answers(
    model_id: UUID, version: dict, seeds: list[dict], item, answers: dict
) -> None:
    rows = [
        (
            model_id,
            providers.grade_key(providers.question_context(version, q, seeds), item),
            answers[q["id"]],
            version["provider"],
            version["provider_model"],
        )
        for q in version["rubric"]
        if q["id"] in answers
    ]
    await get_pool().executemany(
        """INSERT INTO intuition_grades (model_id, grade_key, answer, provider, provider_model)
           VALUES ($1, $2, $3, $4, $5) ON CONFLICT (model_id, grade_key) DO NOTHING""",
        rows,
    )


async def grade_pending(owner_id: UUID, model_id: UUID, limit: int = GRADE_BATCH) -> dict:
    """Grade up to `limit` items for the draft and the active version; call until remaining is 0."""
    model = await _model(owner_id, model_id)
    versions = [
        v
        for v in (
            await _load_version(model["draft_version_id"]),
            await _load_version(model["active_version_id"]),
        )
        if v
    ]
    jobs = await _pending_jobs(model, versions)
    batch = jobs[:limit]
    results = await providers.grade_many(batch)
    errors = []
    for (version, _questions, seeds, item), result in zip(batch, results):
        if isinstance(result, providers.ProviderError):
            errors.append(str(result))
        else:
            await _store_answers(model_id, version, seeds, item, result)
    return {
        "graded": len(batch) - len(errors),
        "failed": len(errors),
        "remaining": len(jobs) - len(batch) + len(errors),
        "errors": sorted(set(errors))[:3],
    }


async def _features(
    model_id: UUID, version: dict, items: list, *, grade_missing: bool
) -> list[list[float] | None]:
    contexts = await _contexts(version)
    if grade_missing:
        jobs = await _pending_jobs({"id": model_id}, [version], items)
        for (v, _q, seeds, item), result in zip(jobs, await providers.grade_many(jobs)):
            if isinstance(result, providers.ProviderError):
                raise result
            await _store_answers(model_id, v, seeds, item, result)
    keys = [[providers.grade_key(ctx, item) for _, ctx in contexts] for item in items]
    cached = await _cached(model_id, [k for row in keys for k in row])
    features = []
    for row in keys:
        if all(k in cached for k in row):
            answers = {q["id"]: cached[k] for (q, _), k in zip(contexts, row)}
            features.append(heads.answers_to_features(version["rubric"], answers))
        else:
            features.append(None)
    return features


async def _answers(model_id: UUID, version: dict, item) -> dict:
    contexts = await _contexts(version)
    cached = await _cached(model_id, [providers.grade_key(ctx, item) for _, ctx in contexts])
    return {q["id"]: cached[providers.grade_key(ctx, item)]["probabilities"] for q, ctx in contexts}


# ── Fitting and evaluation ───────────────────────────────────────────────


async def _rows(model: dict, version: dict) -> tuple[list[dict], int]:
    """Labeled, reviewed examples with features under `version`; also count ungraded ones."""
    examples = [
        e for e in await _examples(model["id"]) if e["label"] is not None and not e["needs_review"]
    ]
    items = [i for e in examples for i in _items_of(e)]
    features = iter(await _features(model["id"], version, items, grade_missing=False))
    rows, missing = [], 0
    seeds = set(version["seed_example_ids"])
    for e in examples:
        f = next(features)
        f_b = next(features) if e["kind"] == "pair" else None
        if f is None or (e["kind"] == "pair" and f_b is None):
            missing += 1
            continue
        rows.append(
            {
                "example_id": e["id"],
                "kind": e["kind"],
                "f": f,
                "f_b": f_b,
                "label": e["label"],
                "split": e["split"],
                "source": e["source"],
                "seed": e["id"] in seeds,
            }
        )
    return rows, missing


def _held_out(rows: list[dict]) -> list[dict]:
    # Seeds are shown to the judge, so they cannot measure generalization.
    return [r for r in rows if r["split"] == "eval" and not r["seed"]]


def _oof_temperature(output_type, names, cls, train, l2) -> float:
    """Calibrate on out-of-fold predictions so held-out metrics stay honest."""
    if len(train) < 2 * CV_FOLDS:
        return 1.0
    order = sorted(train, key=lambda r: r["example_id"])
    oof = []
    for k in range(CV_FOLDS):
        fold_train = [r for i, r in enumerate(order) if i % CV_FOLDS != k]
        fold_test = [r for i, r in enumerate(order) if i % CV_FOLDS == k]
        if output_type == "choice" and len({r["label"] for r in fold_train}) < 2:
            return 1.0
        fold_head = heads.fit(output_type, names, cls, fold_train, l2)
        oof.extend({**r, "_head": fold_head} for r in fold_test)

    def nll(log_t):
        t = math.exp(log_t)
        return -sum(
            math.log(
                max(
                    heads.row_probability({**r["_head"], "temperature": t}, output_type, r)[0], 1e-9
                )
            )
            for r in oof
        ) / len(oof)

    from scipy.optimize import minimize_scalar

    result = minimize_scalar(nll, bounds=(math.log(0.05), math.log(20)), method="bounded")
    return round(math.exp(result.x), 4)


async def _refresh(model: dict, draft: dict, head: dict, fit_options: dict | None) -> dict:
    rows, missing = await _rows(model, draft)
    held = _held_out(rows)
    metrics = {
        "train": heads.evaluate(
            head, model["output_type"], [r for r in rows if r["split"] == "train"]
        ),
        "eval": heads.evaluate(head, model["output_type"], held),
        "ungraded_examples": missing,
        "fit_options": fit_options,
    }
    active = await _load_version(model["active_version_id"])
    incumbent = None
    if active and not active["head_stale"]:
        active_rows, _ = await _rows(model, active)
        held_ids = {r["example_id"] for r in held}
        shared = [r for r in active_rows if r["example_id"] in held_ids]
        incumbent = heads.evaluate(active["head"], model["output_type"], shared)
        incumbent["missing"] = len(held_ids) - len(shared)
    gate = heads.gate(metrics["eval"], incumbent)
    if fit_options and fit_options.get("train_on") == "all":
        gate["passed"] = False
        gate["checks"].append(
            {
                "name": "held_out_independent",
                "passed": False,
                "detail": "This head was fitted on all examples, including evaluation data.",
            }
        )
    if incumbent is not None and incumbent["missing"]:
        gate["checks"].append(
            {
                "name": "incumbent_graded",
                "passed": False,
                "detail": f"{incumbent['missing']} held-out examples are not graded under the active version",
            }
        )
        gate["passed"] = False
    gate["incumbent"] = (
        None
        if incumbent is None
        else {k: incumbent[k] for k in ("n", "accuracy", "log_loss", "ece")}
    )
    gate["active_version"] = active["number"] if active else None
    await get_pool().execute(
        "UPDATE intuition_versions SET head = $2, metrics = $3, gate = $4 WHERE id = $1",
        draft["id"],
        head,
        metrics,
        gate,
    )
    await _touch(model["id"])
    return {"head": head, "metrics": metrics, "gate": gate}


async def fit(
    owner_id: UUID,
    model_id: UUID,
    *,
    l2: float = DEFAULT_L2,
    train_on: str = "train",
    sources: list[str] | None = None,
    calibrate: bool = True,
) -> dict:
    """Refit the draft head on cached features; never calls the judge."""
    model = await _model(owner_id, model_id)
    draft = await ensure_draft(owner_id, model_id)
    if not draft["rubric"]:
        raise Conflict("Add rubric questions before fitting; the head learns from their answers")
    rows, missing = await _rows(model, draft)
    if missing:
        raise Conflict(
            f"{missing} labeled examples are not graded under the draft yet; grade them first"
        )
    pool = rows if train_on == "all" else [r for r in rows if r["split"] == "train"]
    if sources:
        pool = [r for r in pool if r["source"] in sources]
    if model["output_type"] == "choice" and len({r["label"] for r in pool}) < 2:
        raise Conflict("Fitting needs examples of at least two labels in the selected data")
    if not pool:
        raise Conflict("No labeled examples match the selected training data")
    head = heads.fit(model["output_type"], draft["feature_names"], draft["classes"], pool, l2)
    if calibrate:
        head["temperature"] = _oof_temperature(
            model["output_type"], draft["feature_names"], draft["classes"], pool, l2
        )
    options = {
        "l2": l2,
        "train_on": train_on,
        "sources": sources,
        "calibrate": calibrate,
        "rows": len(pool),
    }
    return await _refresh(model, draft, head, options)


async def set_head(
    owner_id: UUID,
    model_id: UUID,
    weights: list[list[float]],
    bias: list[float],
    temperature: float,
) -> dict:
    """Hand-edit the draft head. Shapes must match the draft's features and classes."""
    model = await _model(owner_id, model_id)
    draft = await ensure_draft(owner_id, model_id)
    n_cls, n_feat = len(draft["classes"]), len(draft["feature_names"])
    if len(weights) != n_cls or any(len(row) != n_feat for row in weights) or len(bias) != n_cls:
        raise ValueError(f"Expected {n_cls} x {n_feat} weights and {n_cls} biases")
    if not all(math.isfinite(v) for v in [*bias, *(v for row in weights for v in row)]):
        raise ValueError("Weights must be finite numbers")
    if not 0.01 <= temperature <= 100:
        raise ValueError("Temperature must be between 0.01 and 100")
    base = (
        draft["head"]
        if not draft["head_stale"]
        else heads.blank(draft["feature_names"], draft["classes"])
    )
    head = {**base, "weights": weights, "bias": bias, "temperature": temperature, "edited": True}
    return await _refresh(model, draft, head, (draft["metrics"] or {}).get("fit_options"))


async def promote(owner_id: UUID, model_id: UUID, *, force: bool = False) -> dict:
    model = await _model(owner_id, model_id)
    draft = await _load_version(model["draft_version_id"])
    if draft is None:
        raise Conflict("There is no draft to promote")
    if draft["head_stale"]:
        raise Conflict("The draft head does not match its rubric and labels; fit it first")
    if draft["gate"] is None:
        raise Conflict("Evaluate the draft (fit or save weights) before promoting")
    if not draft["gate"]["passed"] and not force:
        raise Conflict("The draft fails the promotion gate; review it or promote with force")
    seeds = [
        {k: e[k] for k in ("id", "kind", "item", "item_b", "label")} for e in await _seeds(draft)
    ]
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "UPDATE intuition_versions SET status = 'retired' WHERE model_id = $1 AND status = 'active'",
            model_id,
        )
        await conn.execute(
            """UPDATE intuition_versions SET status = 'active', promoted_at = now(),
                      seed_snapshot = $3, gate = gate || jsonb_build_object('forced', $2::boolean)
                WHERE id = $1""",
            draft["id"],
            force and not draft["gate"]["passed"],
            seeds,
        )
        await conn.execute(
            """UPDATE intuition_models SET active_version_id = $2, draft_version_id = NULL,
                      updated_at = now() WHERE id = $1""",
            model_id,
            draft["id"],
        )
    return await get_detail(owner_id, model_id)


async def rollback(owner_id: UUID, model_id: UUID, version_id: UUID) -> dict:
    await _model(owner_id, model_id)
    target = await _load_version(version_id)
    if target is None or target["model_id"] != model_id or target["status"] != "retired":
        raise NotFound("Only a previously active version of this model can be restored")
    if target["head_stale"]:
        raise Conflict("That version has no usable head")
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "UPDATE intuition_versions SET status = 'retired' WHERE model_id = $1 AND status = 'active'",
            model_id,
        )
        await conn.execute(
            "UPDATE intuition_versions SET status = 'active', promoted_at = now() WHERE id = $1",
            version_id,
        )
        await conn.execute(
            "UPDATE intuition_models SET active_version_id = $2, updated_at = now() WHERE id = $1",
            model_id,
            version_id,
        )
    return await get_detail(owner_id, model_id)


async def version_detail(owner_id: UUID, model_id: UUID, version_id: UUID) -> dict:
    await _model(owner_id, model_id)
    version = await _load_version(version_id)
    if version is None or version["model_id"] != model_id:
        raise NotFound("Version not found")
    return version


# ── Serving ──────────────────────────────────────────────────────────────


async def _serving_version(model: dict, which: str) -> dict:
    version_id = model["draft_version_id"] if which == "draft" else model["active_version_id"]
    version = await _load_version(version_id)
    if version is None:
        raise Conflict(
            f"This model has no {which} version"
            + ("; promote a draft first" if which == "active" else "")
        )
    if version["head_stale"]:
        raise Conflict(f"The {which} version has no fitted head yet")
    return version


async def _log(model_id, version, kind, payload, output, caller) -> str:
    return str(
        await get_pool().fetchval(
            """INSERT INTO intuition_predictions (model_id, version_id, kind, input, output, confidence, caller)
           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            model_id,
            version["id"],
            kind,
            payload,
            output,
            output["confidence"],
            caller,
        )
    )


async def predict(
    owner_id: UUID,
    model_id: UUID,
    item,
    *,
    which: str = "active",
    caller: str = "api",
    log: bool = True,
) -> dict:
    model = await _model(owner_id, model_id)
    version = await _serving_version(model, which)
    (features,) = await _features(model_id, version, [item], grade_missing=True)
    if model["output_type"] == "choice":
        output = heads.predict_choice(version["head"], features)
    else:
        output = heads.predict_preference_item(version["head"], features)
    output["rubric"] = await _answers(model_id, version, item)
    output["version"] = version["number"]
    prediction_id = (
        await _log(model_id, version, "predict", {"item": item}, output, caller) if log else None
    )
    return {"prediction_id": prediction_id, **output}


async def compare_items(
    owner_id: UUID,
    model_id: UUID,
    item_a,
    item_b,
    *,
    which: str = "active",
    caller: str = "api",
    log: bool = True,
) -> dict:
    model = await _model(owner_id, model_id)
    if model["output_type"] != "preference":
        raise Conflict("Pairwise comparison is only available for preference models")
    version = await _serving_version(model, which)
    f_a, f_b = await _features(model_id, version, [item_a, item_b], grade_missing=True)
    output = heads.compare(version["head"], f_a, f_b)
    output["rubric_a"] = await _answers(model_id, version, item_a)
    output["rubric_b"] = await _answers(model_id, version, item_b)
    output["version"] = version["number"]
    prediction_id = (
        await _log(model_id, version, "compare", {"item": item_a, "item_b": item_b}, output, caller)
        if log
        else None
    )
    return {"prediction_id": prediction_id, **output}


# ── Collected data: the review inbox ─────────────────────────────────────


async def list_predictions(
    owner_id: UUID, model_id: UUID, status: str = "unreviewed", limit: int = 100
) -> list[dict]:
    await _model(owner_id, model_id)
    rows = await get_pool().fetch(
        """SELECT p.id, p.kind, p.input, p.output, p.confidence, p.caller, p.status, p.example_id,
                  p.created_at, v.number AS version
             FROM intuition_predictions p JOIN intuition_versions v ON v.id = p.version_id
            WHERE p.model_id = $1 AND ($2 = 'all' OR p.status = $2)
            ORDER BY CASE WHEN p.status = 'unreviewed' THEN p.confidence END ASC NULLS LAST,
                     p.created_at DESC
            LIMIT $3""",
        model_id,
        status,
        limit,
    )
    return [dict(r) for r in rows]


async def review_prediction(
    owner_id: UUID,
    model_id: UUID,
    prediction_id: UUID,
    *,
    label: str | None,
    dismiss: bool,
    note: str,
    source: str,
) -> dict:
    """Turn a served prediction into a labeled example (or dismiss it)."""
    await _model(owner_id, model_id)
    row = await get_pool().fetchrow(
        "SELECT * FROM intuition_predictions WHERE id = $1 AND model_id = $2",
        prediction_id,
        model_id,
    )
    if row is None:
        raise NotFound("Prediction not found")
    if row["status"] != "unreviewed":
        raise Conflict("This prediction was already reviewed")
    if dismiss:
        await get_pool().execute(
            "UPDATE intuition_predictions SET status = 'dismissed' WHERE id = $1", prediction_id
        )
        return {"status": "dismissed", "example": None}
    payload = row["input"]
    note = note or f"From prediction {prediction_id} by {row['caller']}"
    (example,) = await add_examples(
        owner_id,
        model_id,
        [
            {
                "item": payload["item"],
                "item_b": payload.get("item_b"),
                "label": label,
                "note": note,
                "source": "production" if source == "human" else source,
            }
        ],
        source,
    )
    await get_pool().execute(
        "UPDATE intuition_predictions SET status = 'labeled', example_id = $2 WHERE id = $1",
        prediction_id,
        UUID(example["id"]),
    )
    return {"status": "labeled", "example": example}


# ── Assisted improvement (Claude) ────────────────────────────────────────


class _Generated(BaseModel):
    items: list[str] = Field(min_length=1)


def _generated_items(raw: list[str], keys: list[str]) -> list:
    if not keys:
        return raw
    items = []
    for text in raw:
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        if isinstance(parsed, dict) and sorted(parsed) == keys:
            items.append(parsed)
    if not items:
        raise Conflict("Claude did not return items in this model's format; try again")
    return items


async def generate_examples(
    owner_id: UUID, model_id: UUID, count: int, guidance: str
) -> list[dict]:
    """Draft new items for the user to label; suggested labels come from the current head."""
    model = await _model(owner_id, model_id)
    version = await _load_version(model["draft_version_id"] or model["active_version_id"])
    existing = [e for e in await _examples(model_id) if e["kind"] == "item"]
    sample = random.Random(len(existing)).sample(existing, min(8, len(existing)))
    # Object-shaped items (e.g. {customer, reply}) are generated as JSON strings
    # with the same keys, so generated items look like real ones.
    keys = sorted({k for e in sample if isinstance(e["item"], dict) for k in e["item"]})
    shape = (
        f"Write {count} new items. Each item is a JSON object string with exactly these keys: "
        f"{json.dumps(keys)}."
        if keys
        else f"Write {count} new items as plain strings."
    )
    result = await llm.complete_structured(
        system=(
            "You write realistic test items for a user's judgment model. Items must look like real "
            "inputs the model will receive, vary in difficulty, and include borderline cases."
        ),
        prompt=(
            f"WHAT THE MODEL JUDGES:\n{version['description']}\n\n"
            f"OUTPUT LABELS: {json.dumps(version['labels'] or ['good', 'bad'])}\n\n"
            f"EXISTING ITEMS (match their format, do not copy them):\n"
            f"{json.dumps([e['item'] for e in sample], ensure_ascii=False)}\n\n"
            f"GUIDANCE FROM THE USER: {guidance or '(none)'}\n\n{shape}"
        ),
        output_model=_Generated,
        tier=llm.ModelTier.QUALITY,
        max_tokens=4096,
    )
    created = await add_examples(
        owner_id,
        model_id,
        [
            {
                "item": item,
                "label": None,
                "needs_review": True,
                "note": "Generated; confirm or change the label",
            }
            for item in _generated_items(result.items[:count], keys)
        ],
        "generated",
    )
    if not version["head_stale"]:
        for example in created:
            try:
                suggestion = await predict(
                    owner_id,
                    model_id,
                    example["item"],
                    which="draft" if model["draft_version_id"] else "active",
                    caller="generator",
                    log=False,
                )
            except providers.ProviderError:
                continue  # The item stays unlabeled; the reviewer labels it from scratch.
            await get_pool().execute(
                "UPDATE intuition_examples SET label = $2, note = $3 WHERE id = $1",
                UUID(example["id"]),
                suggestion["label"],
                f"Generated; suggested {suggestion['label']} at {suggestion['confidence']:.0%} — confirm or change",
            )
    return await _examples(model_id, [e["id"] for e in created])


class _Criterion(BaseModel):
    key: str
    description: str


class _QuestionDraft(BaseModel):
    """Schema-constrained question; converted to the rubric's typed shape."""

    id: str
    type: Literal["noul", "choice", "score"]
    prompt: str
    criteria: list[_Criterion]


def _question(draft: _QuestionDraft, taken: set[str]) -> dict:
    if draft.type == "noul":
        by_key = {c.key.lower(): c.description for c in draft.criteria}
        criteria: dict | list = {
            "true": by_key.get("true", "Yes"),
            "false": by_key.get("false", "No"),
        }
    elif draft.type == "choice":
        criteria = {c.key: c.description for c in draft.criteria}
    else:
        criteria = [c.description for c in draft.criteria]
    slug = re.sub(r"[^a-z0-9_-]+", "_", draft.id.lower()).strip("_-")[:60] or "question"
    while slug in taken:
        slug = f"{slug}_2"
    taken.add(slug)
    try:
        return Question.model_validate(
            {"id": slug, "type": draft.type, "prompt": draft.prompt, "criteria": criteria}
        ).model_dump(mode="json")
    except ValidationError as exc:
        raise Conflict("Claude proposed an invalid rubric question; try again") from exc


QUESTION_FORMAT = (
    "Each question has: id (short lowercase slug), type, prompt, and criteria. Types: 'noul' is "
    "yes/no (criteria keys exactly 'true' and 'false'); 'choice' picks one option (2-6 criteria, "
    "key = option name); 'score' is an ordered scale (3-5 criteria from lowest to highest, keys "
    "'0','1',...). Questions must be answerable from the item alone, concrete, and non-overlapping. "
    "A judge model answers each question with probabilities; a small logistic model learns how "
    "much each answer matters, so ask about observable properties, not the final verdict itself. "
    "Describe general properties, never specific wording: do not quote or paraphrase text from the "
    "examples, so the question still applies to new items and to paraphrases."
)


def _show_examples(examples: list[dict]) -> str:
    return json.dumps(
        [{"item": e["item"], "item_b": e["item_b"], "label": e["label"]} for e in examples],
        ensure_ascii=False,
    )


class _RubricDraft(BaseModel):
    rationale: str
    questions: list[_QuestionDraft] = Field(min_length=1)


async def draft_rubric(owner_id: UUID, model_id: UUID, count: int, guidance: str) -> dict:
    """Propose a starting rubric from the description and labeled examples (not saved)."""
    model = await _model(owner_id, model_id)
    version = await _load_version(model["draft_version_id"] or model["active_version_id"])
    labeled = [e for e in await _examples(model_id) if e["label"] and not e["needs_review"]]
    sample = random.Random(0).sample(labeled, min(24, len(labeled)))
    return await propose_rubric(
        version["description"], model["output_type"], version["labels"], sample, count, guidance
    )


async def propose_rubric(
    description: str,
    output_type: str,
    labels: list[dict],
    examples: list[dict],
    count: int,
    guidance: str,
) -> dict:
    """Claude drafts rubric questions from a description and labeled examples."""
    result = await llm.complete_structured(
        system=(
            "You design rubrics for a user's personal judgment model. Find the properties that "
            "explain how this user labels items. " + QUESTION_FORMAT
        ),
        prompt=(
            f"WHAT THE MODEL JUDGES:\n{description or '(not described yet)'}\n\n"
            f"OUTPUT: {output_type} {json.dumps(labels)}\n\n"
            f"LABELED EXAMPLES:\n{_show_examples(examples) if examples else '(none yet)'}\n\n"
            f"GUIDANCE FROM THE USER: {guidance or '(none)'}\n\n"
            f"Propose {count} questions."
        ),
        output_model=_RubricDraft,
        tier=llm.ModelTier.QUALITY,
        max_tokens=4096,
    )
    taken: set[str] = set()
    questions = [_question(q, taken) for q in result.questions[:MAX_QUESTIONS]]
    return {
        "rationale": result.rationale,
        "rubric": questions,
        "examples_considered": len(examples),
    }


class _Suggestion(BaseModel):
    rationale: str
    question: _QuestionDraft


async def suggest_question(owner_id: UUID, model_id: UUID) -> dict:
    """Propose one rubric question that would separate the draft's current mistakes."""
    model = await _model(owner_id, model_id)
    version = await _load_version(model["draft_version_id"] or model["active_version_id"])
    if version["metrics"] is None:
        raise Conflict("Fit the head first so there are mistakes to learn from")
    by_id = {e["id"]: e for e in await _examples(model_id)}
    scored = version["metrics"]["train"]["rows"] + version["metrics"]["eval"]["rows"]
    wrong = [r for r in scored if r["predicted"] != r["label"]][:12]
    right = [r for r in scored if r["predicted"] == r["label"]][:6]
    if not wrong:
        raise Conflict("The head makes no mistakes on labeled examples; add harder examples first")

    def show(rows):
        return json.dumps(
            [
                {
                    "item": by_id[r["example_id"]]["item"],
                    "item_b": by_id[r["example_id"]]["item_b"],
                    "true_label": r["label"],
                    "predicted": r["predicted"],
                }
                for r in rows
                if r["example_id"] in by_id
            ],
            ensure_ascii=False,
        )

    result = await llm.complete_structured(
        system=(
            "You improve a rubric used by a judge model. Propose ONE new question that the existing "
            "questions miss and that would separate the mistakes from the correct cases. "
            + QUESTION_FORMAT
        ),
        prompt=(
            f"WHAT THE MODEL JUDGES:\n{version['description']}\n\n"
            f"CURRENT RUBRIC:\n{json.dumps(version['rubric'], ensure_ascii=False)}\n\n"
            f"MISTAKES:\n{show(wrong)}\n\nCORRECT CASES:\n{show(right)}"
        ),
        output_model=_Suggestion,
        tier=llm.ModelTier.QUALITY,
        max_tokens=2048,
    )
    question = _question(result.question, {q["id"] for q in version["rubric"]})
    return {"rationale": result.rationale, "question": question, "mistakes_considered": len(wrong)}
