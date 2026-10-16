"""Demo mode for the website taste eval (``TASTE_DEMO_MODE=1``).

The real grader is a linear head on frozen Qwen-VL activations fitted on Modal.
For product demos, the build step instead asks Claude to distill the user's
labeled feedback into preference rules and a SKILL.md, and every check-in is
scored by Claude against those rules. The result carries the same fields as a
real prediction, plus concrete feedback an agent can act on mid-task.

Demo graders are marked ``"demo": true`` so they are never mistaken for a
fitted probe. The real build and predict paths are unchanged when the flag is off.
"""

import asyncio
import base64
import hashlib
import json
import os
import re

from ..config import settings

MAX_REFERENCE_IMAGES = 6
# References shown to the judge on every check: screens the user liked and disliked.
JUDGE_REFERENCES_PER_LABEL = 2
APPROVE = 0.7
JUDGE_READS = 2


def enabled() -> bool:
    return os.environ.get("TASTE_DEMO_MODE") == "1"


def is_demo_grader(model: dict) -> bool:
    return bool(model.get("demo"))


def _json(text: str) -> dict:
    """The JSON object in a reply, tolerating code fences or prose around it."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


async def _ask(system: str, content: list, max_tokens: int) -> dict:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    for attempt in range(2):
        reply = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        try:
            if reply.stop_reason != "end_turn":
                raise ValueError("cut off")
            return _json("".join(c.text for c in reply.content if c.type == "text"))
        except (ValueError, json.JSONDecodeError):
            if attempt:
                raise ValueError("The grader did not return a readable verdict. Retry.") from None
    raise AssertionError("unreachable")


BUILD_SYSTEM = """You distill one person's design taste from example websites they chose: \
some they like and some they don't. You get labeled examples: a screenshot, whether they \
liked it or wanted it changed, and any words they gave. Write the rules a reviewer would \
need to predict their reaction to a new screen. Be specific and visual (layout, density, \
typography, color, controls, decoration), not generic ("clean", "modern"). Ground every rule \
in the examples; never invent taste they did not express.

Return only JSON:
{"preferences": [{"rule": str, "kind": "prefer" | "avoid", "evidence": [example id, ...]}],
 "skill": str}
6-10 preferences. "skill" is the markdown body of a SKILL.md an agent loads before building \
UI for this person: a short intro, then sections with concrete do/don't guidance."""


async def build(row, examples: list[dict], images: dict[str, str]) -> dict:
    """Write a demo grader from usable examples. Returns the grader document."""
    from scripts.website_taste.autolabel import pixels

    usable = [e for e in examples if e["usable"]]
    content: list = []
    shown = 0
    for e in usable:
        content.append(
            {
                "type": "text",
                "text": json.dumps(
                    {"id": e["id"], "label": e["label"], "their_words": e["quote"] or e["note"]}
                ),
            }
        )
        if shown < MAX_REFERENCE_IMAGES and images.get(e["id"]):
            content.append(pixels(images[e["id"]]))
            shown += 1
    content.append({"type": "text", "text": "Write the preferences and skill now."})
    result = await _ask(BUILD_SYSTEM, content, 4000)
    known = {e["id"] for e in usable}
    preferences = [
        {
            "rule": p["rule"],
            "kind": "avoid" if p.get("kind") == "avoid" else "prefer",
            "evidence": [i for i in p.get("evidence", []) if i in known],
        }
        for p in result.get("preferences", [])
        if p.get("rule")
    ]
    if not preferences:
        raise ValueError("Could not distill preferences from your feedback.")
    digest = hashlib.sha256(json.dumps(preferences, sort_keys=True).encode()).hexdigest()
    return {
        "demo": True,
        "version": f"taste-{row['revision']}-{digest[:8]}",
        "spec": {"kind": "claude_judge", "model": settings.ANTHROPIC_MODEL},
        "preferences": preferences,
        "skill": result.get("skill", ""),
        "examples": {
            "liked": sum(e["label"] == "liked" for e in usable),
            "disliked": sum(e["label"] == "disliked" for e in usable),
        },
        "release_gate": {"passed": True, "checks": {}},
        "metrics": None,
        "limitations": [],
    }


