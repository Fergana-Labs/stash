"""Reviewed rubric changes: propose, check, approve or reject.

An eval with review_required keeps its rubric until a person approves a change. A build,
a rewrite or a person's edit ends in a proposal (eval_rubric_proposals): the rubric it would
become, on the version it was proposed on (base), with what changed and why. Each proposal
carries checks, measured before anyone decides:
- agreement with the person's labels before and after, on learned-from and held-out examples;
- the labeled examples whose verdict it fixes, and the ones it breaks;
- the examples added since the base version, which are what the change answers;
- recent agent calls graded again with the proposed rubric, beside the score each got, and
  a short summary of how the agent fares differently under it;
- the manipulation check (robustness.py) on the proposed rubric;
- the rubric verifier's grade (rubric_quality.py) of both rubrics' text, trait by trait.
Approving saves the proposal as the next rubric version (refused when the rubric has changed
since it was proposed); rejecting keeps the rubric and is shown to later builds, so they
don't propose the same edit. A build's new proposal replaces its earlier open one.
"""

import asyncio
import logging
from uuid import UUID

from ...database import get_pool
from .. import llm
from . import channel, items, judge, revise, robustness, rubric_quality, service, versions

log = logging.getLogger(__name__)

CALLS = 10  # recent agent calls graded again with the proposed rubric
LISTED = 50
SNIPPET = 400
COMMENT = 5000

SUMMARY_SYSTEM = """You are told how an AI agent's recent outputs score under the rubric in \
use and under a proposed rubric that would replace it. Say, for the person deciding whether to \
adopt the proposed rubric, what kind of output it treats differently and why.

One sentence, 20 words at most, in plain words. Describe the kind of output, not the \
individual outputs: no names of outputs, no scores, no counts, no lists, no parentheses, no \
colons or semicolons, and never an arrow character. The page shows the outputs and their \
scores right below your sentence. For example: "Replies that promise a refund without \
checking the order now fail." If no verdict changes, reply "No verdicts change." Reply with \
the sentence and nothing else."""


def _proposal(row) -> dict:
    return {
        "id": row["id"],
        "number": row["number"],
        "name": row["name"],
        "base": row["base"],
        "traits": row["traits"],
        "refs": list(row["refs"]),
        "instructions": row["instructions"],
        "scoring": row["scoring"],
        "source": row["source"],
        "changes": row["changes"],
        "checks": row["checks"],
        "status": row["status"],
        "proposed_by": row["proposed_by"],
        "thread_id": row["thread_id"],
        "decided_by": row["decided_by"],
        "decided_at": row["decided_at"],
        "note": row["note"],
        "version": row["version"],
        "created_at": row["created_at"],
    }


def _flips(examples: list[dict], before: dict, after: dict) -> tuple[list[dict], list[dict]]:
    """(fixed, broke): examples both rubrics graded whose verdict the change sets right, and
    the ones it sets wrong."""
    fixed, broke = [], []
    for e in revise._both(examples, before, after):
        was, now = revise.right(e, before[e["id"]]), revise.right(e, after[e["id"]])
        if was != now:
            (fixed if now else broke).append(
                {
                    "id": str(e["id"]),
                    "before": before[e["id"]]["score"],
                    "after": after[e["id"]]["score"],
                }
            )
    return fixed, broke


