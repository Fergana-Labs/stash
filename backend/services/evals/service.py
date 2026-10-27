"""Judge evals: examples marked good or bad in, one scoring endpoint out.

An eval is an intuition_models row with scorer 'judge'. Its examples are
intuition_examples labeled 'good' or 'bad' (items as in items.py, files in object
storage); examples dropped into its channel (channel.py) wait unlabeled until the
person's words decide. Building keeps its rubric up to date with them (build.py), and
any new label queues a build (request_build), so the eval keeps learning. Scoring an
agent's trace and output returns a score, a grade per trait, an explanation and fixes
(judge.py), and logs the call to intuition_predictions, where labeling it turns it into
a new example.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ...database import get_pool
from .. import storage_service
from . import items, judge, versions

MAX_EXAMPLES = 500
BUILDING = ("queued", "starting", "traits", "checking", "revising")
# Evidence that arrives together (a bulk drop, a run of labels) is built once.
DEBOUNCE_SECONDS = 20
# A build that hasn't reported progress in this long died with its worker.
STALE_BUILD = timedelta(minutes=30)
# A channel read takes at most 5 minutes (tasks/evals.py); one busy longer died with its
# worker, and a drop still "uploading" after this long was abandoned.
READ_TIMEOUT = "6 minutes"
# The first examples all teach; after that every fourth is held out to measure the rubric.
HOLDOUT_AFTER = 8
HOLDOUT_EVERY = 4


def splits(have: int, count: int) -> list[str]:
    """The split for each of `count` new examples in an eval that already has `have`."""
    return [
        "eval" if i >= HOLDOUT_AFTER and i % HOLDOUT_EVERY == HOLDOUT_EVERY - 1 else "train"
        for i in range(have, have + count)
    ]


UNTITLED = "Untitled eval"


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
           count(*) FILTER (WHERE label IS NULL) AS unlabeled,
           (SELECT count(*) FROM intuition_predictions WHERE model_id=$1) AS calls,
           (SELECT max(number) FROM eval_rubric_versions WHERE model_id=$1) AS version
           FROM intuition_examples WHERE model_id=$1""",
        eval_id,
    )
    return {
        "good": row["good"],
        "bad": row["bad"],
        "unlabeled": row["unlabeled"],
        "calls": row["calls"],
        "version": row["version"],
    }


