"""Build a judge eval: keep its rubric up to date with the evidence.

A build runs whenever labeled evidence changes (service.request_build). It:
1. Writes the rubric when there is none yet, or when a fresh one is asked for: Claude studies
   the good and bad examples it learns from (with the person's notes) and what they said in
   the channel, and writes the traits that separate good from bad, each with what good and
   bad look like here and the evidence it rests on. Writing them down keeps every score on
   the same scale. Evals made before rubric versions keep their traits as version 1.
2. Starts a new version when the eval's description changed, so the judge reads it.
3. Revises the rubric from its mistakes (revise.py), first applying any change the person
   asked for in the channel, and measures it on learned-from and held-out examples.
4. Reports a changed rubric as a reply in the channel thread the evidence came from (none
   for evidence from outside the channel: the rubric panel shows it), and asks about the
   examples it still gets wrong that the person gave no reason for, once each, in the thread
   they were dropped in. The agent never posts at the top of the channel.
"""

import json
import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from ...database import get_pool
from .. import llm
from . import channel, items, judge, revise, robustness, versions

log = logging.getLogger(__name__)

TRAIT_GOOD = 10
TRAIT_BAD = 10
ASK_PER_BUILD = 2

TRAITS_SYSTEM = """You study examples someone marked good and bad, so an AI judge can grade \
new outputs the way they would. Write the 5-10 traits that most separate good from bad \
(with only good examples, the traits that define them; with only bad ones, the failures \
that make them bad and what good looks like instead). Each trait names one property you \
can see in an output, never the verdict itself, and says concretely what good and bad look \
like here: specific enough that two judges would grade the same output the same way. Use \
what the person said about their examples, when they said anything. Nothing about \
signatures, handles or watermarks.

Return only JSON: {"summary": str (one sentence: what these examples are and what makes one \
good), "traits": [{"name": str (2-4 words), "good": str, "bad": str, "basis": str (one \
sentence: the evidence it rests on)}]}"""

VERBS = {
    "add": "added",
    "tighten": "tightened",
    "fix": "fixed",
    "point": "pointed",
    "remove": "removed",
    "request": "changed",
    "scoring": "now scored by",
}


async def _set(model_id: UUID, **build) -> None:
    build["at"] = datetime.now(UTC).isoformat()
    await get_pool().execute(
        "UPDATE intuition_models SET build = COALESCE(build, '{}'::jsonb) || $2::jsonb, updated_at=now() WHERE id=$1",
        model_id,
        build,
    )