async def _regrade_calls(model_id: UUID, candidate: dict) -> tuple[dict | None, dict[str, str]]:
    """The eval's most recent agent calls (whole outputs, not changes), graded again with the
    proposed rubric: each call's score then and now, the trait it scores lowest on now, and
    which verdicts change. Also the start of each call's output, by call id."""
    rows = await get_pool().fetch(
        """SELECT id, input, confidence FROM intuition_predictions
           WHERE model_id=$1 AND COALESCE(output->>'mode', '') <> 'change'
           ORDER BY created_at DESC LIMIT $2""",
        model_id,
        CALLS,
    )
    if not rows:
        return None, {}
    gate = asyncio.Semaphore(revise.CONCURRENCY)
    graded: list[dict] = []

    async def one(row) -> None:
        async with gate:
            try:
                result = await judge.grade(model_id, row["input"], version=candidate)
            except judge.JudgeUnavailable:
                return
        low = min(result.get("traits") or [], key=lambda t: t["score"], default=None)
        graded.append(
            {
                "id": str(row["id"]),
                "before": float(row["confidence"]),
                "after": result["score"],
                "low": low and {"trait": low["trait"], "why": low.get("why", "")},
            }
        )

    await asyncio.gather(*(one(r) for r in rows))
    if not graded:
        return None, {}
    order = {str(r["id"]): i for i, r in enumerate(rows)}
    graded.sort(key=lambda g: order[g["id"]])
    n = len(graded)
    texts = {str(r["id"]): _snippet(r["input"])["text"] for r in rows}
    return {
        "n": n,
        "mean_before": round(sum(g["before"] for g in graded) / n, 3),
        "mean_after": round(sum(g["after"] for g in graded) / n, 3),
        "pass_before": sum(g["before"] >= 0.5 for g in graded),
        "pass_after": sum(g["after"] >= 0.5 for g in graded),
        "changed": [g for g in graded if (g["before"] >= 0.5) != (g["after"] >= 0.5)],
        "calls": graded,
    }, texts


async def _summarize(
    model_id: UUID, changes: list[dict], calls: dict, texts: dict[str, str]
) -> str | None:
    """What kind of output the proposed rubric treats differently from the one in use, in one
    plain sentence, from the agent's recent calls graded under both."""

    def verdict(score: float) -> str:
        return "pass" if score >= 0.5 else "fail"

    lines = [
        "The proposed rubric's edits:",
        *(f"- {c['kind']} {c.get('trait', '')}: {c.get('why', '')}" for c in changes),
        "",
        f"The agent's last {calls['n']} outputs: {calls['pass_before']} pass under the rubric "
        f"in use, {calls['pass_after']} under the proposed one. Mean score "
        f"{calls['mean_before']:.2f} then, {calls['mean_after']:.2f} now.",
        "",
        "Each output (score and verdict under the rubric in use, then under the proposed one):",
    ]
    for g in calls["calls"]:
        low = g.get("low")
        lines.append(
            f"- {g['before']:.2f} {verdict(g['before'])} -> {g['after']:.2f} {verdict(g['after'])}"
            + (f"; lowest trait now: {low['trait']} ({low['why']})" if low else "")
            + f"; output starts: {items._clip(texts.get(g['id'], ''), 300, keep='start')}"
        )
    reply = await llm._get_client().messages.create(
        model=judge.model(),
        max_tokens=120,
        system=SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": "\n".join(lines)}]}],
    )
    text = "".join(b.text for b in reply.content if b.type == "text").strip()
    return text[:300] or None


async def checks(
    model_id: UUID,
    base: dict,
    candidate: dict,
    examples: list[dict],
    changes: list[dict] | None = None,
) -> dict:
    """Measure a proposed rubric against the one it would replace. Grades come from the cache
    a build already filled where it can (revise.grades), so this mostly costs the agent calls
    and the manipulation check."""
    _, fit, check = revise._measured(model_id, examples)
    measured = fit + check
    out: dict = {
        "before": None,
        "after": None,
        "fixed": [],
        "broke": [],
        "evidence": [
            str(e["id"])
            for e in examples
            if base.get("created_at") and e["created_at"] > base["created_at"]
        ],
        "calls": None,
        "summary": None,
        "rubric_quality": None,
        "manipulation": None,
        "short": None,
    }
    if {e["label"] for e in fit} == {"good", "bad"}:
        before = await revise.grades(model_id, base, measured)
        after = await revise.grades(model_id, candidate, measured)
        short = revise._short(measured, before) or revise._short(measured, after)
        if short:
            out["short"] = short
        else:
            both_fit, both_check = (
                revise._both(fit, before, after),
                revise._both(check, before, after),
            )
            out["before"] = {
                "fit": revise.tally(both_fit, before),
                "check": revise.tally(both_check, before),
            }
            out["after"] = {
                "fit": revise.tally(both_fit, after),
                "check": revise.tally(both_check, after),
            }
            out["fixed"], out["broke"] = _flips(measured, before, after)
    try:
        out["calls"], texts = await _regrade_calls(model_id, candidate)
        if out["calls"]:
            out["summary"] = await _summarize(model_id, changes or [], out["calls"], texts)
    except Exception:
        log.exception("Grading agent calls with a proposed rubric failed for %s", model_id)
    try:
        # The rubric verifier reads each rubric's text: the one in use and the proposed one.
        before_quality, after_quality = await asyncio.gather(
            rubric_quality.grade(base), rubric_quality.grade(candidate)
        )
        if after_quality:
            out["rubric_quality"] = {"before": before_quality, "after": after_quality}
    except Exception:
        log.exception("Grading the quality of a proposed rubric failed for %s", model_id)
    try:
        bad = [e for e in examples if e["split"] == "train" and e["label"] == "bad"]
        out["manipulation"] = await robustness.check(model_id, candidate, bad)
    except Exception:
        log.exception("The manipulation check on a proposed rubric failed for %s", model_id)
    return out


