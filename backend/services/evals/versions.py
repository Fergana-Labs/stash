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
        "created_at": row["created_at"],
    }


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
) -> dict | None:
    """Save a new current version on top of version number `after` (0 when there is none).

    Returns None when another version was saved since `after`, so a build never writes over
    an edit the person made while it ran."""
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT 1 FROM intuition_models WHERE id=$1 FOR UPDATE", model_id)
        latest = await conn.fetchval(
            "SELECT COALESCE(max(number), 0) FROM eval_rubric_versions WHERE model_id=$1",
            model_id,
        )
        if latest != after:
            return None
        row = await conn.fetchrow(
            """INSERT INTO eval_rubric_versions
               (model_id, number, traits, refs, instructions, source, changes, metrics, scoring)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *""",
            model_id,
            latest + 1,
            traits,
            refs,
            instructions,
            source,
            changes,
            metrics,
            scoring,
        )
        await conn.execute(
            "UPDATE intuition_models SET traits=$2, updated_at=now() WHERE id=$1", model_id, traits
        )
    return _version(row)


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
