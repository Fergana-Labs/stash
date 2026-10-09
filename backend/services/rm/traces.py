"""Import, list, read, delete, and export agent traces for the reward model platform."""

from uuid import UUID

import asyncpg

from ...database import get_pool
from . import (
    annotations,
    evaluator,
    step_labeling,
    trace_images,
    trace_sources,
    trace_titles,
    workbench_auto,
    workbench_evaluation,
)
from .adapters import CanonicalTrace, TraceFormatError, parse_traces

SUMMARY_SELECT = """
    SELECT
      t.id, t.owner_user_id, t.external_id, t.title, t.source_format, t.metadata, t.spans, t.created_at, t.shared_training_allowed,
      coalesce(nullif(u.display_name,''),u.name) AS source_owner_name,
      (SELECT count(*) FROM rm_trace_steps s WHERE s.trace_id = t.id)::int AS step_count,
      a.positive_count, a.negative_count, a.comment_count, a.label_error_count,
      ls.reward_model_id AS latest_reward_model_id,
      ls.reward_model_name AS latest_reward_model_name,
      ls.score AS latest_score,
      ac.mean_credit, ac.min_credit, ac.max_credit, ac.scored_actions, ac.revision AS evaluator_revision
    FROM rm_traces t
    JOIN users u ON u.id=t.owner_user_id
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
      WHERE sc.trace_id = t.id AND m.status = 'succeeded' AND sc.created_at >= t.updated_at
      ORDER BY m.finished_at DESC
      LIMIT 1
    ) ls ON true
    LEFT JOIN LATERAL (
      SELECT avg(sc.credit) AS mean_credit, min(sc.credit) AS min_credit, max(sc.credit) AS max_credit, count(*)::int AS scored_actions, r.revision
      FROM rm_evaluator_registry r JOIN rm_action_scores sc ON sc.reward_model_id = r.model_id
      JOIN rm_trace_steps s ON s.id = sc.step_id WHERE s.trace_id = t.id GROUP BY r.revision
    ) ac ON true
"""