def passed(found: dict | None) -> bool | None:
    """Whether a proposal's checks hold: no fewer learned-from or held-out examples right, no
    example broken, and every manipulation attempt resisted. None while they haven't run."""
    if found is None:
        return None
    before, after = found.get("before"), found.get("after")
    if before and after:
        if after["fit"]["right"] < before["fit"]["right"]:
            return False
        if after["check"]["right"] < before["check"]["right"]:
            return False
    if found.get("broke"):
        return False
    tried = found.get("manipulation")
    return not (tried and tried["resisted"] < tried["n"])


async def create(
    model_id: UUID,
    *,
    base: int,
    candidate: dict,
    changes: list[dict],
    source: str,
    found: dict | None = None,
    proposed_by: UUID | None = None,
    thread_id: UUID | None = None,
) -> dict | None:
    """Open a proposal on version `base`. Returns None when the rubric is no longer at `base`.
    A build's proposal (no proposed_by) replaces the build's earlier open one."""
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT 1 FROM intuition_models WHERE id=$1 FOR UPDATE", model_id)
        latest = await conn.fetchval(
            "SELECT COALESCE(max(number), 0) FROM eval_rubric_versions WHERE model_id=$1",
            model_id,
        )
        if latest != base:
            return None
        if proposed_by is None:
            await conn.execute(
                """UPDATE eval_rubric_proposals SET status='replaced'
                   WHERE model_id=$1 AND status='open' AND proposed_by IS NULL""",
                model_id,
            )
        row = await conn.fetchrow(
            """INSERT INTO eval_rubric_proposals
               (model_id, number, base, traits, refs, instructions, scoring, source, changes,
                checks, proposed_by, thread_id)
               VALUES ($1, (SELECT COALESCE(max(number), 0) + 1 FROM eval_rubric_proposals
                            WHERE model_id=$1),
                       $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *""",
            model_id,
            base,
            candidate["traits"],
            candidate["refs"],
            candidate["instructions"],
            candidate["scoring"],
            source,
            changes,
            found,
            proposed_by,
            thread_id,
        )
    return _proposal(row)


async def turned_down(model_id: UUID, base: int) -> list[dict]:
    """Proposals a reviewer rejected on version `base`."""
    rows = await get_pool().fetch(
        """SELECT * FROM eval_rubric_proposals
           WHERE model_id=$1 AND base=$2 AND status='rejected' ORDER BY number""",
        model_id,
        base,
    )
    return [_proposal(r) for r in rows]


async def waiting(model_id: UUID, base: int) -> list[dict]:
    """The build's own open proposal on version `base`, if it has one."""
    rows = await get_pool().fetch(
        """SELECT * FROM eval_rubric_proposals
           WHERE model_id=$1 AND base=$2 AND status='open' AND proposed_by IS NULL""",
        model_id,
        base,
    )
    return [_proposal(r) for r in rows]


def as_tried(rejected: list[dict]) -> list[str]:
    """Rejected proposals as the analysis model reads them, beside the edits it tried."""
    out = []
    for p in rejected:
        edits = ", ".join(f"{c['kind']} {c['trait']}" for c in p["changes"]) or "no edits"
        out.append(f"{edits}: rejected by the reviewer" + (f': "{p["note"]}"' if p["note"] else ""))
    return out