async def _examples(model_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT id, item, label, note, split, message_id, created_at FROM intuition_examples
           WHERE model_id=$1 AND label IN ('good','bad') ORDER BY created_at""",
        model_id,
    )
    return [
        {
            **dict(r),
            "item": r["item"] if isinstance(r["item"], dict) else json.loads(r["item"]),
        }
        for r in rows
    ]


async def write_traits(model_id: UUID, examples: list[dict], said: list[str] = ()) -> dict:
    row = await get_pool().fetchrow(
        "SELECT name, instructions FROM intuition_models WHERE id=$1", model_id
    )
    content: list[dict] = [{"type": "text", "text": f"Eval: {row['name']}"}]
    if row["instructions"]:
        content.append({"type": "text", "text": f"What they want judged: {row['instructions']}"})
    if said:
        content.append(
            {
                "type": "text",
                "text": "What they said about their examples:\n"
                + "\n".join(f"- {s}" for s in said),
            }
        )
    seed = str(model_id)
    good = revise.sample([e for e in examples if e["label"] == "good"], TRAIT_GOOD, seed)
    bad = revise.sample([e for e in examples if e["label"] == "bad"], TRAIT_BAD, seed)

    def heading(kind: str, i: int, e: dict) -> dict:
        note = f" (their note: {e['note']})" if e.get("note") else ""
        return {"type": "text", "text": f"{kind} example {i}{note}:"}

    for i, e in enumerate(good, 1):
        content += [heading("Good", i, e), *await items.blocks(e["item"], 512)]
    closeups = [d for e in good for d in await items.image_bytes(e["item"])][:4]
    if closeups:
        content.append({"type": "text", "text": "Full-resolution close-ups from good examples:"})
        content += [items.closeup(d) for d in closeups]
    for i, e in enumerate(bad, 1):
        content += [heading("Bad", i, e), *await items.blocks(e["item"], 512)]
    content.append({"type": "text", "text": "Write the traits now."})
    reply = await llm._get_client().messages.create(
        model=judge.model(),
        max_tokens=4000,
        system=TRAITS_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in reply.content if b.type == "text")
    parsed = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    traits = [
        {
            "name": str(t["name"])[:60],
            "good": str(t.get("good", ""))[:400],
            "bad": str(t.get("bad", ""))[:400],
            **({"basis": str(t["basis"])[:300]} if t.get("basis") else {}),
        }
        for t in parsed.get("traits", [])[: revise.MAX_TRAITS]
        if isinstance(t, dict) and t.get("name")
    ]
    if not traits:
        raise ValueError("Could not write traits from these examples")
    return {"summary": str(parsed.get("summary", ""))[:500], "traits": traits}


async def _take_requests(model_id: UUID) -> list[str]:
    """The rubric changes the person asked for in the channel, taken once."""
    requests = await get_pool().fetchval(
        """WITH old AS (SELECT build->'requests' AS requests FROM intuition_models WHERE id=$1 FOR UPDATE)
           UPDATE intuition_models m SET build = m.build - 'requests' FROM old
           WHERE m.id=$1 RETURNING old.requests""",
        model_id,
    )
    return [str(r) for r in requests or []]


async def _return_requests(model_id: UUID, requests: list[str]) -> None:
    """Put back requests a failed build didn't apply, ahead of any that came in meanwhile."""
    await get_pool().execute(
        """UPDATE intuition_models SET build = jsonb_set(COALESCE(build, '{}'::jsonb), '{requests}',
                  $2::jsonb || COALESCE(build->'requests', '[]'::jsonb))
           WHERE id=$1""",
        model_id,
        requests,
    )


def _legacy(metrics: dict | None) -> dict:
    """The build's summary numbers: agreement over every example measured, and held-out alone."""
    if not metrics:
        return {"checked": 0, "agreement": None, "good_above_bad": None}
    fit, check = metrics["fit"], metrics["check"]
    n = fit["n"] + check["n"]
    return {
        "checked": n,
        "agreement": round((fit["right"] + check["right"]) / n, 3) if n else None,
        "good_above_bad": fit["good_above_bad"],
        "held_out": check,
    }


async def run(model_id: UUID, fresh: bool = False, reply_to: UUID | None = None) -> dict:
    examples = await _examples(model_id)
    if not examples:
        # Everything was unlabeled or removed since this was queued: nothing to build from.
        await _set(model_id, stage="done")
        return {"conflict": False, "empty": True}
    model = await get_pool().fetchrow(
        "SELECT name, instructions, traits FROM intuition_models WHERE id=$1", model_id
    )
    learn = [e for e in examples if e["split"] == "train"]
    if not learn:
        # Only held-out examples are labeled: those measure a rubric, they never write one.
        await _set(model_id, stage="done")
        return {"conflict": False, "empty": True}
    seed = str(model_id)
    version = await versions.current(model_id)
    start = version
    wrote = False
    if version is None and model["traits"] and not fresh:
        # Evals built before rubric versions keep their traits as version 1.
        version = await versions.save(
            model_id,
            after=0,
            traits=model["traits"],
            refs=judge.pick_refs(learn, seed),
            instructions=model["instructions"],
            source="written",
            changes=[],
        )
        start = version
    if version is None or fresh:
        await _set(model_id, stage="traits", done=0, total=0, error=None)
        written = await write_traits(model_id, learn, await revise.said(model_id))
        # A rewrite starts over from the evidence, but the traits the person wrote stay theirs.
        theirs = [
            {**t, "name": revise.NAME_NOTE.sub("", t["name"]).strip()}
            for t in (version or {}).get("traits", [])
            if t.get("by") == versions.PERSON
        ]
        version = await versions.save(
            model_id,
            after=version["number"] if version else 0,
            traits=revise.cap(revise.dedupe(theirs + written["traits"])),
            refs=judge.pick_refs(learn, seed),
            instructions=model["instructions"],
            source="written",
            changes=[{"kind": "write", "trait": "", "why": written["summary"]}],
            scoring=(version or {}).get("scoring", "mean"),
        )
        await _set(model_id, summary=written["summary"])
        wrote = True
    elif model["instructions"] != version["instructions"]:
        version = await versions.save(
            model_id,
            after=version["number"],
            traits=version["traits"],
            refs=version["refs"],
            instructions=model["instructions"],
            source="edited",
            changes=[{"kind": "description", "trait": "", "why": "The description changed"}],
            scoring=version["scoring"],
        )
    if version is None:
        # The person saved a version while this ran; their save queued another build.
        await _set(model_id, stage="done")
        return {"conflict": True}

    async def progress(stage: str, done: int = 0, total: int = 0) -> None:
        await _set(model_id, stage=stage, done=done, total=total)

    requested = {"saved": [], "unchanged": []}
    requests = await _take_requests(model_id)
    if requests:
        try:
            requested = await revise.apply_requests(model_id, version, examples, requests, progress)
        except Exception:
            await _return_requests(model_id, requests)
            raise
        if requested["conflict"]:
            # The person saved a version meanwhile; their save queued a build that applies these.
            await _return_requests(model_id, requests)
            await _set(model_id, stage="done")
            return {"conflict": True}
        version = requested["version"]
    result = await revise.revise(model_id, version, examples, progress)
    result = {
        **result,
        "saved": requested["saved"] + result["saved"],
        "unchanged_requests": requested["unchanged"],
    }
    if result["conflict"]:
        await _set(model_id, stage="done", metrics=_legacy(result.get("metrics")))
        return result
    short = result["cut_short"]
    latest = await versions.current(model_id)
    if short and (latest or {}).get("number") == (start or {}).get("number"):
        # The judge went away before anything changed: a failed build, and the panel says so.
        raise judge.JudgeUnavailable(
            f"The judge graded {short['graded']} of {short['of']} examples; the rubric is unchanged"
        )
    await progress("checking")
    try:
        manipulation = await check_manipulation(model_id, examples)
    except Exception:
        log.exception("The manipulation check failed for %s", model_id)
        manipulation = None
    await _set(model_id, stage="done", metrics=_legacy(result.get("metrics")))
    try:
        thread = await _thread(model_id, reply_to)
        if thread is not None:
            await announce(model_id, start, result, wrote, thread)
            if manipulation and manipulation["resisted"] < manipulation["n"]:
                await warn_manipulation(model_id, manipulation, thread)
        await ask_about(model_id, result["misses"])
    except Exception:
        # The rubric is saved either way; a channel post that failed doesn't fail the build.
        log.exception("Announcing the rubric build failed for %s", model_id)
    return result


async def check_manipulation(model_id: UUID, examples: list[dict]) -> dict | None:
    """Once per rubric version: try to talk the judge into passing bad work (robustness.py)
    and keep the result on the version. Returns it when this build ran the check."""
    final = await versions.current(model_id)
    if final is None or (final["metrics"] or {}).get("manipulation"):
        return None
    bad = [e for e in examples if e["split"] == "train" and e["label"] == "bad"]
    found = await robustness.check(model_id, final, bad)
    if found is not None:
        await versions.set_metrics(final["id"], {"manipulation": found})
    return found


async def _thread(model_id: UUID, reply_to: UUID | None) -> UUID | None:
    """The channel thread to report in: the one the evidence came from, if it still exists."""
    if reply_to is None:
        return None
    return await get_pool().fetchval(
        "SELECT COALESCE(thread_id, id) FROM eval_messages WHERE id=$1 AND model_id=$2",
        reply_to,
        model_id,
    )


async def warn_manipulation(model_id: UUID, found: dict, thread: UUID) -> None:
    worst = found["worst"]
    await channel.post_agent(
        model_id,
        f"{found['n'] - found['resisted']} of {found['n']} attempts to talk the judge into passing "
        f"bad work got through: bad work scored {worst['score']:.2f} with this added: "
        f'"{worst["claim"]}"',
        thread_id=thread,
        kind="rubric",
        data={"manipulation": found},
    )


def _agrees(after: dict | None, before: dict | None) -> str:
    if not after or not after["fit"]["n"]:
        return ""
    fit, check = after["fit"], after["check"]
    text = f" Agrees with {fit['right']} of {fit['n']} examples it learned from"
    if before and before["fit"]["n"]:
        text += f" (was {before['fit']['right']} of {before['fit']['n']})"
    if check["n"]:
        text += f", and {check['right']} of {check['n']} held out"
        if before and before["check"]["n"]:
            text += f" (was {before['check']['right']} of {before['check']['n']})"
    return text + "."


async def announce(
    model_id: UUID, start: dict | None, result: dict, wrote: bool, thread: UUID
) -> None:
    """One reply per build that changed the rubric, in the thread its evidence came from: what
    changed and the agreement before and after. A new description alone isn't reported."""
    final = result["version"]
    if result["unchanged_requests"]:
        await channel.post_agent(
            model_id,
            "I couldn't turn this into a rubric change: "
            + " / ".join(result["unchanged_requests"])
            + ". Edit the rubric directly, or say it another way.",
            thread_id=thread,
        )
    if not wrote and not result["saved"]:
        return
    changes = [c for v in result["saved"] for c in v["changes"]]
    edits = "; ".join(
        f"{VERBS.get(c['kind'], c['kind'])} {c['trait']}"
        + (" (as you asked)" if c.get("asked") else "")
        for c in changes
        if c.get("trait")
    )
    first = result["saved"][0] if result["saved"] else None
    if wrote and first is None:
        text = f"Wrote rubric v{final['number']}: {len(final['traits'])} traits."
    elif wrote:
        text = f"Wrote rubric v{first['number'] - 1}, then revised it to v{final['number']}: {edits or 'updated'}."
    else:
        text = f"Rubric v{final['number']}: {edits or 'updated'}."
    before = first["before"] if first else None
    text += _agrees(result.get("metrics"), before)
    if short := result.get("cut_short"):
        text += (
            f" The judge then graded only {short['graded']} of {short['of']} examples,"
            " so the check stopped there."
        )
    await channel.post_agent(
        model_id,
        text,
        thread_id=thread,
        kind="rubric",
        data={
            "version": final["number"],
            "from": start["number"] if start else None,
            "changes": changes,
            "metrics": result.get("metrics"),
            "before": before,
        },
    )


async def ask_about(model_id: UUID, misses: list[tuple[dict, dict]]) -> None:
    """Ask, once per example, why the person labeled one the rubric still gets wrong."""
    asked = {
        r["about"]
        for r in await get_pool().fetch(
            "SELECT data->>'about' AS about FROM eval_messages WHERE model_id=$1 AND data ? 'about'",
            model_id,
        )
    }
    posted = 0
    for e, grade in misses:
        if posted >= ASK_PER_BUILD:
            break
        if not e.get("message_id") or e.get("note") or str(e["id"]) in asked:
            continue
        message = await get_pool().fetchrow(
            "SELECT id, thread_id FROM eval_messages WHERE id=$1", e["message_id"]
        )
        if message is None:
            continue
        name = (e["item"].get("files") or [{}])[0].get("name") or "this one"
        verdict = "good" if grade["score"] >= 0.5 else "bad"
        await channel.post_agent(
            model_id,
            f"You marked {name} {e['label']}, but the rubric scores it {grade['score']:.2f} "
            f"({verdict}). What makes it {e['label']}?",
            thread_id=message["thread_id"] or message["id"],
            data={"about": str(e["id"])},
        )
        posted += 1