def _summary(row, viewer_id: UUID, source_names: dict) -> dict:
    latest_score = None
    if row["latest_reward_model_id"] is not None:
        latest_score = {
            "reward_model_id": row["latest_reward_model_id"],
            "reward_model_name": row["latest_reward_model_name"],
            "score": row["latest_score"],
        }
    agent = (row["metadata"] or {}).get("agent")
    source_id = trace_sources.source_id(row["metadata"] or {}, row["source_format"])
    return {
        "id": row["id"],
        "can_score": row["owner_user_id"] == viewer_id,
        "external_id": row["external_id"],
        "title": row["title"],
        "source_format": row["source_format"],
        "source_id": source_id,
        "source_name": source_names.get(
            (row["owner_user_id"], source_id),
            trace_sources.default_name(source_id, row["source_owner_name"]),
        ),
        "source_owner_id": row["owner_user_id"],
        "agent": agent if isinstance(agent, str) and agent.strip() else row["source_format"],
        "step_count": row["step_count"],
        "positive_count": row["positive_count"],
        "negative_count": row["negative_count"],
        "comment_count": row["comment_count"],
        "label_error_count": row["label_error_count"],
        "latest_score": latest_score,
        "created_at": row["created_at"],
        "shared_training_allowed": row["shared_training_allowed"],
        "action_credit": {
            "mean": row["mean_credit"],
            "min": row["min_credit"],
            "max": row["max_credit"],
            "count": row["scored_actions"],
            "revision": row["evaluator_revision"],
        }
        if row["mean_credit"] is not None
        else None,
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


async def import_traces(
    owner_user_id: UUID, format: str, data: str, source_id: str | None = None
) -> dict:
    """Parse and store traces. Re-importing an `id` replaces that trace's steps."""
    resolved_format, traces = parse_traces(data, format)
    if source_id is not None:
        for trace in traces:
            trace.metadata["source_id"] = source_id
    async with get_pool().acquire() as conn, conn.transaction():
        trace_ids = await store_traces(conn, owner_user_id, resolved_format, traces)
    return {"format": resolved_format, "imported": len(trace_ids), "trace_ids": trace_ids}


async def store_traces(
    conn: asyncpg.Connection,
    owner_user_id: UUID,
    source_format: str,
    traces: list[CanonicalTrace],
) -> list[UUID]:
    """Upsert parsed traces by external id on the caller's connection (and transaction)."""
    for index, trace in enumerate(traces):
        if all(step.role == "system" for step in trace.steps):
            raise TraceFormatError(f"trace {index} has only system steps; nothing to judge")
    titles = [
        trace.title if trace.title is not None else await trace_titles.generate_title(trace)
        for trace in traces
    ]

    trace_ids = []
    for trace, title in zip(traces, titles, strict=True):
        trace_id = await conn.fetchval(
            """
            INSERT INTO rm_traces (owner_user_id, external_id, title, source_format, metadata, spans)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (owner_user_id, external_id) DO UPDATE SET
              title = EXCLUDED.title,
              source_format = EXCLUDED.source_format,
              metadata = CASE WHEN NOT (EXCLUDED.metadata ? 'source_id') AND rm_traces.metadata ? 'source_id'
                THEN EXCLUDED.metadata || jsonb_build_object('source_id',rm_traces.metadata->'source_id')
                ELSE EXCLUDED.metadata END,
              spans = EXCLUDED.spans,
              updated_at = now()
            RETURNING id
            """,
            owner_user_id,
            trace.external_id,
            title,
            source_format,
            trace.metadata,
            [span.model_dump() for span in trace.spans],
        )
        # Step-level annotations cascade away with the replaced steps.
        # Multi-step quotes store their anchors in JSON, so remove those explicitly.
        await conn.execute(
            "DELETE FROM rm_annotations WHERE trace_id = $1 AND quote ? 'segments'", trace_id
        )
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
        await trace_images.store_images(conn, owner_user_id, trace_id, trace.steps)
        trace_ids.append(trace_id)
    return trace_ids


async def list_traces(
    owner_user_id: UUID,
    limit: int,
    offset: int,
    query: str = "",
    reward_model_id: UUID | None = None,
) -> dict:
    pool = get_pool()
    if reward_model_id is not None and not await pool.fetchval(
        "SELECT 1 FROM rm_reward_models WHERE id=$1 AND owner_user_id=$2",
        reward_model_id,
        owner_user_id,
    ):
        raise LookupError("Reward model not found")
    # Literal substring search, including tool arguments/results, scoped before pagination.
    where = """ WHERE (t.owner_user_id = $1 OR EXISTS
        (SELECT 1 FROM rm_wb_trace_reviewers r WHERE r.trace_id=t.id AND r.user_id=$1))
        AND ($2='' OR strpos(lower(t.title),lower($2))>0 OR EXISTS
        (SELECT 1 FROM rm_trace_steps s WHERE s.trace_id=t.id AND
          (strpos(lower(s.content),lower($2))>0 OR strpos(lower(coalesce(s.tool_name,'')),lower($2))>0
           OR strpos(lower(coalesce(s.tool_input::text,'')),lower($2))>0)))"""
    query = query.strip()
    select = SUMMARY_SELECT.replace(
        "WHERE sc.trace_id = t.id AND m.status",
        "WHERE ($5::uuid IS NULL OR sc.reward_model_id=$5) AND sc.trace_id = t.id AND m.status",
    )
    if reward_model_id is not None:
        select = select.replace(
            "FROM rm_evaluator_registry r JOIN rm_action_scores sc",
            "FROM (SELECT $5::uuid AS model_id, NULL::integer AS revision) r JOIN rm_action_scores sc",
        )
    rows = await pool.fetch(
        select + where + " ORDER BY t.created_at DESC, t.id LIMIT $3 OFFSET $4",
        owner_user_id,
        query,
        limit,
        offset,
        reward_model_id,
    )
    total = await pool.fetchval("SELECT count(*) FROM rm_traces t" + where, owner_user_id, query)
    source_names = await trace_sources.names(rows)
    summaries = [_summary(row, owner_user_id, source_names) for row in rows]
    if rows:
        coverage = await pool.fetch(
            """WITH selected AS (SELECT unnest($1::uuid[]) AS id), latest AS (
              SELECT DISTINCT ON (a.trace_id,a.grader_id,a.target_step_id,a.criterion_id) a.*
              FROM rm_wb_assessments a JOIN rm_wb_graders g ON g.active_version_id=a.grader_version_id
              WHERE a.trace_id=ANY($1::uuid[]) AND a.target_step_id IS NOT NULL
              ORDER BY a.trace_id,a.grader_id,a.target_step_id,a.criterion_id,a.attempt DESC,a.created_at DESC
            ) SELECT t.id,
              (SELECT count(*) FROM rm_trace_steps s WHERE s.trace_id=t.id AND s.role='assistant'
               AND (s.tool_name IS NOT NULL OR btrim(s.content)<>'') AND coalesce(s.metadata->>'thinking','false')<>'true') AS total_actions,
              (SELECT count(DISTINCT target_step_id) FROM rm_wb_assessments a WHERE a.trace_id=t.id AND a.status='completed') AS assessed_actions,
              (SELECT count(*) FROM latest a WHERE a.trace_id=t.id AND a.verdict='violates') AS violations,
              (SELECT count(*) FROM latest a WHERE a.trace_id=t.id AND a.status IN ('queued','running')) AS pending,
              (SELECT count(*) FROM latest a WHERE a.trace_id=t.id AND a.status='failed') AS failed,
              q.status AS queue_status
            FROM selected t LEFT JOIN rm_wb_queue q ON q.trace_id=t.id""",
            [row["id"] for row in rows],
        )
        by_id = {r["id"]: {k: v for k, v in dict(r).items() if k != "id"} for r in coverage}
        for summary in summaries:
            summary["workbench"] = by_id[summary["id"]]
    await _evaluation_summaries(summaries)
    return {"traces": summaries, "total": total}


async def _evaluation_summaries(summaries: list[dict]) -> None:
    if summaries:
        pool = get_pool()
        evaluations = await pool.fetch(
            """SELECT DISTINCT ON (e.trace_id) e.trace_id,e.id,e.outcome,e.status,e.outcome_probabilities,
            e.total_actions,e.credited_actions,(e.trace_updated_at>=t.updated_at AND e.policy_version=$2 AND e.model=$3) AS current
            FROM rm_wb_evaluations e JOIN rm_traces t ON t.id=e.trace_id WHERE e.trace_id=ANY($1::uuid[])
            ORDER BY e.trace_id,e.created_at DESC""",
            [r["id"] for r in summaries],
            workbench_evaluation.POLICY_VERSION,
            workbench_evaluation.model(),
        )
        evaluations = {r["trace_id"]: dict(r) for r in evaluations}
        calls = await pool.fetch(
            "SELECT evaluation_id,result FROM rm_wb_evaluation_calls WHERE evaluation_id=ANY($1::uuid[]) AND status='completed' AND batch_index>0",
            [r["id"] for r in evaluations.values()],
        )
        credits: dict[UUID, list[float]] = {}
        for call in calls:
            for result in call["result"].get("results", []):
                credit = workbench_evaluation.expected_credit(result)
                if credit is not None:
                    credits.setdefault(call["evaluation_id"], []).append(credit)
        for evaluation in evaluations.values():
            probabilities = evaluation.pop("outcome_probabilities") or {}
            # A rule score stands on its own; the earlier policy's estimate
            # of success means nothing without an established outcome.
            evaluation["score"] = probabilities.get(
                "score",
                probabilities.get("success")
                if evaluation["outcome"] != "insufficient_evidence"
                else None,
            )
            values = credits.get(evaluation["id"], [])
            evaluation["action_credit"] = (
                {
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
                if values
                else None
            )
        for summary in summaries:
            summary["evaluation"] = evaluations.get(summary["id"])


async def get_trace(
    owner_user_id: UUID, trace_id: UUID, *, include_evaluation: bool = False
) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        SUMMARY_SELECT
        + " WHERE t.id = $2 AND (t.owner_user_id = $1 OR EXISTS (SELECT 1 FROM rm_wb_trace_reviewers r WHERE r.trace_id=t.id AND r.user_id=$1))",
        owner_user_id,
        trace_id,
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
    action_scores = await pool.fetch(
        """
        SELECT sc.reward_model_id, m.name AS reward_model_name, sc.step_id, sc.score, sc.credit, sc.created_at
        FROM rm_action_scores sc JOIN rm_trace_steps s ON s.id = sc.step_id
        JOIN rm_reward_models m ON m.id = sc.reward_model_id
        WHERE s.trace_id = $1 AND (m.owner_user_id = $2 OR EXISTS
            (SELECT 1 FROM rm_evaluator_releases er WHERE er.reward_model_id = m.id)) AND m.status = 'succeeded'
        ORDER BY m.finished_at DESC, s.idx
        """,
        trace_id,
        owner_user_id,
    )
    scoring_runs = await pool.fetch(
        """
        SELECT DISTINCT ON (reward_model_id) id, trace_id, reward_model_id, status, error,
               created_at, started_at, finished_at
        FROM rm_scoring_runs WHERE trace_id = $1 AND owner_user_id = $2
        ORDER BY reward_model_id, created_at DESC, id DESC
        """,
        trace_id,
        owner_user_id,
    )
    automatic = await pool.fetchrow(
        "SELECT attempts, error FROM rm_auto_scores WHERE trace_id = $1", trace_id
    )
    collection = await pool.fetchrow(
        "SELECT status, error FROM rm_example_collection WHERE trace_id = $1", trace_id
    )
    training_models = await pool.fetch(
        """SELECT id, name, status, error, created_at, finished_at FROM rm_reward_models
        WHERE owner_user_id=$1 AND $2=ANY(trace_ids) ORDER BY created_at DESC LIMIT 5""",
        owner_user_id,
        trace_id,
    )
    summary = _summary(row, owner_user_id, await trace_sources.names([row]))
    await _evaluation_summaries([summary])
    images = await trace_images.for_trace(trace_id)
    detail = {
        **summary,
        **(
            {
                "automatic_evaluation": await workbench_auto.detail(
                    owner_user_id, trace_id, compact=True, trace_data=(row, steps)
                )
            }
            if include_evaluation
            else {}
        ),
        "metadata": row["metadata"],
        "spans": row["spans"],
        "steps": [{**_step(step), "images": images.get(step["id"], [])} for step in steps],
        "annotations": await annotations.list_for_trace(trace_id),
        "scores": [dict(score) for score in scores],
        "action_scores": [dict(score) for score in action_scores],
        "scoring_runs": [dict(run) for run in scoring_runs],
        "default_evaluator": await evaluator.default_evaluator(),
        "automatic_scoring": dict(automatic) if automatic else None,
        "training_collection": dict(collection) if collection else None,
        "training_models": [dict(model) for model in training_models],
    }
    return await step_labeling.merge_into(trace_id, detail)


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
        SELECT id, external_id, title, metadata, spans FROM rm_traces
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
            if step[key] is not None:
                exported[key] = step[key]
        steps_by_trace.setdefault(step["trace_id"], []).append(exported)

    lines = []
    for trace in traces:
        line = {"title": trace["title"], "metadata": trace["metadata"], "spans": trace["spans"]}
        if trace["external_id"] is not None:
            line["id"] = trace["external_id"]
        line["steps"] = steps_by_trace[trace["id"]]
        lines.append(line)
    return lines