def repeats(candidate: dict, earlier: list[dict]) -> bool:
    """The same rubric as an earlier proposal on this version: one a reviewer turned down, or
    one still waiting for a decision."""
    return any(
        revise.same(candidate["traits"], p["traits"])
        and candidate["scoring"] == p["scoring"]
        and candidate["instructions"] == p["instructions"]
        for p in earlier
    )


async def run_checks(proposal_id: UUID) -> None:
    """Measure a proposal that was opened without checks (a person's own edit)."""
    row = await get_pool().fetchrow(
        "SELECT * FROM eval_rubric_proposals WHERE id=$1 AND status='open'", proposal_id
    )
    if row is None:
        return
    from . import build

    base = next(
        (v for v in await versions.history(row["model_id"]) if v["number"] == row["base"]), None
    )
    if base is None:
        return
    found = await checks(
        row["model_id"],
        base,
        _proposal(row),
        await build._examples(row["model_id"]),
        row["changes"],
    )
    await get_pool().execute(
        "UPDATE eval_rubric_proposals SET checks=$2 WHERE id=$1", proposal_id, found
    )


# ── The API ──────────────────────────────────────────────────────────────


async def _names(ids: set[UUID]) -> dict[UUID, str]:
    rows = await get_pool().fetch(
        "SELECT id, COALESCE(NULLIF(display_name, ''), name) AS name FROM users WHERE id = ANY($1::uuid[])",
        list(ids),
    )
    return {r["id"]: r["name"] for r in rows}


def _snippet(item: dict) -> dict:
    """What a list shows of an example or a call: its name, the start of its text, its files."""
    trace = item.get("trace") or []
    asked = next((s.get("content", "") for s in reversed(trace) if s.get("role") == "user"), "")
    return {
        "name": item.get("name", ""),
        "asked": str(asked)[:SNIPPET],
        "text": (item.get("text") or "")[:SNIPPET],
        "files": [
            {"name": f["name"], "content_type": f["content_type"]} for f in item.get("files") or []
        ],
    }


