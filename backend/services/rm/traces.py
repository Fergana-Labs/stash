"""Import, list, read, delete, and export agent traces for the reward model platform."""

from uuid import UUID

from ...database import get_pool
from . import annotations
from .adapters import CanonicalTrace, TraceFormatError, parse_traces

TITLE_CHARS = 80

SUMMARY_SELECT = """
    SELECT
      t.id, t.external_id, t.title, t.source_format, t.metadata, t.created_at,
      (SELECT count(*) FROM rm_trace_steps s WHERE s.trace_id = t.id)::int AS step_count,
      a.positive_count, a.negative_count, a.comment_count, a.label_error_count,
      ls.reward_model_id AS latest_reward_model_id,
      ls.reward_model_name AS latest_reward_model_name,
      ls.score AS latest_score
    FROM rm_traces t
    CROSS JOIN LATERAL (
      SELECT
        count(*) FILTER (WHERE rating = 1 AND NOT label_error)::int AS positive_count,
        count(*) FILTER (WHERE rating = -1 AND NOT label_error)::int AS negative_count,
        count(*) FILTER (WHERE comment IS NOT NULL)::int AS comment_count,
        count(*) FILTER (WHERE label_error)::int AS label_error_count
      FROM rm_annotations WHERE trace_id = t.id
    ) a
    LEFT JOIN LATERAL (
      SELECT sc.reward_model_id, m.name AS reward_model_name, sc.score
      FROM rm_trace_scores sc JOIN rm_reward_models m ON m.id = sc.reward_model_id
      WHERE sc.trace_id = t.id AND m.status = 'succeeded'
      ORDER BY m.finished_at DESC
      LIMIT 1
    ) ls ON true
"""


def _title(trace: CanonicalTrace, index: int) -> str:
    if trace.title:
        return trace.title
    for step in trace.steps:
        if step.role == "user":
            return step.content[:TITLE_CHARS]
    raise TraceFormatError(f"trace {index} has no title and no user step to derive one from")


def _summary(row) -> dict:
    latest_score = None
    if row["latest_reward_model_id"] is not None:
        latest_score = {
            "reward_model_id": row["latest_reward_model_id"],
            "reward_model_name": row["latest_reward_model_name"],
            "score": row["latest_score"],
        }
    return {
        "id": row["id"],
        "external_id": row["external_id"],
        "title": row["title"],
        "source_format": row["source_format"],
        "step_count": row["step_count"],
        "positive_count": row["positive_count"],
        "negative_count": row["negative_count"],
        "comment_count": row["comment_count"],
        "label_error_count": row["label_error_count"],
        "latest_score": latest_score,
        "created_at": row["created_at"],
    }


def _step(row) -> dict:
    return {
        "id": row["id"],
        "index": row["idx"],
        "role": row["role"],
        "content": row["content"],
        "tool_name": row["tool_name"],
        "tool_input": row["tool_input"],
        "tool_call_id": row["tool_call_id"],
        "metadata": row["metadata"],
    }


