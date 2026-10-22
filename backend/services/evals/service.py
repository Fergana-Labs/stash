"""Judge evals: examples marked good or bad in, one scoring endpoint out.

An eval is an intuition_models row with scorer 'judge'. Its examples are
intuition_examples labeled 'good' or 'bad' (items as in items.py, files in object
storage). Building writes its traits (build.py). Scoring an agent's trace and output
returns a score, a grade per trait, an explanation and fixes (judge.py), and logs the
call to intuition_predictions, where labeling it turns it into a new example.
"""

import asyncio
from uuid import UUID

from ...database import get_pool
from .. import storage_service
from . import items, judge

MAX_EXAMPLES = 500
BUILDING = ("queued", "traits", "checking")


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


async def _owned(owner: UUID, eval_id: UUID):
    row = await get_pool().fetchrow(
        "SELECT * FROM intuition_models WHERE id=$1 AND owner_user_id=$2 AND scorer='judge'",
        eval_id,
        owner,
    )
    if row is None:
        raise NotFound("Eval not found")
    return row


async def _counts(eval_id: UUID) -> dict:
    row = await get_pool().fetchrow(
        """SELECT count(*) FILTER (WHERE label='good') AS good, count(*) FILTER (WHERE label='bad') AS bad,
           (SELECT count(*) FROM intuition_predictions WHERE model_id=$1) AS calls
           FROM intuition_examples WHERE model_id=$1""",
        eval_id,
    )
    return {"good": row["good"], "bad": row["bad"], "calls": row["calls"]}