async def _render(eval_id: UUID, rows: list) -> list[dict]:
    """Proposals as the page shows them: names for the people, the rubric each would replace,
    and the examples and calls its checks point at."""
    found = [_proposal(r) for r in rows]
    history = {v["number"]: v for v in await versions.history(eval_id)}
    current = max(history, default=0)
    example_ids = {
        UUID(i)
        for p in found
        for i in (
            (p["checks"] or {}).get("evidence", [])
            + [f["id"] for f in (p["checks"] or {}).get("fixed", [])]
            + [f["id"] for f in (p["checks"] or {}).get("broke", [])]
        )
    }
    call_ids = {
        UUID(c["id"])
        for p in found
        for c in ((p["checks"] or {}).get("calls") or {}).get("calls", [])
    }
    examples = await get_pool().fetch(
        """SELECT id, item, label, note, split, created_at, added_by, added_via, caller
           FROM intuition_examples WHERE model_id=$1 AND id = ANY($2::uuid[])""",
        eval_id,
        list(example_ids),
    )
    calls = await get_pool().fetch(
        """SELECT id, input, caller, created_at FROM intuition_predictions
           WHERE model_id=$1 AND id = ANY($2::uuid[])""",
        eval_id,
        list(call_ids),
    )
    comments = await get_pool().fetch(
        """SELECT id, proposal_id, author, trait, body, created_at
           FROM eval_rubric_proposal_comments WHERE proposal_id = ANY($1::uuid[])
           ORDER BY created_at, id""",
        [p["id"] for p in found],
    )
    # A change the wizard drafts is opened for the eval's owner: it answers their examples.
    owner = await get_pool().fetchval(
        "SELECT owner_user_id FROM intuition_models WHERE id=$1", eval_id
    )
    names = await _names(
        {owner}
        | {p[k] for p in found for k in ("proposed_by", "decided_by") if p[k]}
        | {e["added_by"] for e in examples if e["added_by"]}
        | {c["author"] for c in comments if c["author"]}
    )
    shown_examples = {
        str(e["id"]): {
            "id": e["id"],
            **_snippet(e["item"]),
            "label": e["label"],
            "note": e["note"],
            "held_out": e["split"] == "eval",
            "created_at": e["created_at"],
            "added_by_name": names.get(e["added_by"]),
            "added_via": e["added_via"],
            "caller": e["caller"],
        }
        for e in examples
    }
    shown_calls = {
        str(c["id"]): {
            "id": c["id"],
            **_snippet(c["input"]),
            "caller": c["caller"],
            "created_at": c["created_at"],
        }
        for c in calls
    }
    out = []
    for p in found:
        base = history.get(p["base"])
        found_checks = p["checks"]
        ids = (
            (found_checks or {}).get("evidence", [])
            + [f["id"] for f in (found_checks or {}).get("fixed", [])]
            + [f["id"] for f in (found_checks or {}).get("broke", [])]
        )
        graded = ((found_checks or {}).get("calls") or {}).get("calls", [])
        after_metrics = (
            {**found_checks["after"], "manipulation": found_checks.get("manipulation")}
            if found_checks and found_checks.get("after")
            else None
        )
        if after_metrics and not after_metrics["manipulation"]:
            after_metrics.pop("manipulation")
        out.append(
            {
                **{k: v for k, v in p.items() if k not in ("refs", "thread_id")},
                "proposed_by": names.get(p["proposed_by"]),
                "opened_by": names.get(p["proposed_by"] or owner),
                "decided_by": names.get(p["decided_by"]),
                "before": base
                and {k: base[k] for k in ("traits", "scoring", "instructions", "number")},
                "passed": passed(found_checks),
                "quality": {
                    "before": versions.quality(
                        {**found_checks["before"], **_manipulation(base)}
                        if found_checks and found_checks.get("before")
                        else None
                    ),
                    "after": versions.quality(after_metrics),
                },
                # An open proposal made on a version that is no longer current can't be approved.
                "stale": p["status"] == "open" and p["base"] != current,
                "examples": {i: shown_examples[i] for i in ids if i in shown_examples},
                "calls": {c["id"]: shown_calls[c["id"]] for c in graded if c["id"] in shown_calls},
                "comments": [
                    {
                        "id": c["id"],
                        "author": names.get(c["author"]),
                        "trait": c["trait"],
                        "body": c["body"],
                        "created_at": c["created_at"],
                    }
                    for c in comments
                    if c["proposal_id"] == p["id"]
                ],
            }
        )
    return out


def _manipulation(version: dict | None) -> dict:
    tried = ((version or {}).get("metrics") or {}).get("manipulation")
    return {"manipulation": tried} if tried else {}


async def listing(owner: UUID, eval_id: UUID) -> dict:
    row = await service._owned(owner, eval_id)
    rows = await get_pool().fetch(
        """SELECT * FROM eval_rubric_proposals WHERE model_id=$1 AND status <> 'replaced'
           ORDER BY number DESC LIMIT $2""",
        eval_id,
        LISTED,
    )
    return {"review_required": row["review_required"], "proposals": await _render(eval_id, rows)}


async def set_required(owner: UUID, eval_id: UUID, required: bool) -> dict:
    """Turn approval of rubric changes on or off. Turning it off leaves open proposals open:
    they can still be approved or rejected, and builds go back to saving versions."""
    await service._owned(owner, eval_id)
    await get_pool().execute(
        "UPDATE intuition_models SET review_required=$2, updated_at=now() WHERE id=$1",
        eval_id,
        required,
    )
    return await listing(owner, eval_id)


async def _open(conn, eval_id: UUID, proposal_id: UUID):
    row = await conn.fetchrow(
        "SELECT * FROM eval_rubric_proposals WHERE id=$1 AND model_id=$2 FOR UPDATE",
        proposal_id,
        eval_id,
    )
    if row is None:
        raise service.NotFound("Proposed change not found")
    if row["status"] != "open":
        raise service.Conflict(f"This change was already {row['status']}")
    return row