async def import_traces(owner_user_id: UUID, format: str, data: str) -> dict:
    """Parse and store traces. Re-importing an `id` replaces that trace's steps."""
    resolved_format, traces = parse_traces(data, format)
    for index, trace in enumerate(traces):
        if all(step.role == "system" for step in trace.steps):
            raise TraceFormatError(f"trace {index} has only system steps; nothing to judge")
    titles = [_title(trace, index) for index, trace in enumerate(traces)]

    trace_ids = []
    async with get_pool().acquire() as conn, conn.transaction():
        for trace, title in zip(traces, titles, strict=True):
            trace_id = await conn.fetchval(
                """
                INSERT INTO rm_traces (owner_user_id, external_id, title, source_format, metadata)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (owner_user_id, external_id) DO UPDATE SET
                  title = EXCLUDED.title,
                  source_format = EXCLUDED.source_format,
                  metadata = EXCLUDED.metadata,
                  updated_at = now()
                RETURNING id
                """,
                owner_user_id,
                trace.external_id,
                title,
                resolved_format,
                trace.metadata,
            )
            # Step-level annotations cascade away with the replaced steps.
            await conn.execute("DELETE FROM rm_trace_steps WHERE trace_id = $1", trace_id)
            await conn.executemany(
                """
                INSERT INTO rm_trace_steps
                  (trace_id, idx, role, content, tool_name, tool_input, tool_call_id, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                [
                    (
                        trace_id,
                        idx,
                        step.role,
                        step.content,
                        step.tool_name,
                        step.tool_input,
                        step.tool_call_id,
                        step.metadata if step.metadata else None,
                    )
                    for idx, step in enumerate(trace.steps)
                ],
            )
            trace_ids.append(trace_id)
    return {"format": resolved_format, "imported": len(trace_ids), "trace_ids": trace_ids}


async def list_traces(owner_user_id: UUID, limit: int, offset: int) -> dict:
    pool = get_pool()
    rows = await pool.fetch(
        SUMMARY_SELECT
        + " WHERE t.owner_user_id = $1 ORDER BY t.created_at DESC, t.id LIMIT $2 OFFSET $3",
        owner_user_id,
        limit,
        offset,
    )
    total = await pool.fetchval(
        "SELECT count(*) FROM rm_traces WHERE owner_user_id = $1", owner_user_id
    )
    return {"traces": [_summary(row) for row in rows], "total": total}


async def get_trace(owner_user_id: UUID, trace_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        SUMMARY_SELECT + " WHERE t.owner_user_id = $1 AND t.id = $2", owner_user_id, trace_id
    )
    if row is None:
        return None
    steps = await pool.fetch(
        "SELECT * FROM rm_trace_steps WHERE trace_id = $1 ORDER BY idx", trace_id
    )
    scores = await pool.fetch(
        """
        SELECT sc.reward_model_id, m.name AS reward_model_name, sc.score, sc.created_at
        FROM rm_trace_scores sc JOIN rm_reward_models m ON m.id = sc.reward_model_id
        WHERE sc.trace_id = $1 AND m.status = 'succeeded'
        ORDER BY m.finished_at DESC
        """,
        trace_id,
    )
    return {
        **_summary(row),
        "metadata": row["metadata"],
        "steps": [_step(step) for step in steps],
        "annotations": await annotations.list_for_trace(trace_id),
        "scores": [dict(score) for score in scores],
    }


async def delete_trace(owner_user_id: UUID, trace_id: UUID) -> bool:
    result = await get_pool().execute(
        "DELETE FROM rm_traces WHERE owner_user_id = $1 AND id = $2", owner_user_id, trace_id
    )
    return result == "DELETE 1"


async def export_traces(owner_user_id: UUID) -> list[dict]:
    """Every trace in Stash Trace Format, re-importable with format `stash`."""
    pool = get_pool()
    traces = await pool.fetch(
        """
        SELECT id, external_id, title, metadata FROM rm_traces
        WHERE owner_user_id = $1 ORDER BY created_at, id
        """,
        owner_user_id,
    )
    steps = await pool.fetch(
        """
        SELECT s.* FROM rm_trace_steps s JOIN rm_traces t ON t.id = s.trace_id
        WHERE t.owner_user_id = $1 ORDER BY s.trace_id, s.idx
        """,
        owner_user_id,
    )
    steps_by_trace: dict[UUID, list[dict]] = {}
    for step in steps:
        exported = {"role": step["role"], "content": step["content"]}
        for key in ("tool_name", "tool_input", "tool_call_id", "metadata"):
            if step[key]:
                exported[key] = step[key]
        steps_by_trace.setdefault(step["trace_id"], []).append(exported)

    lines = []
    for trace in traces:
        line = {"title": trace["title"], "metadata": trace["metadata"]}
        if trace["external_id"] is not None:
            line["id"] = trace["external_id"]
        line["steps"] = steps_by_trace[trace["id"]]
        lines.append(line)
    return lines
