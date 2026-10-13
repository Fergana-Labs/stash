"""Agent monitoring from persisted evidence; no training or inference on reads."""

from ...database import get_pool
from . import optimization, trace_sources

AGENT_SQL = """coalesce(CASE WHEN jsonb_typeof(t.metadata->'agent')='string'
    THEN nullif(btrim(t.metadata->>'agent'),'') END,t.source_format)"""


async def overview(owner):
    pool = get_pool()
    rows = await pool.fetch(
        f"""WITH traces AS (
        SELECT {AGENT_SQL} AS agent,count(*)::int AS trace_count,max(t.created_at) AS last_seen
        FROM rm_traces t WHERE t.owner_user_id=$1 GROUP BY 1
        ), agents AS (
        SELECT agent FROM traces UNION SELECT agent FROM rm_optimizations WHERE owner_user_id=$1)
        SELECT a.agent,coalesce(t.trace_count,0) AS trace_count,t.last_seen,s.name AS display_name
        FROM agents a LEFT JOIN traces t USING(agent)
        LEFT JOIN rm_trace_sources s ON s.owner_user_id=$1 AND s.source_id=a.agent
        ORDER BY t.last_seen DESC NULLS LAST,a.agent""",
        owner,
    )
    agents = [
        {**dict(r), "display_name": r["display_name"] or trace_sources.default_name(r["agent"])}
        for r in rows
    ]
    models = await pool.fetch(
        """SELECT id,name,metrics,finished_at FROM rm_reward_models
        WHERE owner_user_id=$1 AND scope='personal' AND status='succeeded'
        ORDER BY created_at DESC""",
        owner,
    )
    programs = await pool.fetch(
        """SELECT o.id,o.name,o.agent,o.scope,o.status,o.reward_model_id,o.intuition_model_id,
        m.name AS reward_model_name,e.name AS eval_name,o.active_revision_id,p.version AS active_version,o.error,
        (SELECT count(*)::int FROM rm_optimization_runs r WHERE r.optimization_id=o.id) AS run_count,
        (SELECT count(*)::int FROM rm_optimization_rounds r WHERE r.optimization_id=o.id AND r.status='promoted') AS accepted_count
        FROM rm_optimizations o LEFT JOIN rm_reward_models m ON m.id=o.reward_model_id
        LEFT JOIN intuition_models e ON e.id=o.intuition_model_id
        LEFT JOIN rm_prompt_revisions p ON p.id=o.active_revision_id
        WHERE o.owner_user_id=$1 ORDER BY o.created_at DESC""",
        owner,
    )
    return {
        "agents": agents,
        "models": [dict(r) for r in models],
        "programs": [dict(r) for r in programs],
        "gepa": [],  # Older clients expect this key; Monitoring no longer loads skill trials.
    }


