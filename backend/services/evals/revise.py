"""Revise a judge eval's rubric from its evidence, pass by pass, keeping only what helps.

A rubric is measured on labeled examples: each is graded with itself left out of the
references, and a score of 0.5 or more counts as good. Examples are split when added
(service.splits): the rubric is written and revised from the 'train' ones, and the held-out
'eval' ones only measure it, so an edit that just memorizes the latest examples shows up.

Each pass shows an analysis model the learned-from examples the judge gets wrong (with the
person's notes and what they said in the channel), a few it gets right, and the edits already
tried and rejected. It proposes at most three focused edits, each grounded in that evidence:
add a missing trait, tighten vague wording, fix wording that passes bad work or fails good
work, point a trait at the evidence to look at, or remove a misleading one. The edited rubric
is graded on the misses first (if it fixes none, the pass ends there), then on a sample of the
examples the current rubric gets right and on the held-out ones, and is kept only when it gets
more learned-from examples right without getting fewer held-out ones right. Passes stop after
PATIENCE without a gain.

Changes the person asks for in the channel are applied as asked whatever the agreement does,
and reported with it. Traits the person wrote or changed are kept word for word by every
revision that wasn't asked for.
"""

import asyncio
import json
import logging
import random
import re
from collections.abc import Awaitable, Callable
from uuid import UUID

from ...database import get_pool
from .. import llm
from . import items, judge, versions

log = logging.getLogger(__name__)

MAX_FIT = 24  # learned-from examples each rubric is measured on
MAX_CHECK = 12  # held-out examples each rubric is measured on
MAX_PASSES = 3
PATIENCE = 2
SHOW_WRONG = 8  # misses shown to the analysis model, with their files
SHOW_RIGHT = 4
KEEP_RIGHT = 8  # examples the current rubric gets right that a candidate is checked on
MAX_TRAITS = 8
CONCURRENCY = 4
SAID = 40
NOTES = 40

Progress = Callable[..., Awaitable[None]]

SYSTEM = """You maintain the rubric an AI judge uses to grade an agent's work the way one \
person would. The judge grades the work 1-5 on each trait, beside the person's good and bad \
examples; the mean grade scaled to 0-1 is the score, and 0.5 or more means good.

You see the rubric, examples the judge gets wrong (what the person said about each and what \
the judge said), a few it gets right, notes the person left on examples, and what they said in \
their channel. Find the pattern behind the mistakes, not one-off fixes, and make at most three \
focused edits:
- add: a trait the rubric is missing
- tighten: sharpen a trait's wording so it separates the cases it now confuses
- fix: change wording that makes the judge pass bad work or fail good work
- point: tell a trait which evidence to look at (the agent's tool results rather than its own \
summary, a part of the screenshot)
- remove: drop a trait that misleads the judge
Each trait names one property you can see in the work, never the verdict itself, and says \
concretely what good and bad look like here, specific enough that two judges would grade the \
same work the same way. Ground every edit in the evidence: its why names the examples or the \
person's words it comes from. Keep traits that work unchanged, word for word. Traits marked \
(the person's) are theirs: keep them exactly. 3-8 traits in total. Nothing about signatures, \
handles or watermarks.

Return only JSON: {"changes": [{"kind": "add"|"tighten"|"fix"|"point"|"remove", "trait": str \
(the trait's name), "why": str (one sentence: the evidence)}], "traits": [{"name": str (2-4 \
words), "good": str, "bad": str, "basis": str (one sentence: the evidence it rests on)}]} \
where traits is the whole rubric after your edits, in order."""

REQUEST = """The person asked for this change to the rubric: {request}
Make exactly the change they asked for and nothing else. Each change's kind is "request" and \
its why quotes them. Keep every other trait word for word."""