def _summary(row, counts: dict) -> dict:
    build = row["build"] or {}
    return {
        "id": row["id"],
        "name": row["name"],
        "instructions": row["instructions"],
        "traits": row["traits"] or [],
        "build": build or None,
        "ready": bool(row["traits"]) and build.get("stage") == "done",
        "examples": {"good": counts["good"], "bad": counts["bad"]},
        "calls": counts["calls"],
        "endpoint": f"/api/v1/evals/{row['id']}/score",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def create(owner: UUID, name: str, instructions: str = "") -> dict:
    row = await get_pool().fetchrow(
        """INSERT INTO intuition_models (owner_user_id, name, output_type, scorer, instructions)
        VALUES ($1, $2, 'preference', 'judge', $3) RETURNING *""",
        owner,
        name.strip()[:160] or "Untitled eval",
        instructions.strip()[:2000],
    )
    return _summary(row, {"good": 0, "bad": 0, "calls": 0})


async def get(owner: UUID, eval_id: UUID) -> dict:
    return _summary(await _owned(owner, eval_id), await _counts(eval_id))


async def list_evals(owner: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT * FROM intuition_models WHERE owner_user_id=$1 AND scorer='judge' ORDER BY updated_at DESC",
        owner,
    )
    return [_summary(r, await _counts(r["id"])) for r in rows]


async def update(owner: UUID, eval_id: UUID, name: str | None, instructions: str | None) -> dict:
    await _owned(owner, eval_id)
    await get_pool().execute(
        """UPDATE intuition_models SET name=COALESCE($2, name), instructions=COALESCE($3, instructions),
        updated_at=now() WHERE id=$1""",
        eval_id,
        name.strip()[:160] if name else None,
        instructions.strip()[:2000] if instructions is not None else None,
    )
    return await get(owner, eval_id)


async def delete(owner: UUID, eval_id: UUID) -> None:
    await _owned(owner, eval_id)
    await get_pool().execute("DELETE FROM intuition_models WHERE id=$1", eval_id)


# ── Examples ─────────────────────────────────────────────────────────────


async def add_examples(
    owner: UUID,
    eval_id: UUID,
    label: str,
    files: list[tuple[str, bytes, str]],
    text: str = "",
    trace=None,
    note: str = "",
) -> list[dict]:
    """One example per file; or one example from text and/or a trace when no files are given."""
    if label not in ("good", "bad"):
        raise ValueError("label must be good or bad")
    await _owned(owner, eval_id)
    have = await get_pool().fetchval(
        "SELECT count(*) FROM intuition_examples WHERE model_id=$1", eval_id
    )
    wanted = len(files) or 1
    if have + wanted > MAX_EXAMPLES:
        raise ValueError(f"An eval holds at most {MAX_EXAMPLES} examples")
    stored = (
        # Files are checked and uploaded concurrently; a batch of images otherwise waits on each in turn.
        await asyncio.gather(
            *(items.store(owner, name, [(name, data, ctype)]) for name, data, ctype in files)
        )
        if files
        else [await items.store(owner, "", [], text=text, trace=trace)]
    )
    out = []
    for item in stored:
        row = await get_pool().fetchrow(
            """INSERT INTO intuition_examples (model_id, kind, item, label, source, split, note)
            VALUES ($1, 'item', $2, $3, 'human', 'train', $4) RETURNING id, item, label, note, source, created_at""",
            eval_id,
            item,
            label,
            note.strip()[:2000],
        )
        out.append(dict(row))
    await get_pool().execute("UPDATE intuition_models SET updated_at=now() WHERE id=$1", eval_id)
    return out


async def list_examples(owner: UUID, eval_id: UUID) -> list[dict]:
    await _owned(owner, eval_id)
    rows = await get_pool().fetch(
        "SELECT id, item, label, note, source, created_at FROM intuition_examples WHERE model_id=$1 ORDER BY created_at",
        eval_id,
    )
    return [dict(r) for r in rows]


async def delete_example(owner: UUID, eval_id: UUID, example_id: UUID) -> None:
    await _owned(owner, eval_id)
    row = await get_pool().fetchrow(
        "DELETE FROM intuition_examples WHERE id=$1 AND model_id=$2 RETURNING item",
        example_id,
        eval_id,
    )
    if row is None:
        raise NotFound("Example not found")


async def _file(item: dict, index: int) -> tuple[bytes, str, str]:
    files = item.get("files") or []
    if not 0 <= index < len(files):
        raise NotFound("File not found")
    f = files[index]
    return await storage_service.download_file(f["key"]), f["content_type"], f["name"]


async def example_file(
    owner: UUID, eval_id: UUID, example_id: UUID, index: int
) -> tuple[bytes, str, str]:
    await _owned(owner, eval_id)
    item = await get_pool().fetchval(
        "SELECT item FROM intuition_examples WHERE id=$1 AND model_id=$2", example_id, eval_id
    )
    if item is None:
        raise NotFound("Example not found")
    return await _file(item, index)


# ── Building ─────────────────────────────────────────────────────────────


async def start_build(owner: UUID, eval_id: UUID) -> dict:
    from ...tasks import evals as eval_tasks

    row = await _owned(owner, eval_id)
    if (row["build"] or {}).get("stage") in BUILDING:
        raise Conflict("A build is already running")
    if (await _counts(eval_id))["good"] < 1:
        raise ValueError("Add at least one good example first")
    await get_pool().execute(
        "UPDATE intuition_models SET build=$2::jsonb, updated_at=now() WHERE id=$1",
        eval_id,
        {"stage": "queued", "done": 0, "total": 0, "error": None},
    )
    eval_tasks.build_eval.delay(str(eval_id))
    return await get(owner, eval_id)


# ── Scoring and the call log ─────────────────────────────────────────────


async def score(
    owner: UUID,
    eval_id: UUID,
    *,
    trace=None,
    text: str = "",
    files: list[tuple[str, bytes, str]] = (),
    caller: str = "",
    ref: str | None = None,
    metadata: dict | None = None,
) -> dict:
    row = await _owned(owner, eval_id)
    if not row["traits"]:
        raise Conflict("Build this eval before scoring with it")
    submission = await items.store(owner, "", list(files), text=text, trace=trace)
    result = await judge.grade(eval_id, submission)
    call = await get_pool().fetchrow(
        """INSERT INTO intuition_predictions (model_id, kind, input, output, confidence, caller, ref, metadata)
        VALUES ($1, 'predict', $2, $3, $4, $5, $6, $7) RETURNING id, created_at""",
        eval_id,
        submission,
        result,
        result["score"],
        caller[:100],
        ref,
        metadata or {},
    )
    return {"call_id": call["id"], "created_at": call["created_at"], **result}


async def list_calls(owner: UUID, eval_id: UUID, limit: int = 100) -> list[dict]:
    await _owned(owner, eval_id)
    rows = await get_pool().fetch(
        """SELECT p.id, p.input, p.output, p.caller, p.ref, p.status, p.created_at, e.label, e.note
        FROM intuition_predictions p LEFT JOIN intuition_examples e ON e.id = p.example_id
        WHERE p.model_id=$1 ORDER BY p.created_at DESC LIMIT $2""",
        eval_id,
        limit,
    )
    return [
        {
            "id": r["id"],
            "input": r["input"],
            **r["output"],
            "caller": r["caller"],
            "ref": r["ref"],
            "created_at": r["created_at"],
            "label": r["label"],
            "note": r["note"] or "",
        }
        for r in rows
    ]


async def call_file(
    owner: UUID, eval_id: UUID, call_id: UUID, index: int
) -> tuple[bytes, str, str]:
    await _owned(owner, eval_id)
    item = await get_pool().fetchval(
        "SELECT input FROM intuition_predictions WHERE id=$1 AND model_id=$2", call_id, eval_id
    )
    if item is None:
        raise NotFound("Call not found")
    return await _file(item, index)


async def label_call(
    owner: UUID, eval_id: UUID, call_id: UUID, label: str | None, note: str = ""
) -> dict:
    """Mark a scored output good or bad (it becomes an example), or clear the label."""
    if label not in ("good", "bad", None):
        raise ValueError("label must be good, bad or null")
    await _owned(owner, eval_id)
    call = await get_pool().fetchrow(
        "SELECT input, example_id FROM intuition_predictions WHERE id=$1 AND model_id=$2",
        call_id,
        eval_id,
    )
    if call is None:
        raise NotFound("Call not found")
    async with get_pool().acquire() as conn, conn.transaction():
        if call["example_id"]:
            await conn.execute("DELETE FROM intuition_examples WHERE id=$1", call["example_id"])
        example_id = None
        if label:
            example_id = await conn.fetchval(
                """INSERT INTO intuition_examples (model_id, kind, item, label, source, split, note)
                VALUES ($1, 'item', $2, $3, 'production', 'train', $4) RETURNING id""",
                eval_id,
                call["input"],
                label,
                note.strip()[:2000],
            )
        await conn.execute(
            "UPDATE intuition_predictions SET example_id=$2, status=$3 WHERE id=$1",
            call_id,
            example_id,
            "labeled" if label else "unreviewed",
        )
    return {"call_id": call_id, "label": label, "example_id": example_id}