async def rewards(owner, agent, model_id, window, program_id=None):
    if window not in (20, 50, 100):
        raise ValueError("Choose a window of 20, 50 or 100 runs")
    pool = get_pool()
    program = await optimization.owned(owner, program_id) if program_id else None
    if program and program["intuition_model_id"]:
        # Eval-scored programs: model_id names the eval, rewards are P(success decision).
        model = {"metrics": {}, "status": "succeeded", "finished_at": None}
        if program["agent"] != agent or program["intuition_model_id"] != model_id:
            raise ValueError("Choose the agent and eval belonging to this optimization")
    else:
        model = await pool.fetchrow(
            """SELECT id,name,metrics,status,finished_at FROM rm_reward_models
            WHERE id=$1 AND owner_user_id=$2 AND scope='personal'""",
            model_id,
            owner,
        )
    if not model:
        raise LookupError("Reward model not found")
    if not program_id and model["status"] != "succeeded":
        raise ValueError("Choose a ready reward model")
    active_revision = None
    if program_id:
        if not program["intuition_model_id"] and (
            program["agent"] != agent or program["reward_model_id"] != model_id
        ):
            raise ValueError("Choose the agent and reward model belonging to this optimization")
        active_revision = program["active_revision_id"]
        observations = """SELECT r.id,r.trace_id,r.work_key AS title,r.assigned_at AS recorded_at,
            r.reward,r.revision_id FROM rm_optimization_runs r
            WHERE r.optimization_id=$5 AND r.status='completed' AND r.reward IS NOT NULL"""
        unit = "eval_probability" if program["intuition_model_id"] else "action_credit"
    elif (model["metrics"] or {}).get("action_scoring_version") == 1:
        observations = f"""SELECT t.id,t.id AS trace_id,t.title,t.created_at AS recorded_at,
            ac.reward,NULL::uuid AS revision_id FROM rm_traces t
            CROSS JOIN LATERAL (
              SELECT avg(sc.credit) AS reward FROM rm_trace_steps s JOIN rm_action_scores sc
              ON sc.step_id=s.id AND sc.reward_model_id=$3 WHERE s.trace_id=t.id
            ) ac
            WHERE t.owner_user_id=$1 AND {AGENT_SQL}=$2 AND ac.reward IS NOT NULL
            AND EXISTS (SELECT 1 FROM rm_scoring_runs r WHERE r.trace_id=t.id
              AND r.reward_model_id=$3 AND r.owner_user_id=$1 AND r.status='succeeded'
              AND r.trace_updated_at=t.updated_at AND r.model_finished_at=$7)"""
        unit = "action_credit"
    elif (model["metrics"] or {}).get("trace_scoring_version") == 1:
        observations = f"""SELECT t.id,t.id AS trace_id,t.title,t.created_at AS recorded_at,
            sc.score AS reward,NULL::uuid AS revision_id FROM rm_traces t
            JOIN rm_trace_scores sc ON sc.trace_id=t.id AND sc.reward_model_id=$3
            WHERE t.owner_user_id=$1 AND {AGENT_SQL}=$2
            AND sc.created_at>=t.updated_at AND sc.created_at>=$7"""
        unit = "trace_reward"
    else:
        raise ValueError("This reward model does not support monitoring scores")
    # Average each run once. Compute windows over ALL observations before
    # thinning the chart, and keep experimental prompt arms in separate series.
    row = await pool.fetchrow(
        f"""WITH params AS (SELECT $1::uuid,$2::text,$3::uuid,$4::int,$5::uuid,$6::uuid,$7::timestamptz),
        observations AS ({observations}), rolling AS (
          SELECT *,avg(reward) OVER w AS rolling_mean,count(*) OVER w AS window_count,
          row_number() OVER (ORDER BY recorded_at,id) AS position,
          count(*) OVER () AS total,
          row_number() OVER (PARTITION BY revision_id ORDER BY recorded_at,id) AS revision_first,
          row_number() OVER (PARTITION BY revision_id ORDER BY recorded_at DESC,id DESC) AS revision_last
          FROM observations WINDOW w AS (PARTITION BY revision_id ORDER BY recorded_at,id
            ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW)
        ), recent AS (
          SELECT *,row_number() OVER (ORDER BY recorded_at DESC,id DESC) AS recency
          FROM observations WHERE $6::uuid IS NULL OR revision_id=$6
        ) SELECT
        (SELECT count(*)::int FROM observations) AS total,
        (SELECT avg(reward) FROM observations) AS mean,
        (SELECT count(*)::int FROM recent WHERE recency<=$4) AS current_n,
        (SELECT avg(reward) FROM recent WHERE recency<=$4) AS current_mean,
        (SELECT count(*)::int FROM recent WHERE recency>$4 AND recency<=2*$4) AS previous_n,
        (SELECT avg(reward) FROM recent WHERE recency>$4 AND recency<=2*$4) AS previous_mean,
        coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.recorded_at,p.id) FROM (
          SELECT id,trace_id,title,recorded_at,reward,revision_id,rolling_mean,window_count
          FROM rolling WHERE position=1 OR position=total OR revision_first=1 OR revision_last=1
            OR mod(position, greatest(1,ceil(total/500.0)::int))=0
        ) p),'[]'::jsonb) AS points""",
        owner,
        agent,
        model_id,
        window,
        program_id,
        active_revision,
        model["finished_at"],
    )
    return {
        "agent": agent,
        "model_id": model_id,
        "program_id": program_id,
        "active_revision_id": active_revision,
        "unit": unit,
        "window": window,
        **dict(row),
    }
