"""Behaviors: define them, review their hits, and turn hits into eval data.

Editing what a behavior means (definition, examples, detector, rule) bumps its
version: unreviewed automatic hits are dropped and the scanner reads every
trace again. Reviews are human judgments and survive. A behavior can be
promoted to an eval: confirmed hits become "yes" examples and rejected hits
"no", each item being the trace window with a little context; from then on
reviews keep feeding that eval.
"""

from __future__ import annotations

import re
from uuid import UUID

from ...database import get_pool
from ..intuition import builder, curation
from ..intuition import service as evals
from . import alerts, builtin
from .monitoring import _public

CONTEXT_STEPS = 2
MEANING = ("definition", "examples", "detector", "rule")


class NotFound(LookupError):
    pass


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "behavior"


def _validate(detector: str, rule: dict | None, definition: str) -> dict | None:
    if detector == "rule":
        if not rule or rule.get("kind") not in builtin.RULES:
            raise ValueError(f"A rule behavior needs rule.kind, one of {', '.join(builtin.RULES)}")
        return {"kind": rule["kind"]}
    if not definition.strip():
        raise ValueError("A model-detected behavior needs a definition")
    return None


async def _get(owner_id: UUID, behavior_id: UUID) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM behaviors WHERE id = $1 AND owner_user_id = $2", behavior_id, owner_id
    )
    if row is None:
        raise NotFound("Behavior not found")
    return dict(row)


async def list_behaviors(owner_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT b.*, (SELECT count(*) FROM behavior_hits h WHERE h.behavior_id = b.id
                         AND h.review IS DISTINCT FROM 'rejected')::int AS hit_count
           FROM behaviors b WHERE b.owner_user_id = $1 ORDER BY b.actor, b.name""",
        owner_id,
    )
    return [{**_public(r), "hit_count": r["hit_count"]} for r in rows]


async def get(owner_id: UUID, behavior_id: UUID) -> dict:
    return _public(await _get(owner_id, behavior_id))


async def create(owner_id: UUID, body: dict) -> dict:
    rule = _validate(body["detector"], body.get("rule"), body.get("definition", ""))
    alert = alerts.normalize(body.get("alert"))
    base = body.get("slug") or slugify(body["name"])
    pool = get_pool()
    taken = {
        r["slug"]
        for r in await pool.fetch(
            "SELECT slug FROM behaviors WHERE owner_user_id = $1 AND slug LIKE $2 || '%'",
            owner_id,
            base,
        )
    }
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    row = await pool.fetchrow(
        """INSERT INTO behaviors
             (owner_user_id, name, slug, actor, definition, examples, detector, rule, severity, enabled, alert)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *""",
        owner_id, body["name"], slug, body["actor"], body.get("definition", ""), body.get("examples") or [],
        body["detector"], rule, body.get("severity", "medium"), body.get("enabled", True), alert,
    )  # fmt: skip
    return _public(row)


async def install_starters(owner_id: UUID, kinds: list[str] | None = None) -> list[dict]:
    pool = get_pool()
    existing = {
        r["kind"]
        for r in await pool.fetch(
            "SELECT rule->>'kind' AS kind FROM behaviors WHERE owner_user_id = $1 AND detector = 'rule'",
            owner_id,
        )
    }
    created = []
    for starter in builtin.STARTERS:
        if (kinds and starter["kind"] not in kinds) or starter["kind"] in existing:
            continue
        created.append(
            await create(
                owner_id,
                {**starter, "detector": "rule", "rule": {"kind": starter["kind"]}},
            )
        )
    return created


async def update(owner_id: UUID, behavior_id: UUID, changes: dict) -> dict:
    current = await _get(owner_id, behavior_id)
    merged = {**current, **changes}
    if "alert" in changes:
        changes["alert"] = alerts.normalize(changes["alert"])
    if any(k in changes for k in ("detector", "rule", "definition")):
        changes["rule"] = _validate(
            merged["detector"], merged.get("rule"), merged.get("definition") or ""
        )
    bump = any(k in changes and changes[k] != current[k] for k in MEANING)
    allowed = (
        "name",
        "actor",
        "definition",
        "examples",
        "detector",
        "rule",
        "severity",
        "enabled",
        "alert",
    )
    sets = {k: v for k, v in changes.items() if k in allowed}
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        if sets:
            cols = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(sets))
            await conn.execute(
                f"UPDATE behaviors SET {cols}, updated_at = now() WHERE id = $1 AND owner_user_id = $2",
                behavior_id,
                owner_id,
                *sets.values(),
            )
        if bump:
            await conn.execute(
                "UPDATE behaviors SET version = version + 1 WHERE id = $1", behavior_id
            )
            await conn.execute(
                "DELETE FROM behavior_hits WHERE behavior_id = $1 AND source = 'auto' AND review IS NULL",
                behavior_id,
            )
    return await get(owner_id, behavior_id)


async def delete(owner_id: UUID, behavior_id: UUID) -> None:
    await _get(owner_id, behavior_id)
    await get_pool().execute("DELETE FROM behaviors WHERE id = $1", behavior_id)


def _hit(row) -> dict:
    return dict(row)


async def hits(
    owner_id: UUID,
    behavior_id: UUID,
    *,
    review: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    await _get(owner_id, behavior_id)
    rows = await get_pool().fetch(
        """SELECT h.*, t.title AS trace_title, t.created_at AS trace_created_at
           FROM behavior_hits h JOIN rm_traces t ON t.id = h.trace_id
           WHERE h.behavior_id = $1
             AND ($2::text IS NULL OR ($2 = 'unreviewed' AND h.review IS NULL) OR h.review = $2)
           ORDER BY t.created_at DESC, h.start_idx LIMIT $3 OFFSET $4""",
        behavior_id,
        review,
        limit,
        offset,
    )
    return [_hit(r) for r in rows]


async def trace_hits(owner_id: UUID, trace_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT h.*, b.name AS behavior_name, b.actor, b.severity
           FROM behavior_hits h JOIN behaviors b ON b.id = h.behavior_id
           WHERE h.trace_id = $1 AND h.owner_user_id = $2 ORDER BY h.start_idx, b.name""",
        trace_id,
        owner_id,
    )
    return [_hit(r) for r in rows]