async def approve(owner: UUID, eval_id: UUID, proposal_id: UUID, note: str = "") -> dict:
    """Save the proposal as the next rubric version. Refused when the rubric changed since it
    was proposed: its checks compared it with a rubric that is no longer the current one."""
    await service._owned(owner, eval_id)
    async with get_pool().acquire() as conn, conn.transaction():
        # The eval's row first, then the proposal's: the order create() and a build take them.
        await conn.execute("SELECT 1 FROM intuition_models WHERE id=$1 FOR UPDATE", eval_id)
        row = await _open(conn, eval_id, proposal_id)
        found = row["checks"] or {}
        metrics = found.get("after") and {
            **found["after"],
            **({"manipulation": found["manipulation"]} if found.get("manipulation") else {}),
        }
        saved = await versions.save(
            eval_id,
            after=row["base"],
            traits=row["traits"],
            refs=list(row["refs"]),
            instructions=row["instructions"],
            source=row["source"],
            changes=row["changes"],
            metrics=metrics or None,
            scoring=row["scoring"],
            created_by=row["proposed_by"],
            proposal_id=proposal_id,
            conn=conn,
        )
        if saved is None:
            raise service.Conflict(
                "The rubric changed since this was proposed; it needs proposing again"
            )
        await conn.execute(
            """UPDATE eval_rubric_proposals
               SET status='approved', decided_by=$2, decided_at=now(), note=$3, version=$4
               WHERE id=$1""",
            proposal_id,
            owner,
            note.strip()[:2000],
            saved["number"],
        )
        # The build's other open proposal was made on the version this one replaces.
        await conn.execute(
            """UPDATE eval_rubric_proposals SET status='replaced'
               WHERE model_id=$1 AND status='open' AND proposed_by IS NULL AND id <> $2""",
            eval_id,
            proposal_id,
        )
    await _report(eval_id, row, owner, f"approved: now rubric v{saved['number']}", note)
    # The next build measures the new version and proposes whatever the evidence still asks for.
    await service.request_build(eval_id)
    return await listing(owner, eval_id)


async def reject(owner: UUID, eval_id: UUID, proposal_id: UUID, note: str = "") -> dict:
    await service._owned(owner, eval_id)
    async with get_pool().acquire() as conn, conn.transaction():
        row = await _open(conn, eval_id, proposal_id)
        await conn.execute(
            """UPDATE eval_rubric_proposals
               SET status='rejected', decided_by=$2, decided_at=now(), note=$3 WHERE id=$1""",
            proposal_id,
            owner,
            note.strip()[:2000],
        )
    await _report(eval_id, row, owner, "rejected: the rubric stays as it is", note)
    return await listing(owner, eval_id)


async def comment(
    owner: UUID, eval_id: UUID, proposal_id: UUID, body: str, trait: str = ""
) -> dict:
    """Comment on a proposed change, open or decided: on the whole change, or on one trait of
    the rubric it proposes or replaces."""
    await service._owned(owner, eval_id)
    body = body.strip()
    if not body:
        raise ValueError("A comment needs some text")
    found = await get_pool().fetchval(
        "SELECT 1 FROM eval_rubric_proposals WHERE id=$1 AND model_id=$2 AND status <> 'replaced'",
        proposal_id,
        eval_id,
    )
    if found is None:
        raise service.NotFound("Proposed change not found")
    await get_pool().execute(
        """INSERT INTO eval_rubric_proposal_comments (proposal_id, author, trait, body)
           VALUES ($1, $2, $3, $4)""",
        proposal_id,
        owner,
        trait.strip()[:200],
        body[:COMMENT],
    )
    return await listing(owner, eval_id)


async def _report(eval_id: UUID, row, decided_by: UUID, outcome: str, note: str) -> None:
    """Say what was decided in the channel thread the change's evidence came from."""
    if row["thread_id"] is None:
        return
    try:
        name = (await _names({decided_by})).get(decided_by, "")
        await channel.post_agent(
            eval_id,
            f"Proposed change #{row['number']} {outcome}"
            + (f" ({name})" if name else "")
            + (f'. "{note.strip()}"' if note.strip() else "."),
            thread_id=row["thread_id"],
            kind="rubric",
            data={"proposal": row["number"]},
        )
    except Exception:
        # The decision is saved either way; a channel post that failed doesn't undo it.
        log.exception("Reporting a decision on proposal %s failed", row["id"])
