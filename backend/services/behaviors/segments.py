"""Segments: a trace cut at each user turn, the unit of search and detection.

A segment is one user message and everything the agent and its tools did until
the next one (steps before the first user message form their own segment). It
is small enough to embed and to hand a detector whole, and its step range is
the natural window a behavior hit points into.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from ...database import get_pool

SEGMENT_CHARS = 6_000
STEP_CHARS = 1_500


def clip(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    head = int(cap * 0.7)
    return f"{text[:head]}\n…[omitted]…\n{text[-(cap - head) :]}"


def render_step(step: dict, cap: int = STEP_CHARS) -> str:
    role = step["role"].upper()
    if step.get("tool_name"):
        args = json.dumps(step.get("tool_input") or {}, sort_keys=True)
        head = f"[{step['idx']}] {role} tool call {step['tool_name']} {clip(args, 400)}"
        return f"{head}\n{clip(step.get('content') or '', cap)}".rstrip()
    return f"[{step['idx']}] {role}\n{clip(step.get('content') or '', cap)}"


def split(steps: list[dict]) -> list[list[dict]]:
    """Steps grouped into segments, in order. System steps belong to no segment."""
    groups: list[list[dict]] = []
    for step in steps:
        if step["role"] == "system":
            continue
        if step["role"] == "user" or not groups:
            groups.append([])
        groups[-1].append(step)
    return groups


def render(group: list[dict], cap: int = SEGMENT_CHARS) -> str:
    return clip("\n\n".join(render_step(step) for step in group), cap)


def build(steps: list[dict]) -> list[dict]:
    out = []
    for group in split(steps):
        text = render(group)
        out.append(
            {
                "start_idx": group[0]["idx"],
                "end_idx": group[-1]["idx"],
                "text": text,
                "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
    return out


async def read_steps(trace_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT idx, role, content, tool_name, tool_input, tool_call_id, metadata "
        "FROM rm_trace_steps WHERE trace_id = $1 ORDER BY idx",
        trace_id,
    )
    return [dict(r) for r in rows]


async def sync(trace_id: UUID, owner_id: UUID, steps: list[dict] | None = None) -> list[dict]:
    """Bring a trace's stored segments in line with its steps. Changed segments
    are marked for re-embedding; unchanged ones keep their embedding."""
    if steps is None:
        steps = await read_steps(trace_id)
    built = build(steps)
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM rm_trace_segments WHERE trace_id = $1 AND NOT (start_idx = ANY($2::int[]))",
            trace_id,
            [s["start_idx"] for s in built],
        )
        for s in built:
            await conn.execute(
                """INSERT INTO rm_trace_segments
                     (trace_id, owner_user_id, start_idx, end_idx, text, content_hash)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (trace_id, start_idx) DO UPDATE SET
                     end_idx = EXCLUDED.end_idx, text = EXCLUDED.text,
                     content_hash = EXCLUDED.content_hash, updated_at = now(),
                     embed_stale = rm_trace_segments.embed_stale
                       OR rm_trace_segments.content_hash <> EXCLUDED.content_hash""",
                trace_id, owner_id, s["start_idx"], s["end_idx"], s["text"], s["content_hash"],
            )  # fmt: skip
        # Touch unchanged segments too, so the sweep knows this trace version is done.
        await conn.execute(
            "UPDATE rm_trace_segments SET updated_at = now() WHERE trace_id = $1", trace_id
        )
    return built


async def stale_traces(limit: int, days: int) -> list[dict]:
    """Recent traces whose segments are missing or older than the trace."""
    rows = await get_pool().fetch(
        """SELECT t.id, t.owner_user_id FROM rm_traces t
           WHERE t.updated_at > now() - make_interval(days => $2)
             AND t.updated_at < now() - interval '15 seconds'
             AND EXISTS (SELECT 1 FROM rm_trace_steps st WHERE st.trace_id = t.id AND st.role <> 'system')
             AND NOT EXISTS (
               SELECT 1 FROM rm_trace_segments s
               WHERE s.trace_id = t.id AND s.updated_at >= t.updated_at)
           ORDER BY t.updated_at DESC LIMIT $1""",
        limit,
        days,
    )
    return [dict(r) for r in rows]