async def window_item(owner_id: UUID, trace_id: UUID, start: int, end: int) -> dict:
    """The eval input for a window: the trace's steps around it, marked."""
    try:
        item, _ = await builder.trace_input(owner_id, trace_id)
    except evals.NotFound as exc:
        raise NotFound(str(exc)) from exc
    lo, hi = start - CONTEXT_STEPS, end + CONTEXT_STEPS
    item["steps"] = [s for s in item["steps"] if lo <= s["index"] <= hi]
    item["window"] = {"start": start, "end": end}
    return item


async def _to_eval(owner_id: UUID, eval_id: UUID, hit: dict, label: str, note: str = "") -> None:
    item = await window_item(owner_id, hit["trace_id"], hit["start_idx"], hit["end_idx"])
    await evals.add_examples(
        owner_id, eval_id, [{"item": item, "label": label, "note": note}], "human"
    )


async def review(owner_id: UUID, hit_id: UUID, verdict: str | None, note: str = "") -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """UPDATE behavior_hits SET review = $3, review_note = $4
           WHERE id = $1 AND owner_user_id = $2 RETURNING *""",
        hit_id,
        owner_id,
        verdict,
        note if verdict else "",
    )
    if row is None:
        raise NotFound("Hit not found")
    behavior = await _get(owner_id, row["behavior_id"])
    if verdict and behavior["eval_id"]:
        await _to_eval(
            owner_id,
            behavior["eval_id"],
            dict(row),
            "yes" if verdict == "confirmed" else "no",
            note,
        )
    return _hit(row)