JUDGE_SYSTEM = """You are a personal design grader. You predict whether one specific person \
would approve a screen their coding agent built, using only their preferences below. You \
see the task, what the agent has done so far, and a screenshot of the current work. The \
work may be unfinished; judge what is on screen.

Their preferences:
{rules}

Also judge execution, the way they would on close inspection: sloppy execution reads as \
vibecoded even when the style is right. Look for items in a row whose text baselines or \
vertical centers don't line up; summary rows, toolbars or headers that wrap awkwardly onto a \
second line; text or labels that are clipped, truncated, overlapping, or run off an edge; and \
inconsistent spacing between similar elements. Each clear execution flaw is a fix, named \
precisely (which element, what is wrong). Visible execution flaws block approval: while \
any remain, score below 70 even if the style is right.

You may also see reference screens they explicitly liked and wanted changed. Compare the current work against them: closer to the liked references is better.

Score how likely they are to approve, 0-100:
- 0-15: breaks several "avoid" rules outright (they would call it slop or vibecoded)
- 15-40: some rules followed, but the overall impression is still what they dislike
- 40-70: mostly right with a few clear violations
- 70-90: they would approve with small nits
- 90-100: exemplary; matches what they called "goals"
Be strict and consistent: the same screen always gets the same score.

Return only JSON:
{{"score": int,
  "summary": str (one sentence, plain words, what they would say),
  "fixes": [{{"issue": str, "fix": str}}] (the 1-4 changes that would raise the score most, \
most important first; concrete enough to act on in CSS/HTML; empty if score >= 90),
  "keep": [str] (0-3 things already right, to preserve)}}"""


def references(examples: list[dict], images: dict) -> list[tuple[str, object]]:
    """Pick a few liked and disliked screens, with their images, as contrastive references."""
    picked = []
    for label in ("liked", "disliked"):
        rows = [e for e in examples if e["usable"] and e["label"] == label and e["id"] in images]
        rows.sort(key=lambda e: (not e["reviewed"], -len(e["quote"] or "")))
        picked += [(label, images[e["id"]]) for e in rows[:JUDGE_REFERENCES_PER_LABEL]]
    return picked


async def judge(model: dict, item: dict, image_path, refs=()) -> dict:
    """Score current work against the demo grader's preferences and reference screens."""
    from scripts.website_taste.autolabel import pixels

    rules = "\n".join(
        f"- {'AVOID' if p['kind'] == 'avoid' else 'PREFER'}: {p['rule']}"
        for p in model["preferences"]
    )
    steps = "\n".join(f"[{s['role']}] {s['text'][:600]}" for s in item["trace"][-12:])
    raw = image_path.read_bytes()
    media = "image/jpeg" if raw.startswith(b"\xff\xd8\xff") else "image/png"
    content: list = []
    for label, path in refs:
        content += [
            {
                "type": "text",
                "text": f"Reference screen they {'liked' if label == 'liked' else 'wanted changed'}:",
            },
            pixels(path),
        ]
    content += [
        {
            "type": "text",
            "text": f"Now the work to grade. Task: {item['brief']}\n\nAgent trace so far"
            f"{' (complete)' if item.get('trace_complete') else ' (in progress)'}:\n{steps}",
        },
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media,
                "data": base64.b64encode(raw).decode(),
            },
        },
    ]
    # Two independent reads, averaged: a single read of the same screen can swing widely.
    reads = await asyncio.gather(
        *(_ask(JUDGE_SYSTEM.format(rules=rules), content, 1200) for _ in range(JUDGE_READS))
    )
    scores = [max(0, min(100, int(r.get("score", 0)))) for r in reads]
    result = reads[scores.index(min(scores))]  # the stricter read's feedback
    score = sum(scores) / len(scores) / 100
    return {
        "label": "liked" if score >= 0.5 else "disliked",
        "score": round(score, 3),
        "approved": score >= APPROVE,
        "summary": str(result.get("summary", ""))[:400],
        "fixes": [
            {"issue": str(f.get("issue", ""))[:300], "fix": str(f.get("fix", ""))[:400]}
            for f in result.get("fixes", [])[:4]
        ],
        "keep": [str(k)[:200] for k in result.get("keep", [])[:3]],
        "note": "Scored by your taste grader against the preferences learned from your examples.",
    }
