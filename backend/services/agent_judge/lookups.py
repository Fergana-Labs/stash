"""Search beyond the trajectory: similar runs, what was decided about them, and connected sources.

- similar_traces: other traces where the same thing happened, by segment meaning.
- prior_labels: what people and earlier judges concluded about those traces --
  eval labels, reviewed behavior hits, and Agent Judge claim verdicts -- so a
  worker can see how a similar case was called before, and where judges and
  people disagreed.
- sources: a read-only shell over the owner's Stash filesystem (connected
  sources included), for facts about the systems the agent acted on. It runs
  with a short-lived read-only key, so it can see only what the owner can and
  change nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from ...database import get_pool
from .. import embeddings
from ..behaviors.search import quote
from ..behaviors.segments import clip

SIMILAR = 5
SOURCE_CHARS = 8_000
SCRIPT_CHARS = 500


async def _similar(owner_id: UUID, query: str, exclude: UUID | None) -> list[dict]:
    if not embeddings.is_configured():
        return []
    vector = await embeddings.embed_text(query)
    if vector is None:
        return []
    rows = await get_pool().fetch(
        """SELECT DISTINCT ON (s.trace_id) s.trace_id, s.start_idx, s.end_idx, s.text, t.title,
                  1 - (s.embedding <=> $2) AS score
           FROM rm_trace_segments s JOIN rm_traces t ON t.id = s.trace_id
           WHERE s.owner_user_id = $1 AND s.embedding IS NOT NULL AND ($3::uuid IS NULL OR s.trace_id <> $3)
           ORDER BY s.trace_id, s.embedding <=> $2""",
        owner_id,
        vector,
        exclude,
    )
    return sorted((dict(r) for r in rows), key=lambda r: -r["score"])[:SIMILAR]


async def similar_traces(owner_id: UUID | None, query: str, exclude: UUID | None) -> str:
    if owner_id is None:
        return "Unavailable: no owner to search."
    found = await _similar(owner_id, query, exclude)
    if not found:
        return "No similar traces found."
    return "\n".join(
        f"- trace {r['trace_id']} “{r['title'] or 'Untitled'}” steps {r['start_idx'] + 1}–{r['end_idx'] + 1} "
        f"(similarity {r['score']:.2f}): {quote(r['text'], query)}"
        for r in found
    )


async def prior_labels(owner_id: UUID | None, query: str, exclude: UUID | None) -> str:
    if owner_id is None:
        return "Unavailable: no owner to search."
    found = await _similar(owner_id, query, exclude)
    if not found:
        return "No similar traces with prior labels."
    ids = [r["trace_id"] for r in found]
    pool = get_pool()
    labels = await pool.fetch(
        """SELECT e.item->>'trace_id' AS trace_id, m.name, e.label, e.note FROM intuition_examples e
           JOIN intuition_models m ON m.id = e.model_id
           WHERE m.owner_user_id = $1 AND e.label IS NOT NULL AND e.item->>'trace_id' = ANY($2::text[])""",
        owner_id,
        [str(i) for i in ids],
    )
    reviews = await pool.fetch(
        """SELECT h.trace_id, b.name, h.review, h.start_idx, h.end_idx FROM behavior_hits h
           JOIN behaviors b ON b.id = h.behavior_id
           WHERE h.trace_id = ANY($1::uuid[]) AND h.review IS NOT NULL""",
        ids,
    )
    verdicts = await pool.fetch(
        """SELECT trace_id, report FROM agent_judge_reports
           WHERE trace_id = ANY($1::uuid[]) AND status = 'done' ORDER BY created_at DESC""",
        ids,
    )
    lines = []
    for r in found:
        tid = r["trace_id"]
        head = f"trace {tid} “{r['title'] or 'Untitled'}”:"
        notes = [
            f"eval “{x['name']}” labeled it {x['label']!r}{' — ' + x['note'] if x['note'] else ''}"
            for x in labels
            if x["trace_id"] == str(tid)
        ]
        notes += [
            f"a person {x['review']} the “{x['name']}” tag on steps {x['start_idx'] + 1}–{x['end_idx'] + 1}"
            for x in reviews
            if x["trace_id"] == tid
        ]
        for v in [v for v in verdicts if v["trace_id"] == tid][:1]:
            claims = (v["report"] or {}).get("claims", [])
            notes += [f"an earlier judge found “{c['text']}” {c['status']}" for c in claims[:4]]
        if notes:
            lines.append(head + "\n  " + "\n  ".join(notes))
    return "\n".join(lines) or "Similar traces exist but none has been labeled or judged."


async def sources(owner_id: UUID | None, script: str) -> str:
    """Run a read-only VFS script (ls, cat, rg, find, head…) over the owner's Stash."""
    if owner_id is None:
        return "Unavailable: no owner to read sources for."
    script = script.strip()
    if not script or len(script) > SCRIPT_CHARS:
        return f"Give a shell script under {SCRIPT_CHARS} characters, e.g. ls /"
    from ...auth import create_api_key, hash_api_key
    from ...main import app
    from ..vfs_service import run_vfs_script

    key = await create_api_key(
        owner_id,
        name="agent judge (read-only, 15 min)",
        key_type="machine",
        access="read",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    try:
        result = await run_vfs_script(app, f"Bearer {key}", script, "/")
    finally:
        await get_pool().execute(
            "UPDATE user_api_keys SET revoked_at = now() WHERE key_hash = $1", hash_api_key(key)
        )
    out = (result.get("stdout") or "") + (
        ("\nSTDERR: " + result["stderr"]) if result.get("stderr") else ""
    )
    return clip(out.strip() or "(no output)", SOURCE_CHARS)
