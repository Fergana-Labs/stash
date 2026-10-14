"""Search traces by what happened in them, narrowed by the behaviors they show.

The query is matched against segments (a user turn and the agent's work after
it) by embedding similarity, or by full-text match when no embedder is
configured, then grouped by trace. Each result carries its best-matching
windows and the behavior hits it has, so "support tickets not resolving after
refund-policy lookups" lands on the traces and the steps, not on a log line.
An optional rerank asks Claude to keep only the traces that answer the query.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from ...database import get_pool
from .. import embeddings, llm
from ..rm.monitoring import AGENT_SQL

CANDIDATES = 200
SEGMENTS_PER_TRACE = 3
SNIPPET_CHARS = 600


def _filters(start: int) -> str:
    """SQL conditions on trace t for agent, recency and behaviors, with placeholders from $start."""
    return f"""AND ($%d::text IS NULL OR {AGENT_SQL} = $%d)
            AND t.created_at > now() - make_interval(days => $%d)
            AND ($%d::uuid[] IS NULL OR EXISTS (
                  SELECT 1 FROM behavior_hits h WHERE h.trace_id = t.id
                  AND h.behavior_id = ANY($%d::uuid[]) AND h.review IS DISTINCT FROM 'rejected'))""" % (
        start,
        start,
        start + 1,
        start + 2,
        start + 2,
    )


async def _matches(owner_id: UUID, q: str, agent, days, behaviors) -> list[dict]:
    pool = get_pool()
    where = _filters(4)
    vector = await embeddings.embed_text(q) if embeddings.is_configured() else None
    if vector is not None:
        rows = await pool.fetch(
            f"""SELECT s.trace_id, s.start_idx, s.end_idx, s.text, 1 - (s.embedding <=> $2) AS score
                FROM rm_trace_segments s JOIN rm_traces t ON t.id = s.trace_id
                WHERE s.owner_user_id = $1 AND s.embedding IS NOT NULL {where}
                ORDER BY s.embedding <=> $2 LIMIT $3""",
            owner_id, vector, CANDIDATES, agent, days, behaviors,
        )  # fmt: skip
    else:
        rows = await pool.fetch(
            f"""SELECT s.trace_id, s.start_idx, s.end_idx, s.text,
                       ts_rank(to_tsvector('english', s.text), websearch_to_tsquery('english', $2)) AS score
                FROM rm_trace_segments s JOIN rm_traces t ON t.id = s.trace_id
                WHERE s.owner_user_id = $1
                  AND to_tsvector('english', s.text) @@ websearch_to_tsquery('english', $2) {where}
                ORDER BY score DESC LIMIT $3""",
            owner_id, q, CANDIDATES, agent, days, behaviors,
        )  # fmt: skip
    return [dict(r) for r in rows]


async def _browse(owner_id: UUID, agent, days, behaviors, limit: int) -> list[dict]:
    where = _filters(3)
    rows = await get_pool().fetch(
        f"""SELECT t.id AS trace_id FROM rm_traces t
            WHERE t.owner_user_id = $1 {where}
            ORDER BY t.created_at DESC LIMIT $2""",
        owner_id, limit, agent, days, behaviors,
    )  # fmt: skip
    return [{"trace_id": r["trace_id"], "score": None} for r in rows]


async def _decorate(owner_id: UUID, ids: list[UUID]) -> dict[UUID, dict]:
    pool = get_pool()
    traces = await pool.fetch(
        f"""SELECT t.id, t.title, t.created_at, {AGENT_SQL} AS agent,
              (SELECT left(content, 300) FROM rm_trace_steps WHERE trace_id = t.id AND role = 'user' ORDER BY idx LIMIT 1) AS input,
              (SELECT left(content, 300) FROM rm_trace_steps WHERE trace_id = t.id AND role = 'assistant' AND tool_name IS NULL ORDER BY idx DESC LIMIT 1) AS output
            FROM rm_traces t WHERE t.owner_user_id = $1 AND t.id = ANY($2::uuid[])""",
        owner_id,
        ids,
    )
    hits = await pool.fetch(
        """SELECT h.id, h.trace_id, h.behavior_id, b.name, b.actor, h.start_idx, h.end_idx, h.review, h.confidence
           FROM behavior_hits h JOIN behaviors b ON b.id = h.behavior_id
           WHERE h.trace_id = ANY($1::uuid[]) AND h.review IS DISTINCT FROM 'rejected'
           ORDER BY h.start_idx""",
        ids,
    )
    out = {r["id"]: {**dict(r), "behaviors": []} for r in traces}
    for h in hits:
        if h["trace_id"] in out:
            out[h["trace_id"]]["behaviors"].append({k: h[k] for k in h.keys() if k != "trace_id"})
    return out


class _Ranked(BaseModel):
    relevant: list[int] = Field(description="Candidate numbers that answer the query, best first")


async def _rerank(q: str, results: list[dict]) -> list[dict]:
    listing = "\n\n".join(
        f"#{i} {r['title'] or 'Untitled'} (behaviors: {', '.join(sorted({b['name'] for b in r['behaviors']})) or 'none'})\n"
        + "\n---\n".join(s["snippet"] for s in r["segments"])
        for i, r in enumerate(results)
    )
    ranked = await llm.complete_structured(
        prompt=f"QUERY: {q}\n\nCANDIDATE TRACES:\n\n{listing}",
        system="You rerank agent traces for a search query. Return the numbers of the candidates whose content actually matches the query, best match first. Leave out candidates that do not match.",
        output_model=_Ranked,
        tier=llm.ModelTier.FAST,
        max_tokens=600,
    )
    keep = [i for i in dict.fromkeys(ranked.relevant) if 0 <= i < len(results)]
    return [results[i] for i in keep]


async def search(
    owner_id: UUID,
    q: str | None,
    *,
    behaviors: list[UUID] | None = None,
    agent: str | None = None,
    days: int = 30,
    limit: int = 25,
    rerank: bool = False,
) -> dict:
    q = (q or "").strip()
    behaviors = behaviors or None
    if q:
        matches = await _matches(owner_id, q, agent, days, behaviors)
        grouped: dict[UUID, dict] = {}
        for m in matches:
            g = grouped.setdefault(
                m["trace_id"], {"trace_id": m["trace_id"], "score": m["score"], "segments": []}
            )
            if len(g["segments"]) < SEGMENTS_PER_TRACE:
                g["segments"].append(
                    {"start_idx": m["start_idx"], "end_idx": m["end_idx"], "score": m["score"],
                     "snippet": m["text"][:SNIPPET_CHARS]}
                )  # fmt: skip
        ranked = list(grouped.values())[:limit]
    else:
        ranked = [
            {**r, "segments": []} for r in await _browse(owner_id, agent, days, behaviors, limit)
        ]
    info = await _decorate(owner_id, [r["trace_id"] for r in ranked])
    results = [{**info[r["trace_id"]], **r} for r in ranked if r["trace_id"] in info]
    for r in results:
        r.pop("id", None)
    if q and rerank and results:
        results = await _rerank(q, results)
    return {
        "query": q,
        "mode": "semantic" if q and embeddings.is_configured() else "text" if q else "browse",
        "results": results,
    }
