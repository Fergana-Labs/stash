"""Rubric versions: every rubric a judge eval has had, and the judge's grades under each.

A version is everything the judge reads besides the submission: the traits, the reference
examples shown beside them and the eval's description. The newest version is current, and
intuition_models.traits follows it. Grades are cached per (rubric, example) under
judge.rubric_key, so measuring a rubric against new evidence costs one judge call per new
example.
"""

from uuid import UUID

from ...database import get_pool

# A trait the person wrote or changed carries by='person'; revisions keep it as written.
PERSON = "person"
# Held-out examples needed before agreement on them, not on the learned-from ones, is the
# agreement a rubric's quality score uses.
QUALITY_HELD_OUT = 4


def _version(row) -> dict:
    return {
        "id": row["id"],
        "number": row["number"],
        "traits": row["traits"],
        "refs": list(row["refs"]),
        "instructions": row["instructions"],
        "scoring": row["scoring"],
        "source": row["source"],
        "changes": row["changes"],
        "metrics": row["metrics"],
        "created_by": row["created_by"],
        "proposal_id": row["proposal_id"],
        "created_at": row["created_at"],
    }


def quality(metrics: dict | None) -> dict | None:
    """One number for how far a rubric can be trusted, 0-100, and the parts it is the mean of
    (each 0-1): how often its verdict matches the person's label (on held-out examples when
    there are enough to measure with, else the ones it learned from), how often it scores a
    good example above a bad one, and how many attempts to talk the judge into passing bad
    work it resisted. None until the rubric has been measured."""
    if not metrics:
        return None
    fit, check = metrics.get("fit") or {}, metrics.get("check") or {}
    measured = check if (check.get("n") or 0) >= QUALITY_HELD_OUT else fit
    parts = {
        "agreement": measured.get("agreement"),
        "ranking": fit.get("good_above_bad"),
    }
    if tried := metrics.get("manipulation"):
        parts["manipulation"] = round(tried["resisted"] / tried["n"], 3) if tried["n"] else None
    parts = {k: v for k, v in parts.items() if v is not None}
    if not parts:
        return None
    return {"score": round(100 * sum(parts.values()) / len(parts)), "parts": parts}


async def current(model_id: UUID) -> dict | None:
    row = await get_pool().fetchrow(
        "SELECT * FROM eval_rubric_versions WHERE model_id=$1 ORDER BY number DESC LIMIT 1",
        model_id,
    )
    return _version(row) if row else None


async def history(model_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT * FROM eval_rubric_versions WHERE model_id=$1 ORDER BY number DESC", model_id
    )
    return [_version(r) for r in rows]


async def save(
    model_id: UUID,
    *,
    after: int,
    traits: list[dict],
    refs: list[UUID],
    instructions: str,
    source: str,
    changes: list[dict],
    metrics: dict | None = None,
    scoring: str = "mean",
    created_by: UUID | None = None,
    proposal_id: UUID | None = None,
    conn=None,
) -> dict | None:
    """Save a new current version on top of version number `after` (0 when there is none).
    created_by is the person who edited the rubric directly; proposal_id the approved
    proposal it came from. A caller already in a transaction passes its connection.

    Returns None when another version was saved since `after`, so a build never writes over
    an edit the person made while it ran."""
    if conn is None:
        async with get_pool().acquire() as own, own.transaction():
            return await save(
                model_id,
                after=after,
                traits=traits,
                refs=refs,
                instructions=instructions,
                source=source,
                changes=changes,
                metrics=metrics,
                scoring=scoring,
                created_by=created_by,
                proposal_id=proposal_id,
                conn=own,
            )
    await conn.execute("SELECT 1 FROM intuition_models WHERE id=$1 FOR UPDATE", model_id)
    latest = await conn.fetchval(
        "SELECT COALESCE(max(number), 0) FROM eval_rubric_versions WHERE model_id=$1",
        model_id,
    )
    if latest != after:
        return None
    row = await conn.fetchrow(
        """INSERT INTO eval_rubric_versions
           (model_id, number, traits, refs, instructions, source, changes, metrics, scoring,
            created_by, proposal_id)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *""",
        model_id,
        latest + 1,
        traits,
        refs,
        instructions,
        source,
        changes,
        metrics,
        scoring,
        created_by,
        proposal_id,
    )
    await conn.execute(
        "UPDATE intuition_models SET traits=$2, updated_at=now() WHERE id=$1", model_id, traits
    )
    return _version(row)


async def draft(
    model_id: UUID,
    *,
    after: int,
    traits: list[dict],
    refs: list[UUID],
    instructions: str,
    source: str,
    changes: list[dict],
    metrics: dict | None = None,
    scoring: str = "mean",
) -> dict:
    """What save() would save, kept in memory: for an eval whose rubric changes need approval,
    a build works on drafts and proposes the last one (proposals.py) instead of saving it."""
    return {
        "id": None,
        "number": after + 1,
        "traits": traits,
        "refs": list(refs),
        "instructions": instructions,
        "scoring": scoring,
        "source": source,
        "changes": changes,
        "metrics": metrics,
        "created_by": None,
        "proposal_id": None,
        "created_at": None,
    }


async def set_metrics(version_id: UUID, metrics: dict) -> None:
    """Merge into the version's metrics (agreement, the manipulation check)."""
    await get_pool().execute(
        "UPDATE eval_rubric_versions SET metrics = COALESCE(metrics, '{}'::jsonb) || $2::jsonb WHERE id=$1",
        version_id,
        metrics,
    )


async def cached(model_id: UUID, rubric_key: str, example_ids: list[UUID]) -> dict[UUID, dict]:
    rows = await get_pool().fetch(
        """SELECT example_id, grade FROM eval_grades
           WHERE model_id=$1 AND rubric_key=$2 AND example_id = ANY($3::uuid[])""",
        model_id,
        rubric_key,
        example_ids,
    )
    return {r["example_id"]: r["grade"] for r in rows}


async def remember(model_id: UUID, rubric_key: str, grades: dict[UUID, dict]) -> None:
    if not grades:
        return
    # Joined to the examples so one deleted while it was being graded is skipped, not an error.
    await get_pool().execute(
        """INSERT INTO eval_grades (model_id, rubric_key, example_id, grade)
           SELECT $1, $2, e.id, g.value FROM jsonb_each($3::jsonb) AS g
           JOIN intuition_examples e ON e.id = g.key::uuid AND e.model_id = $1
           ON CONFLICT (model_id, rubric_key, example_id) DO NOTHING""",
        model_id,
        rubric_key,
        {str(example_id): grade for example_id, grade in grades.items()},
    )