def sample(examples: list[dict], n: int, seed: str) -> list[dict]:
    """Up to n examples: the newest half, and a fixed-seed sample of the older ones."""
    if len(examples) <= n:
        return list(examples)
    ordered = sorted(examples, key=lambda e: e["created_at"])
    newest = ordered[len(ordered) - n // 2 :]
    older = ordered[: len(ordered) - n // 2]
    return random.Random(seed).sample(older, n - len(newest)) + newest


def right(example: dict, grade: dict) -> bool:
    return (grade["score"] >= 0.5) == (example["label"] == "good")


def tally(examples: list[dict], grades: dict) -> dict:
    scored = [(e, grades[e["id"]]) for e in examples if e["id"] in grades]
    good = [g["score"] for e, g in scored if e["label"] == "good"]
    bad = [g["score"] for e, g in scored if e["label"] == "bad"]
    pairs = [(a > b) + 0.5 * (a == b) for a in good for b in bad]
    n_right = sum(right(e, g) for e, g in scored)
    return {
        "n": len(scored),
        "right": n_right,
        "agreement": round(n_right / len(scored), 3) if scored else None,
        "good_above_bad": round(sum(pairs) / len(pairs), 3) if pairs else None,
    }


def _both(examples: list[dict], a: dict, b: dict) -> list[dict]:
    """The examples both rubrics graded, so a judge outage on one never decides a comparison."""
    return [e for e in examples if e["id"] in a and e["id"] in b]


async def grades(
    model_id: UUID,
    version: dict,
    examples: list[dict],
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> dict[UUID, dict]:
    """The rubric's grade for each example, from the cache or the judge (examples the judge
    couldn't grade are left out)."""
    rubric_key = await judge.rubric_key(model_id, version)
    have = await versions.cached(model_id, rubric_key, [e["id"] for e in examples])
    todo = [e for e in examples if e["id"] not in have]
    gate = asyncio.Semaphore(CONCURRENCY)
    fresh: dict[UUID, dict] = {}

    async def one(e: dict) -> None:
        async with gate:
            try:
                result = await judge.grade(model_id, e["item"], exclude=e["id"], version=version)
            except judge.JudgeUnavailable:
                return
        fresh[e["id"]] = {k: result[k] for k in ("score", "traits", "explanation")}
        if on_progress:
            await on_progress(len(fresh), len(todo))

    await asyncio.gather(*(one(e) for e in todo))
    await versions.remember(model_id, rubric_key, fresh)
    return {**have, **fresh}


async def said(model_id: UUID) -> list[str]:
    """What the person wrote in the channel, oldest first, leaving out what they said about
    held-out examples only (a message whose files are all held out, and replies in its
    thread): the rubric never learns from those."""
    rows = await get_pool().fetch(
        """SELECT m.text FROM eval_messages m
           WHERE m.model_id=$1 AND m.author='user' AND m.text <> ''
             AND NOT EXISTS (
                 SELECT 1 FROM intuition_examples e
                 WHERE e.message_id = COALESCE(m.thread_id, m.id)
                 HAVING count(*) > 0 AND bool_and(e.split = 'eval')
             )
           ORDER BY m.created_at DESC LIMIT $2""",
        model_id,
        SAID,
    )
    return [r["text"][:600] for r in reversed(rows)]


def _traits_text(traits: list[dict]) -> str:
    return "\n".join(
        f"- {t['name']}{' (the person' + chr(39) + 's)' if t.get('by') == versions.PERSON else ''}: "
        f"good = {t.get('good', '')}; bad = {t.get('bad', '')}"
        + (f"; basis: {t['basis']}" if t.get("basis") else "")
        for t in traits
    )


async def _content(
    name: str,
    version: dict,
    wrong: list[tuple[dict, dict]],
    shown_right: list[tuple[dict, dict]],
    tried: list[str],
    channel: list[str],
    notes: list[str],
    request: str | None,
) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": f"Eval: {name}"}]
    if version["instructions"]:
        content.append(
            {"type": "text", "text": f"What they want judged: {version['instructions']}"}
        )
    content.append({"type": "text", "text": "Current rubric:\n" + _traits_text(version["traits"])})
    if channel:
        content.append(
            {
                "type": "text",
                "text": "What the person said in the channel (oldest first):\n"
                + "\n".join(f"- {s}" for s in channel),
            }
        )
    if notes:
        content.append(
            {
                "type": "text",
                "text": "Their notes on examples:\n" + "\n".join(f"- {n}" for n in notes),
            }
        )
    for i, (e, g) in enumerate(wrong, 1):
        line = (
            f"Miss {i}: they marked it {e['label']}; the judge scored it {g['score']:.2f}. "
            f"The judge said: {g.get('explanation', '')}"
        )
        if e.get("note"):
            line += f" Their note: {e['note']}"
        content += [{"type": "text", "text": line}, *await items.blocks(e["item"], 512)]
    for i, (e, g) in enumerate(shown_right, 1):
        content += [
            {
                "type": "text",
                "text": f"Judged right {i}: they marked it {e['label']}; scored {g['score']:.2f}.",
            },
            *await items.blocks(e["item"], 512),
        ]
    if tried:
        content.append(
            {
                "type": "text",
                "text": "Edits already tried and rejected (they didn't get more examples right):\n"
                + "\n".join(f"- {t}" for t in tried),
            }
        )
    content.append(
        {
            "type": "text",
            "text": REQUEST.format(request=request) if request else "Make your edits now.",
        }
    )
    return content


def parse(text: str) -> tuple[list[dict], list[dict]]:
    """(traits, changes) from the analysis model's reply."""
    parsed = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    traits = [
        {
            "name": str(t["name"]).strip()[:60],
            "good": str(t.get("good", ""))[:400],
            "bad": str(t.get("bad", ""))[:400],
            "basis": str(t.get("basis", ""))[:300],
        }
        for t in parsed.get("traits", [])[: MAX_TRAITS + 2]
        if isinstance(t, dict) and str(t.get("name", "")).strip()
    ]
    changes = [
        {
            "kind": str(c.get("kind", "fix"))[:20],
            "trait": str(c.get("trait", ""))[:60],
            "why": str(c.get("why", ""))[:400],
        }
        for c in parsed.get("changes", [])[:6]
        if isinstance(c, dict)
    ]
    if not traits:
        raise ValueError("The proposal had no traits")
    return traits, changes


def same(a: list[dict], b: list[dict]) -> bool:
    fields = lambda ts: [tuple(t.get(k, "") for k in ("name", "good", "bad")) for t in ts]  # noqa: E731
    return fields(a) == fields(b)


def keep_theirs(current: list[dict], proposed: list[dict]) -> list[dict]:
    """The proposal with the person's own traits exactly as they wrote them, put back if dropped."""
    theirs = {t["name"].lower(): t for t in current if t.get("by") == versions.PERSON}
    out = [theirs.get(t["name"].lower(), t) for t in proposed]
    named = {t["name"].lower() for t in out}
    return out + [t for key, t in theirs.items() if key not in named]


def mark_theirs(current: list[dict], proposed: list[dict]) -> list[dict]:
    """After a change the person asked for: the traits it added or changed are theirs."""
    old = {t["name"].lower(): t for t in current}
    out = []
    for t in proposed:
        prior = old.get(t["name"].lower())
        unchanged = prior and all(prior.get(k, "") == t.get(k, "") for k in ("name", "good", "bad"))
        out.append(prior if unchanged else {**t, "by": versions.PERSON})
    return out


async def propose(
    model_id: UUID,
    version: dict,
    wrong: list[tuple[dict, dict]],
    shown_right: list[tuple[dict, dict]],
    tried: list[str],
    channel: list[str],
    notes: list[str],
    request: str | None = None,
) -> tuple[list[dict], list[dict]]:
    name = await get_pool().fetchval("SELECT name FROM intuition_models WHERE id=$1", model_id)
    content = await _content(name, version, wrong, shown_right, tried, channel, notes, request)
    reply = await llm._get_client().messages.create(
        model=judge.model(),
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    return parse("".join(b.text for b in reply.content if b.type == "text"))


def _tried(changes: list[dict], fixed: int, missed: int) -> str:
    edits = ", ".join(f"{c['kind']} {c['trait']}" for c in changes) or "no edits"
    return f"{edits}: fixed {fixed} of {missed} misses"


def _measured(model_id: UUID, examples: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(every learned-from example, the learned-from ones measured, the held-out ones measured)."""
    seed = str(model_id)
    fit_all = [e for e in examples if e["split"] == "train"]
    fit = sample(fit_all, MAX_FIT, seed)
    check = sample([e for e in examples if e["split"] == "eval"], MAX_CHECK, seed)
    return fit_all, fit, check


def _kind(name: str, before: list[dict], after: list[dict]) -> str:
    """What a change the person asked for did to the trait it names."""
    had = {t["name"].lower() for t in before}
    has = {t["name"].lower() for t in after}
    if name.lower() not in had and name.lower() in has:
        return "add"
    if name.lower() in had and name.lower() not in has:
        return "remove"
    return "tighten" if name else "request"


async def apply_requests(
    model_id: UUID, version: dict, examples: list[dict], requests: list[str], progress: Progress
) -> dict:
    """Apply the rubric changes the person asked for, as asked, whatever the agreement does.

    Returns {"version", "saved" (with the "before" metrics), "unchanged" (requests that
    changed nothing), "conflict"}. Raises when no change could be proposed, so the build can
    keep the requests for its next run instead of dropping them."""
    fit_all, fit, check = _measured(model_id, examples)
    measured = fit + check
    notes = [f"({e['label']}) {e['note']}" for e in fit_all if e.get("note")][-NOTES:]
    done = {"version": version, "saved": [], "unchanged": [], "conflict": False}
    await progress("revising", 0, 0)
    traits, changes = await propose(
        model_id, version, [], [], [], await said(model_id), notes, request=" / ".join(requests)
    )
    traits = mark_theirs(version["traits"], traits)[: MAX_TRAITS + 2]
    if same(traits, version["traits"]):
        return {**done, "unchanged": list(requests)}

    async def checking(d: int, t: int) -> None:
        await progress("checking", d, t)

    both_labels = {e["label"] for e in fit} == {"good", "bad"}
    before = await grades(model_id, version, measured, checking) if both_labels else {}
    after = (
        await grades(model_id, {**version, "traits": traits}, measured, checking)
        if both_labels
        else {}
    )
    new = await versions.save(
        model_id,
        after=version["number"],
        traits=traits,
        refs=version["refs"],
        instructions=version["instructions"],
        source="edited",
        changes=[
            {**c, "kind": _kind(c["trait"], version["traits"], traits), "asked": True}
            for c in changes
        ]
        or [{"kind": "request", "trait": "", "why": " / ".join(requests), "asked": True}],
        metrics={"fit": tally(fit, after), "check": tally(check, after)},
    )
    if new is None:
        return {**done, "conflict": True}
    before_metrics = {"fit": tally(fit, before), "check": tally(check, before)}
    return {**done, "version": new, "saved": [{**new, "before": before_metrics}]}


async def revise(model_id: UUID, version: dict, examples: list[dict], progress: Progress) -> dict:
    """Bring `version` up to date with the labeled `examples`.

    Returns {"version": the current version after, "saved": [new versions, each with the
    "before" metrics of the one it replaced], "metrics": {"fit", "check"} (None with only one
    kind of example), "misses": [(example, grade)] the current rubric still gets wrong among
    learned-from examples, "conflict": bool (the person saved a version meanwhile; the build
    should run again)}."""
    seed = str(model_id)
    fit_all, fit, check = _measured(model_id, examples)
    measured = fit + check
    channel = await said(model_id)
    notes = [f"({e['label']}) {e['note']}" for e in fit_all if e.get("note")][-NOTES:]
    saved: list[dict] = []
    done: dict = {"version": version, "saved": saved, "misses": [], "conflict": False}

    async def checking(d: int, t: int) -> None:
        await progress("checking", d, t)

    if {e["label"] for e in fit} != {"good", "bad"}:
        # Nothing to separate yet: with one kind of example there is no mistake to learn from.
        return {**done, "metrics": None}

    await progress("checking", 0, len(measured))
    current = await grades(model_id, version, measured, checking)
    tried: list[str] = []
    stale = 0
    for n in range(1, MAX_PASSES + 1):
        wrong = [e for e in fit if e["id"] in current and not right(e, current[e["id"]])]
        if not wrong or stale >= PATIENCE:
            break
        await progress("revising", n, MAX_PASSES)
        correct = [e for e in fit if e["id"] in current and right(e, current[e["id"]])]
        rng = random.Random(f"{seed}:{n}")
        shown: list[dict] = []
        for label in ("good", "bad"):
            pool = [e for e in correct if e["label"] == label]
            shown += rng.sample(pool, min(SHOW_RIGHT // 2, len(pool)))
        try:
            traits, changes = await propose(
                model_id,
                version,
                [(e, current[e["id"]]) for e in wrong[:SHOW_WRONG]],
                [(e, current[e["id"]]) for e in shown],
                tried,
                channel,
                notes,
            )
        except Exception:
            log.warning("Rubric proposal failed for %s (pass %d)", model_id, n, exc_info=True)
            stale += 1
            continue
        traits = keep_theirs(version["traits"], traits)[: MAX_TRAITS + 2]
        if same(traits, version["traits"]):
            tried.append(_tried(changes, 0, len(wrong)) + " (no change to the rubric)")
            stale += 1
            continue
        candidate = {
            "traits": traits,
            "refs": judge.pick_refs(fit_all, seed),
            "instructions": version["instructions"],
        }
        # The misses first: a rubric that fixes none of them isn't worth grading further.
        new_grades = await grades(model_id, candidate, wrong)
        fixed = sum(right(e, new_grades[e["id"]]) for e in wrong if e["id"] in new_grades)
        if fixed == 0:
            tried.append(_tried(changes, 0, len(wrong)))
            stale += 1
            continue
        keep = sample(correct, KEEP_RIGHT, f"{seed}:{n}")
        new_grades |= await grades(model_id, candidate, keep + check)
        on_fit = _both(wrong + keep, current, new_grades)
        on_check = _both(check, current, new_grades)
        gained = tally(on_fit, new_grades)["right"] > tally(on_fit, current)["right"]
        held = tally(on_check, new_grades)["right"] >= tally(on_check, current)["right"]
        if not (gained and held):
            tried.append(
                _tried(changes, fixed, len(wrong)) + ("" if held else ", lost held-out examples")
            )
            stale += 1
            continue
        # Kept: measure it on everything the current rubric was measured on, then save it.
        new_grades |= await grades(model_id, candidate, measured)
        new = await versions.save(
            model_id,
            after=version["number"],
            traits=traits,
            refs=candidate["refs"],
            instructions=version["instructions"],
            source="revised",
            changes=changes,
            metrics={"fit": tally(fit, new_grades), "check": tally(check, new_grades)},
        )
        if new is None:
            return {**done, "version": version, "conflict": True}
        saved.append(
            {**new, "before": {"fit": tally(fit, current), "check": tally(check, current)}}
        )
        version, current, stale = new, new_grades, 0

    metrics = {"fit": tally(fit, current), "check": tally(check, current)}
    await versions.set_metrics(version["id"], metrics)
    misses = [
        (e, current[e["id"]]) for e in fit if e["id"] in current and not right(e, current[e["id"]])
    ]
    return {**done, "version": version, "metrics": metrics, "misses": misses}