def _summary(row, counts: dict) -> dict:
    build = row["build"] or {}
    return {
        "id": row["id"],
        "name": row["name"],
        "instructions": row["instructions"],
        "traits": row["traits"] or [],
        "build": {k: v for k, v in build.items() if k != "requests"} or None,
        # Scoring works as soon as there is a rubric; later builds only improve it.
        "ready": bool(row["traits"]),
        "version": counts.get("version"),
        "examples": {"good": counts["good"], "bad": counts["bad"]},
        "unlabeled": counts.get("unlabeled", 0),
        "calls": counts["calls"],
        "agent_busy": row["channel_busy_since"] is not None,
        "endpoint": f"/api/v1/evals/{row['id']}/score",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def create(owner: UUID, name: str, instructions: str = "") -> dict:
    row = await get_pool().fetchrow(
        """INSERT INTO intuition_models (owner_user_id, name, output_type, scorer, instructions)
        VALUES ($1, $2, 'preference', 'judge', $3) RETURNING *""",
        owner,
        name.strip()[:160] or UNTITLED,
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
        "UPDATE intuition_models SET name=COALESCE($2, name), updated_at=now() WHERE id=$1",
        eval_id,
        name.strip()[:160] if name else None,
    )
    if instructions is not None:
        await set_instructions(eval_id, instructions)
    return await get(owner, eval_id)


async def set_instructions(eval_id: UUID, instructions: str) -> None:
    """A new description reaches the judge now: the current rubric gets a version that
    carries it (and the next build measures that version)."""
    instructions = instructions.strip()[:2000]
    changed = await get_pool().fetchval(
        """UPDATE intuition_models SET instructions=$2, updated_at=now()
           WHERE id=$1 AND instructions <> $2 RETURNING true""",
        eval_id,
        instructions,
    )
    if not changed:
        return
    version = await versions.current(eval_id)
    if version is not None and version["instructions"] != instructions:
        await versions.save(
            eval_id,
            after=version["number"],
            traits=version["traits"],
            refs=version["refs"],
            instructions=instructions,
            source="edited",
            changes=[{"kind": "description", "trait": "", "why": "The description changed"}],
            scoring=version["scoring"],
        )
    await request_build(eval_id)


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
    for item, split in zip(stored, splits(have, len(stored)), strict=True):
        row = await get_pool().fetchrow(
            """INSERT INTO intuition_examples (model_id, kind, item, label, source, split, note)
            VALUES ($1, 'item', $2, $3, 'human', $4, $5) RETURNING id, item, label, note, source, split, created_at""",
            eval_id,
            item,
            label,
            split,
            note.strip()[:2000],
        )
        out.append(dict(row))
    await get_pool().execute("UPDATE intuition_models SET updated_at=now() WHERE id=$1", eval_id)
    await request_build(eval_id)
    return out


EXAMPLE_COLUMNS = "id, item, label, note, source, split, message_id, created_at"


async def list_examples(owner: UUID, eval_id: UUID) -> list[dict]:
    await _owned(owner, eval_id)
    rows = await get_pool().fetch(
        f"SELECT {EXAMPLE_COLUMNS} FROM intuition_examples WHERE model_id=$1 ORDER BY created_at",
        eval_id,
    )
    return [dict(r) for r in rows]


async def edit_example(
    owner: UUID, eval_id: UUID, example_id: UUID, label: str | None, note: str | None
) -> dict:
    """Set an example's label (good, bad, or none yet) and, if given, its note."""
    if label not in ("good", "bad", None):
        raise ValueError("label must be good, bad or null")
    await _owned(owner, eval_id)
    row = await get_pool().fetchrow(
        f"""UPDATE intuition_examples SET label=$3::text, needs_review=($3::text IS NULL),
               note=COALESCE($4, note)
            WHERE id=$1 AND model_id=$2 RETURNING {EXAMPLE_COLUMNS}""",
        example_id,
        eval_id,
        label,
        note.strip()[:2000] if note is not None else None,
    )
    if row is None:
        raise NotFound("Example not found")
    # A label set on a dropped file is reported in that drop's thread.
    thread = await get_pool().fetchval(
        "SELECT COALESCE(thread_id, id) FROM eval_messages WHERE id=$1", row["message_id"]
    )
    await request_build(eval_id, reply_to=thread)
    return dict(row)


async def delete_example(owner: UUID, eval_id: UUID, example_id: UUID) -> None:
    """Take an example out of the eval. A channel post that was only there for its files (a
    drop with no words, or one an agent added) goes with its last one, threads and all; a
    post with the person's own words keeps them."""
    await _owned(owner, eval_id)
    row = await get_pool().fetchrow(
        "DELETE FROM intuition_examples WHERE id=$1 AND model_id=$2 RETURNING item, label, message_id",
        example_id,
        eval_id,
    )
    if row is None:
        raise NotFound("Example not found")
    if row["message_id"]:
        await get_pool().execute(
            """DELETE FROM eval_messages m WHERE m.id=$1 AND (m.text = '' OR m.data ? 'via')
                 AND NOT EXISTS (SELECT 1 FROM intuition_examples e WHERE e.message_id = m.id)""",
            row["message_id"],
        )
    if row["label"]:
        await request_build(eval_id)


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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _live(build: dict) -> bool:
    """A build is queued or running, and has reported progress recently."""
    if build.get("stage") not in BUILDING or not build.get("at"):
        return False
    return datetime.now(UTC) - datetime.fromisoformat(build["at"]) < STALE_BUILD


async def request_build(
    eval_id: UUID,
    *,
    fresh: bool = False,
    delay: int = DEBOUNCE_SECONDS,
    reply_to: UUID | None = None,
) -> bool:
    """Bring the rubric up to date with the evidence: queue a build, or have the running one
    go again when it finishes. fresh rewrites the rubric from scratch instead of revising it.
    reply_to is the channel thread the evidence came from: the build reports there, and
    evidence from outside the channel leaves the report to the rubric panel. Returns whether a
    new build was queued."""
    from ...tasks import evals as eval_tasks

    async with get_pool().acquire() as conn, conn.transaction():
        build = (
            await conn.fetchval(
                "SELECT build FROM intuition_models WHERE id=$1 FOR UPDATE", eval_id
            )
            or {}
        )
        if not await conn.fetchval(
            """SELECT EXISTS (SELECT 1 FROM intuition_examples
               WHERE model_id=$1 AND label IN ('good','bad'))""",
            eval_id,
        ):
            return False  # nothing to build from yet
        queue = not _live(build)
        if queue:
            flags = {
                "stage": "queued",
                "done": 0,
                "total": 0,
                "error": None,
                "again": False,
                "fresh": fresh,
                "at": _now(),
            }
        else:
            # A queued build hasn't read the evidence yet; a running one goes again after.
            flags = {"fresh": True} if fresh else {}
            if build["stage"] != "queued":
                flags["again"] = True
        if reply_to is not None:
            # Numbered, so a build can tell evidence that came in after it started, even in
            # the same thread, from the evidence it reported.
            flags["reply_to"] = str(reply_to)
            flags["reply_seq"] = int(build.get("reply_seq") or 0) + 1
        if flags:
            await conn.execute(
                """UPDATE intuition_models SET build = COALESCE(build, '{}'::jsonb) || $2::jsonb
                   WHERE id=$1""",
                eval_id,
                flags,
            )
    if queue:
        eval_tasks.build_eval.apply_async(args=[str(eval_id)], countdown=delay)
    elif build["stage"] == "queued" and delay == 0:
        # Asked for now while a debounced build waits: start it now (claim_build lets one run).
        eval_tasks.build_eval.apply_async(args=[str(eval_id)], countdown=0)
    return queue


async def claim_build(eval_id: UUID) -> dict | None:
    """Take the queued build for this worker: {"fresh": bool, "reply_to": the thread to report
    in, or None}, or None if another worker took it. reply_to stays in the build state until
    the build finishes (done_reporting), so a build the sweep restarts still reports."""
    row = await get_pool().fetchrow(
        """WITH old AS (
               SELECT build FROM intuition_models
               WHERE id=$1 AND build->>'stage' = 'queued' FOR UPDATE
           )
           UPDATE intuition_models m
              SET build = m.build
                          || jsonb_build_object('stage', 'starting', 'fresh', false, 'at', $2::text)
             FROM old WHERE m.id=$1
           RETURNING COALESCE((old.build->>'fresh')::boolean, false) AS fresh,
                     (old.build->>'reply_to')::uuid AS reply_to,
                     (old.build->>'reply_seq')::int AS reply_seq""",
        eval_id,
        _now(),
    )
    if row is None:
        return None
    return {"fresh": row["fresh"], "reply_to": row["reply_to"], "reply_seq": row["reply_seq"]}


async def done_reporting(eval_id: UUID, reply_seq: int | None) -> None:
    """A build is over, reported or failed: forget the thread it claimed, unless evidence came
    in after it started (even in the same thread), which the next build reports."""
    if reply_seq is not None:
        await get_pool().execute(
            """UPDATE intuition_models SET build = build - 'reply_to'
               WHERE id=$1 AND (build->>'reply_seq')::int = $2""",
            eval_id,
            reply_seq,
        )


async def finish_build(eval_id: UUID) -> None:
    """Evidence that arrived while the build ran gets a build of its own (a fresh one, if a
    rewrite was asked for meanwhile)."""
    fresh = await get_pool().fetchval(
        """WITH old AS (SELECT build FROM intuition_models WHERE id=$1 FOR UPDATE)
           UPDATE intuition_models m SET build = m.build || '{"again": false, "fresh": false}'::jsonb
             FROM old WHERE m.id=$1 AND COALESCE((old.build->>'again')::boolean, false)
           RETURNING COALESCE((old.build->>'fresh')::boolean, false)""",
        eval_id,
    )
    if fresh is not None:
        await request_build(eval_id, fresh=fresh)


async def start_build(owner: UUID, eval_id: UUID, fresh: bool = False) -> dict:
    await _owned(owner, eval_id)
    counts = await _counts(eval_id)
    if counts["good"] + counts["bad"] < 1:
        raise ValueError("Label at least one example first")
    await request_build(eval_id, fresh=fresh, delay=0)
    return await get(owner, eval_id)


# ── The rubric ───────────────────────────────────────────────────────────


def rubric_changes(before: list[dict], after: list[dict], kind: str) -> list[dict]:
    """What changed between two trait lists, by trait name."""
    old = {t["name"]: t for t in before}
    new = {t["name"]: t for t in after}
    same = lambda a, b: all(a.get(k, "") == b.get(k, "") for k in ("good", "bad"))  # noqa: E731
    return (
        [{"kind": "add", "trait": n, "why": kind} for n in new if n not in old]
        + [{"kind": "tighten", "trait": n, "why": kind} for n in new if n in old and not same(old[n], new[n])]
        + [{"kind": "remove", "trait": n, "why": kind} for n in old if n not in new]
    )  # fmt: skip


async def rubric(owner: UUID, eval_id: UUID) -> dict:
    await _owned(owner, eval_id)
    return {"versions": await versions.history(eval_id)}


async def edit_rubric(owner: UUID, eval_id: UUID, traits: list[dict], base: int) -> dict:
    """The person's own edit of version `base`: a new version, measured (and built on) by the
    next build. Traits they add or change are theirs; revisions keep them word for word. An
    edit made on a version that is no longer current is refused rather than undoing the
    newer one."""
    row = await _owned(owner, eval_id)
    version = await versions.current(eval_id)
    if (version["number"] if version else 0) != base:
        raise Conflict("The rubric changed while you were editing; reload and try again")
    before = version["traits"] if version else (row["traits"] or [])
    old = {t["name"]: t for t in before}
    edited = []
    for t in traits:
        prior = old.get(t["name"])
        unchanged = prior and all(prior.get(k, "") == t.get(k, "") for k in ("good", "bad"))
        edited.append(
            {**(prior if unchanged else t), **({} if unchanged else {"by": versions.PERSON})}
        )
    changes = rubric_changes(before, edited, "You edited the rubric")
    if not changes:
        return await rubric(owner, eval_id)
    saved = await versions.save(
        eval_id,
        after=base,
        traits=edited,
        refs=await _refs(eval_id, version),
        instructions=row["instructions"],
        source="edited",
        changes=changes,
        scoring=version["scoring"] if version else "mean",
    )
    if saved is None:
        raise Conflict("The rubric changed while you were editing; reload and try again")
    await request_build(eval_id)
    return await rubric(owner, eval_id)


async def _refs(eval_id: UUID, version: dict | None) -> list[UUID]:
    if version:
        return version["refs"]
    rows = await get_pool().fetch(
        "SELECT id, label FROM intuition_examples WHERE model_id=$1 AND split='train' AND label IN ('good','bad')",
        eval_id,
    )
    return judge.pick_refs([dict(r) for r in rows], str(eval_id))


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
    # A relabel keeps the split the example already had; a new label takes the next one.
    split = (
        await get_pool().fetchval(
            "SELECT split FROM intuition_examples WHERE id=$1", call["example_id"]
        )
        or splits(
            await get_pool().fetchval(
                "SELECT count(*) FROM intuition_examples WHERE model_id=$1", eval_id
            ),
            1,
        )[0]
    )
    async with get_pool().acquire() as conn, conn.transaction():
        if call["example_id"]:
            await conn.execute("DELETE FROM intuition_examples WHERE id=$1", call["example_id"])
        example_id = None
        if label:
            example_id = await conn.fetchval(
                """INSERT INTO intuition_examples (model_id, kind, item, label, source, split, note)
                VALUES ($1, 'item', $2, $3, 'production', $4, $5) RETURNING id""",
                eval_id,
                call["input"],
                label,
                split,
                note.strip()[:2000],
            )
        await conn.execute(
            "UPDATE intuition_predictions SET example_id=$2, status=$3 WHERE id=$1",
            call_id,
            example_id,
            "labeled" if label else "unreviewed",
        )
    # A verdict on real traffic is the evidence the rubric most needs to agree with.
    await request_build(eval_id)
    return {"call_id": call_id, "label": label, "example_id": example_id}


# ── Recovery ─────────────────────────────────────────────────────────────


async def sweep() -> dict:
    """Restart what a lost task left stuck (beat runs this every minute): builds queued or
    running with no progress, and channels with messages nobody is reading. Each restart
    goes through the usual claims, so a task that is in fact alive never runs twice."""
    from ...tasks import evals as eval_tasks

    now = datetime.now(UTC)
    builds = await get_pool().fetch(
        """UPDATE intuition_models
              SET build = build || jsonb_build_object('stage', 'queued', 'at', $4::text)
           WHERE scorer = 'judge' AND build->>'stage' = ANY($1::text[])
             AND (build->>'at')::timestamptz
                 < CASE WHEN build->>'stage' = 'queued' THEN $3::timestamptz
                        ELSE $2::timestamptz END
           RETURNING id""",
        list(BUILDING),
        now - STALE_BUILD,
        now - timedelta(seconds=DEBOUNCE_SECONDS + 120),
        now.isoformat(),
    )
    for row in builds:
        eval_tasks.build_eval.apply_async(args=[str(row["id"])], countdown=0)
    channels = await get_pool().fetch(
        f"""SELECT DISTINCT m.model_id FROM eval_messages m
            JOIN intuition_models im ON im.id = m.model_id
            WHERE m.author = 'user' AND m.handled_at IS NULL
              AND m.created_at < now() - interval '30 seconds'
              AND (NOT m.data ? 'uploading' OR m.created_at < now() - interval '{READ_TIMEOUT}')
              AND (im.channel_busy_since IS NULL
                   OR im.channel_busy_since < now() - interval '{READ_TIMEOUT}')"""
    )
    for row in channels:
        eval_tasks.read_channel.delay(str(row["model_id"]))
    return {"builds": len(builds), "channels": len(channels)}
