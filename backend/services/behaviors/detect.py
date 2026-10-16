"""Custom behaviors: a model reads a segment and tags the windows where the behavior happens.

A team describes a behavior in words (and optionally a few example quotes); the
detector reads one segment at a time -- a user turn and the agent's work until
the next one -- and returns step windows with verbatim evidence. Segments most
like the definition go first, so a capped pass spends its calls where hits are
likely; segments already read for this behavior version are never read again.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from .. import embeddings, llm

MAX_SEGMENTS_PER_PASS = 12

SYSTEM = """You tag one behavior in a segment of an agent's trajectory.

You get the behavior's name, who exhibits it (the user, the agent, or the environment the agent's tools talk to), its definition, optional examples, and one segment of the trace. Each step in the segment starts with its index in brackets, like [12].

Tag every window of consecutive steps where the behavior clearly happens. A window is the smallest step range that shows it: start_idx is the first step that shows it, end_idx the last. Quote the steps that show it verbatim (under 200 characters each). Tag only what is observable in the segment; when it is ambiguous, leave it out or give a low confidence. Return no hits when the behavior does not happen.

When people have confirmed or rejected earlier hits, those verdicts show where the line is: follow them over your own reading of the definition."""


class Evidence(BaseModel):
    idx: int
    quote: str = Field(max_length=400)


class Hit(BaseModel):
    start_idx: int
    end_idx: int
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence]
    note: str = Field(default="", max_length=400)


class Detection(BaseModel):
    hits: list[Hit]


def describe(behavior: dict) -> str:
    lines = [
        f"BEHAVIOR: {behavior['name']}",
        f"EXHIBITED BY: {behavior['actor']}",
        f"DEFINITION: {behavior['definition']}",
    ]
    examples = [e for e in behavior.get("examples") or [] if isinstance(e, str) and e.strip()]
    if examples:
        lines.append("EXAMPLES:\n" + "\n".join(f"- {e}" for e in examples[:8]))
    return "\n".join(lines)


async def rank(behavior: dict, segments: list[dict]) -> list[dict]:
    """Segments ordered by similarity to the behavior; unchanged order without embeddings."""
    if len(segments) <= 1 or not embeddings.is_configured():
        return segments
    vecs = await embeddings.embed_batch([describe(behavior)] + [s["text"] for s in segments])
    if not vecs:
        return segments
    query = vecs[0] / (np.linalg.norm(vecs[0]) or 1.0)
    scores = [float(np.dot(query, v / (np.linalg.norm(v) or 1.0))) for v in vecs[1:]]
    order = sorted(range(len(segments)), key=lambda i: -scores[i])
    return [segments[i] for i in order]


MAX_REVIEWED = 4
REVIEW_CHARS = 900


async def reviewed(behavior: dict) -> str:
    """People's verdicts on earlier hits, as examples: confirmed windows show what
    the behavior looks like, rejected ones what it is not. Reviews teach the
    detector without anyone editing its definition."""
    from ...database import get_pool
    from .segments import clip, render_step

    pool = get_pool()
    blocks = []
    for verdict, heading in (
        ("confirmed", "CONFIRMED BY A PERSON (this is the behavior)"),
        ("rejected", "REJECTED BY A PERSON (this is NOT the behavior)"),
    ):
        hits = await pool.fetch(
            """SELECT trace_id, start_idx, end_idx,
                      CASE WHEN source = 'human' THEN note ELSE review_note END AS note FROM behavior_hits
               WHERE behavior_id = $1 AND review = $2 ORDER BY created_at DESC LIMIT $3""",
            behavior["id"], verdict, MAX_REVIEWED,
        )  # fmt: skip
        shown = []
        for h in hits:
            steps = await pool.fetch(
                "SELECT idx, role, content, tool_name, tool_input FROM rm_trace_steps WHERE trace_id = $1 AND idx BETWEEN $2 AND $3 ORDER BY idx",
                h["trace_id"], h["start_idx"], h["end_idx"],
            )  # fmt: skip
            text = clip("\n".join(render_step(dict(st), 400) for st in steps), REVIEW_CHARS)
            shown.append(text + (f"\nREVIEWER NOTE: {h['note']}" if h["note"] else ""))
        if shown:
            blocks.append(heading + ":\n" + "\n---\n".join(shown))
    return "\n\n".join(blocks)


async def classify(behavior: dict, segment: dict, reviews: str = "") -> list[dict]:
    result = await llm.complete_structured(
        prompt="\n\n".join(
            part
            for part in (
                describe(behavior),
                reviews,
                f"SEGMENT (steps {segment['start_idx']}–{segment['end_idx']}):\n\n{segment['text']}",
            )
            if part
        ),
        system=SYSTEM,
        output_model=Detection,
        tier=llm.ModelTier.FAST,
        max_tokens=2000,
    )
    lo, hi = segment["start_idx"], segment["end_idx"]
    hits = []
    for hit in result.hits:
        start, end = (
            max(lo, min(hit.start_idx, hit.end_idx)),
            min(hi, max(hit.start_idx, hit.end_idx)),
        )
        if start > end:
            continue  # The window points outside the segment it was read from.
        hits.append(
            {
                "start_idx": start,
                "end_idx": end,
                "confidence": hit.confidence,
                "evidence": [e.model_dump() for e in hit.evidence if lo <= e.idx <= hi][:6],
                "note": hit.note,
            }
        )
    return hits


async def detect(
    behavior: dict, segments: list[dict], seen: set[str]
) -> tuple[list[dict], set[str]]:
    """Hits in segments not yet read, and the content hashes now read."""
    todo = await rank(behavior, [s for s in segments if s["content_hash"] not in seen])
    hits: list[dict] = []
    read = set(seen)
    reviews = await reviewed(behavior) if todo and behavior.get("id") else ""
    for segment in todo[:MAX_SEGMENTS_PER_PASS]:
        hits.extend(await classify(behavior, segment, reviews))
        read.add(segment["content_hash"])
    return hits, read