async def add_hit(
    owner_id: UUID, behavior_id: UUID, trace_id: UUID, start: int, end: int, note: str
) -> dict:
    """A window a person tagged by hand: confirmed by construction."""
    behavior = await _get(owner_id, behavior_id)
    owns = await get_pool().fetchval(
        "SELECT 1 FROM rm_traces WHERE id = $1 AND owner_user_id = $2", trace_id, owner_id
    )
    if not owns:
        raise NotFound("Trace not found")
    row = await get_pool().fetchrow(
        """INSERT INTO behavior_hits
             (behavior_id, owner_user_id, trace_id, start_idx, end_idx, note, source, review, detector_version)
           VALUES ($1, $2, $3, $4, $5, $6, 'human', 'confirmed', $7)
           ON CONFLICT (behavior_id, trace_id, start_idx, end_idx)
           DO UPDATE SET review = 'confirmed', review_note = EXCLUDED.note RETURNING *""",
        behavior_id, owner_id, trace_id, start, end, note, behavior["version"],
    )  # fmt: skip
    if behavior["eval_id"]:
        await _to_eval(owner_id, behavior["eval_id"], dict(row), "yes", note)
    return _hit(row)


async def export(owner_id: UUID, eval_id: UUID, label: str, windows: list[dict]) -> list[dict]:
    """Search results or hits saved as examples of an existing eval."""
    examples = [
        {
            "item": await window_item(
                owner_id, UUID(str(w["trace_id"])), w["start_idx"], w["end_idx"]
            ),
            "label": label,
        }
        for w in windows
    ]
    try:
        return await evals.add_examples(owner_id, eval_id, examples, "production")
    except evals.NotFound as exc:
        raise NotFound(str(exc)) from exc


async def promote(owner_id: UUID, behavior_id: UUID) -> dict:
    """Make the behavior an eval of trace windows, seeded with its reviewed hits."""
    behavior = await _get(owner_id, behavior_id)
    if behavior["eval_id"]:
        raise ValueError("This behavior already has an eval")
    definition = behavior["definition"] or behavior["name"]
    detail = await evals.create_model(
        owner_id,
        name=f"{behavior['name']} (behavior)",
        output_type="choice",
        description=(
            f"Input: a window of an agent trace (steps window.start..window.end, with a little context). "
            f"Decide whether the window shows this {behavior['actor']} behavior: {definition}"
        ),
        labels=[
            {"id": "yes", "description": f"The window shows: {definition}"},
            {"id": "no", "description": "The window does not show it"},
        ],
        rubric=[
            {
                "id": "shows",
                "type": "noul",
                "prompt": f"Do the steps in the window show this behavior? {definition}"[:2000],
                "criteria": {
                    "true": "The window's steps clearly show the behavior",
                    "false": "The behavior does not happen in the window, or only arguably",
                },
            }
        ],
    )
    eval_id = UUID(str(detail["model"]["id"]))
    # What the behavior already says; the costly mistake and must-nevers stay for a person.
    await curation.save_brief(
        owner_id,
        eval_id,
        {
            "decision": f"Does a window of an agent trace show “{behavior['name']}”? Hits feed the behavior's monitor and alerts.",
            "input": "A window of an agent trace: the steps a hit covers, with a little context before it.",
            "labels": f"yes: the window shows it — {definition}\nno: it does not happen in the window, or only arguably.",
        },
    )
    reviewed = await get_pool().fetch(
        "SELECT * FROM behavior_hits WHERE behavior_id = $1 AND review IS NOT NULL ORDER BY created_at",
        behavior_id,
    )
    examples = [
        {
            "item": await window_item(owner_id, r["trace_id"], r["start_idx"], r["end_idx"]),
            "label": "yes" if r["review"] == "confirmed" else "no",
            "note": r["review_note"] or (r["note"] if r["source"] == "human" else ""),
        }
        for r in reviewed
    ]
    if examples:
        await evals.add_examples(owner_id, eval_id, examples, "human")
    await get_pool().execute(
        "UPDATE behaviors SET eval_id = $2, updated_at = now() WHERE id = $1", behavior_id, eval_id
    )
    return {
        "behavior": await get(owner_id, behavior_id),
        "eval_id": eval_id,
        "examples": len(examples),
    }
