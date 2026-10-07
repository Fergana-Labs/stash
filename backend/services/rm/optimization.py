"""Owner-scoped online prompt experiments with immutable evidence and outcomes."""

import json
import secrets

from ...database import get_pool
from . import optimization_policy as policy
from .workbench_evaluation import boundary


async def owned(owner, optimization_id, conn=None, *, lock=False):
    row = await (conn or get_pool()).fetchrow(
        "SELECT * FROM rm_optimizations WHERE id=$1 AND owner_user_id=$2"
        + (" FOR UPDATE" if lock else ""),
        optimization_id,
        owner,
    )
    if not row:
        raise LookupError("Optimization not found")
    return dict(row)


async def event(conn, program, kind, detail):
    await conn.execute(
        "INSERT INTO rm_optimization_events(optimization_id,kind,detail) VALUES($1,$2,$3)",
        program,
        kind,
        detail,
    )


async def create(owner, body):
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))",
            f"optimization:{owner}:{body['agent']}:{body['scope']}",
        )
        if await conn.fetchval(
            "SELECT 1 FROM rm_optimizations WHERE owner_user_id=$1 AND agent=$2 AND scope=$3 AND status IN ('waiting_model','active')",
            owner,
            body["agent"],
            body["scope"],
        ):
            raise ValueError("An optimization is already active for this agent and scope")
        model = await conn.fetchrow(
            "SELECT * FROM rm_reward_models WHERE id=$1 AND owner_user_id=$2 AND scope='personal'",
            body["reward_model_id"],
            owner,
        )
        if not model:
            raise LookupError("Reward model not found")
        if model["status"] == "failed":
            raise ValueError("Train a successful reward model before starting optimization")
        if model["status"] == "succeeded":
            validate_model(model)
        program = await conn.fetchrow(
            """INSERT INTO rm_optimizations
            (owner_user_id,reward_model_id,name,agent,scope,metric,status,runs_per_arm,max_rounds)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
            owner,
            model["id"],
            body["name"],
            body["agent"],
            body["scope"],
            body["metric"],
            "active" if model["status"] == "succeeded" else "waiting_model",
            body["runs_per_arm"],
            body["max_rounds"],
        )
        revision = await conn.fetchval(
            """INSERT INTO rm_prompt_revisions
            (optimization_id,version,content,rationale) VALUES($1,1,$2,'Original instructions') RETURNING id""",
            program["id"],
            body["initial_prompt"],
        )
        await conn.execute(
            "UPDATE rm_optimizations SET active_revision_id=$2 WHERE id=$1", program["id"], revision
        )
        await event(
            conn,
            program["id"],
            "started",
            {
                "policy": policy.POLICY_VERSION,
                "reward_model_id": str(model["id"]),
                "metric": body["metric"],
                "runs_per_arm": body["runs_per_arm"],
                "max_rounds": body["max_rounds"],
            },
        )
    return await detail(owner, program["id"])


def validate_model(model):
    if not model["artifact_key"] or (model["metrics"] or {}).get("action_scoring_version") != 1:
        raise ValueError("Train an action reward model before starting optimization")


async def list_programs(owner):
    return [
        dict(r)
        for r in await get_pool().fetch(
            """SELECT o.*,m.name AS reward_model_name,
        (SELECT count(*) FROM rm_optimization_runs r WHERE r.optimization_id=o.id)::int AS run_count
        FROM rm_optimizations o JOIN rm_reward_models m ON m.id=o.reward_model_id
        WHERE o.owner_user_id=$1 ORDER BY o.created_at DESC""",
            owner,
        )
    ]


async def detail(owner, optimization_id):
    program = await owned(owner, optimization_id)
    pool = get_pool()
    program["reward_model"] = dict(
        await pool.fetchrow(
            "SELECT id,name,status,error FROM rm_reward_models WHERE id=$1",
            program["reward_model_id"],
        )
    )
    program["revisions"] = [
        dict(r)
        for r in await pool.fetch(
            "SELECT * FROM rm_prompt_revisions WHERE optimization_id=$1 ORDER BY version",
            optimization_id,
        )
    ]
    rounds = [
        dict(r)
        for r in await pool.fetch(
            """SELECT id,number,baseline_id,candidate_id,status,
        report,error,created_at,finished_at FROM rm_optimization_rounds WHERE optimization_id=$1 ORDER BY number DESC""",
            optimization_id,
        )
    ]
    for row in rounds:
        if row["status"] == "collecting":
            runs = await pool.fetch(
                "SELECT arm,status,reward,outcome FROM rm_optimization_runs WHERE round_id=$1",
                row["id"],
            )
            row["report"] = policy.compare(runs, program["runs_per_arm"], program["metric"])
    program["rounds"] = rounds
    program["runs"] = [
        dict(r)
        for r in await pool.fetch(
            """SELECT id,round_id,revision_id,work_key,
        agent_version,arm,status,trace_id,reward,outcome,outcome_source,outcome_at,error,assigned_at,finished_at
        FROM rm_optimization_runs WHERE optimization_id=$1 ORDER BY assigned_at DESC LIMIT 100""",
            optimization_id,
        )
    ]
    # Aggregate all observations, not just the paged recent-run list. Group by
    # assignment date so late outcomes stay in their original workload cohort.
    program["trends"] = [
        dict(r)
        for r in await pool.fetch(
            """SELECT
        (assigned_at AT TIME ZONE 'UTC')::date AS day, revision_id,
        count(*)::int AS assigned, count(reward)::int AS scored, count(outcome)::int AS measured,
        avg(reward) AS reward, avg(outcome) AS business
        FROM rm_optimization_runs WHERE optimization_id=$1
        GROUP BY 1,2 ORDER BY 1,2""",
            optimization_id,
        )
    ]
    program["events"] = [
        dict(r)
        for r in await pool.fetch(
            "SELECT kind,detail,created_at FROM rm_optimization_events WHERE optimization_id=$1 ORDER BY created_at DESC LIMIT 100",
            optimization_id,
        )
    ]
    return program


async def control(owner, optimization_id, action, revision_id=None):
    async with get_pool().acquire() as conn, conn.transaction():
        program = await owned(owner, optimization_id, conn, lock=True)
        if action == "rollback":
            revision = await conn.fetchrow(
                "SELECT * FROM rm_prompt_revisions WHERE id=$1 AND optimization_id=$2",
                revision_id,
                optimization_id,
            )
            if not revision:
                raise LookupError("Prompt version not found")
            if revision["version"] != 1 and not await conn.fetchval(
                "SELECT 1 FROM rm_optimization_rounds WHERE optimization_id=$1 AND candidate_id=$2 AND status='promoted'",
                optimization_id,
                revision_id,
            ):
                raise ValueError("Rollback requires an original or previously promoted prompt")
            await conn.execute(
                "UPDATE rm_optimizations SET active_revision_id=$2,status='paused',error=NULL,updated_at=now() WHERE id=$1",
                optimization_id,
                revision_id,
            )
            await conn.execute(
                """UPDATE rm_optimization_rounds SET status='cancelled',lease_token=NULL,
                finished_at=now() WHERE optimization_id=$1 AND status IN ('queued','generating','collecting')""",
                optimization_id,
            )
        elif action == "resume":
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"optimization:{owner}:{program['agent']}:{program['scope']}",
            )
            if program["status"] == "completed":
                raise ValueError(
                    "This optimization reached its round limit; start another to authorize more rounds"
                )
            if await conn.fetchval(
                "SELECT 1 FROM rm_optimizations WHERE owner_user_id=$1 AND agent=$2 AND scope=$3 AND id<>$4 AND status IN ('waiting_model','active')",
                owner,
                program["agent"],
                program["scope"],
                optimization_id,
            ):
                raise ValueError("Another optimization is already active for this agent and scope")
            await conn.execute(
                """UPDATE rm_optimizations SET status='waiting_model',error=NULL,updated_at=now()
                WHERE id=$1""",
                optimization_id,
            )
            # Failed work requires explicit resume; provider errors do not
            # silently consume an unbounded stream of paid attempts.
            await conn.execute(
                """UPDATE rm_optimization_rounds SET status='queued',attempts=0,error=NULL,
                dispatched_at=NULL WHERE optimization_id=$1 AND status='failed' AND candidate_id IS NULL""",
                optimization_id,
            )
            await conn.execute(
                """UPDATE rm_optimization_runs SET status='queued',attempts=0,error=NULL,
                dispatched_at=NULL WHERE optimization_id=$1 AND status='failed'""",
                optimization_id,
            )
        else:
            await conn.execute(
                "UPDATE rm_optimizations SET status='paused',updated_at=now() WHERE id=$1",
                optimization_id,
            )
        await event(
            conn,
            optimization_id,
            action,
            {"revision_id": str(revision_id) if revision_id else None},
        )
    return await detail(owner, optimization_id)


async def assign(owner, optimization_id, body):
    async with get_pool().acquire() as conn, conn.transaction():
        program = await owned(owner, optimization_id, conn, lock=True)
        if (body["agent"], body["scope"]) != (program["agent"], program["scope"]):
            raise ValueError("Agent and scope must match this optimization exactly")
        run = await conn.fetchrow(
            "SELECT * FROM rm_optimization_runs WHERE optimization_id=$1 AND work_key=$2",
            optimization_id,
            body["work_key"],
        )
        if run and run["agent_version"] != body["agent_version"]:
            raise ValueError("This task was already assigned to a different agent version")
        if not run:
            if program["status"] not in ("active", "completed"):
                return {
                    "enabled": False,
                    "status": program["status"],
                    "instruction": "",
                    "run_id": None,
                }
            round_ = await conn.fetchrow(
                "SELECT * FROM rm_optimization_rounds WHERE optimization_id=$1 AND status='collecting'",
                optimization_id,
            )
            arm, revision_id, round_id = "current", program["active_revision_id"], None
            if round_:
                if round_["agent_version"] and round_["agent_version"] != body["agent_version"]:
                    raise ValueError(
                        "Keep the agent version fixed during a comparison; pause and start a new optimization after changing the agent"
                    )
                await conn.execute(
                    "UPDATE rm_optimization_rounds SET agent_version=$2 WHERE id=$1",
                    round_["id"],
                    body["agent_version"],
                )
                counts = {
                    r["arm"]: r["n"]
                    for r in await conn.fetch(
                        "SELECT arm,count(*) AS n FROM rm_optimization_runs WHERE round_id=$1 GROUP BY arm",
                        round_["id"],
                    )
                }
                available = [
                    a
                    for a in ("baseline", "candidate")
                    if counts.get(a, 0) < program["runs_per_arm"]
                ]
                if available:
                    arm = secrets.choice(available)
                    revision_id = (
                        round_["candidate_id"] if arm == "candidate" else round_["baseline_id"]
                    )
                    round_id = round_["id"]
            run = await conn.fetchrow(
                """INSERT INTO rm_optimization_runs
                (optimization_id,round_id,revision_id,work_key,agent_version,arm,capture_external_id)
                VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
                optimization_id,
                round_id,
                revision_id,
                body["work_key"],
                body["agent_version"],
                arm,
                body.get("session_id") or body["work_key"],
            )
        revision = await conn.fetchrow(
            "SELECT * FROM rm_prompt_revisions WHERE id=$1", run["revision_id"]
        )
        return {
            "enabled": True,
            "run_id": run["id"],
            "revision_id": revision["id"],
            "version": revision["version"],
            "instruction": policy.instruction(run, revision),
            "metric": program["metric"],
            "status": run["status"],
        }


async def run_access(owner, run_id, conn, *, lock=False):
    program_id = await conn.fetchval(
        """SELECT r.optimization_id FROM rm_optimization_runs r
        JOIN rm_optimizations o ON o.id=r.optimization_id WHERE r.id=$1 AND o.owner_user_id=$2""",
        run_id,
        owner,
    )
    if not program_id:
        raise LookupError("Run not found")
    program = await owned(owner, program_id, conn, lock=lock)
    run = await conn.fetchrow(
        "SELECT * FROM rm_optimization_runs WHERE id=$1" + (" FOR UPDATE" if lock else ""), run_id
    )
    return program, dict(run)


async def submit(owner, run_id, trace_id):
    async with get_pool().acquire() as conn, conn.transaction():
        program, run = await run_access(owner, run_id, conn, lock=True)
        if run["submitted_at"]:
            if run["trace_id"] != trace_id:
                raise ValueError("This run already has immutable trace evidence")
            return {"id": run_id, "status": run["status"]}
        if run["status"] != "assigned":
            raise ValueError("Only an assigned run can receive a trace")
        trace = await conn.fetchrow(
            "SELECT * FROM rm_traces WHERE id=$1 AND owner_user_id=$2 FOR SHARE", trace_id, owner
        )
        if not trace:
            raise LookupError("Trace not found")
        model = await conn.fetchrow(
            "SELECT * FROM rm_reward_models WHERE id=$1", program["reward_model_id"]
        )
        if trace_id in model["trace_ids"]:
            raise ValueError(
                "Online evaluation must use fresh tasks, separate from reward-model training"
            )
        steps = [
            dict(s)
            for s in await conn.fetch(
                "SELECT * FROM rm_trace_steps WHERE trace_id=$1 ORDER BY idx", trace_id
            )
        ]
        if not boundary(steps):
            raise ValueError("Wait for a completed assistant response before submitting the trace")
        revision = await conn.fetchrow(
            "SELECT * FROM rm_prompt_revisions WHERE id=$1", run["revision_id"]
        )
        wrapper = policy.instruction(run, revision)
        receipt = next(
            (
                i
                for i, s in enumerate(steps)
                if any(wrapper in text for text in policy.content_strings(s["content"]))
            ),
            None,
        )
        if receipt is None or not any(s["role"] == "assistant" for s in steps[receipt + 1 :]):
            raise ValueError(
                "The recorded trace must contain the exact assigned instructions before the agent response"
            )
        # An existing coding session can contain multiple tasks. Only actions
        # after this task's recorded assignment become this run's measurements.
        targets = steps[receipt + 1 :]
        if any(
            "<stash-optimization" in text
            for s in targets
            for text in policy.content_strings(s["content"])
        ):
            raise ValueError(
                "Submit the completed run before requesting instructions for another task in this trace"
            )
        items = policy.score_items(steps, trace_id, model, {s["id"] for s in targets})
        if not items:
            raise ValueError("No agent actions to score")
        cleaned = policy.clean_steps(targets)
        evidence_hash = policy.digest(
            [{k: s.get(k) for k in ("role", "content", "tool_name", "tool_input")} for s in cleaned]
        )
        duplicate = await conn.fetchval(
            "SELECT id FROM rm_optimization_runs WHERE optimization_id=$1 AND evidence_hash=$2",
            program["id"],
            evidence_hash,
        )
        if duplicate:
            raise ValueError("This task evidence was already submitted to this optimization")
        snapshot = json.loads(json.dumps(steps, default=str))
        await conn.execute(
            """UPDATE rm_optimization_runs SET trace_id=$2,trace_snapshot=$3,
            evidence_hash=$4,submission_hash=$5,score_items=$6,status='queued',error=NULL,submitted_at=now() WHERE id=$1""",
            run_id,
            trace_id,
            snapshot,
            evidence_hash,
            policy.digest(snapshot),
            items,
        )
        return {"id": run_id, "status": "queued"}


async def record_outcome(owner, run_id, value, source):
    async with get_pool().acquire() as conn, conn.transaction():
        program, run = await run_access(owner, run_id, conn, lock=True)
        metric = program["metric"]
        if not metric["minimum"] <= value <= metric["maximum"]:
            raise ValueError("Outcome is outside the configured metric range")
        if run["outcome"] is not None:
            if run["outcome"] != value or run["outcome_source"] != source:
                raise ValueError("This run already has an immutable business outcome")
        else:
            await conn.execute(
                "UPDATE rm_optimization_runs SET outcome=$2,outcome_source=$3,outcome_at=now() WHERE id=$1",
                run_id,
                value,
                source,
            )
            await event(
                conn,
                program["id"],
                "business_outcome",
                {"run_id": str(run_id), "value": value, "source": source},
            )
        return {"id": run_id, "outcome": value, "source": source}


async def abandon(owner, run_id, reason):
    async with get_pool().acquire() as conn, conn.transaction():
        program, run = await run_access(owner, run_id, conn, lock=True)
        if run["status"] == "completed":
            raise ValueError("Completed runs cannot be removed from a comparison")
        await conn.execute(
            "UPDATE rm_optimization_runs SET status='abandoned',lease_token=NULL,error=$2,finished_at=now() WHERE id=$1",
            run_id,
            reason,
        )
        await event(conn, program["id"], "run_abandoned", {"run_id": str(run_id), "reason": reason})
    return {"id": run_id, "status": "abandoned"}


async def run_detail(owner, run_id):
    async with get_pool().acquire() as conn:
        _, run = await run_access(owner, run_id, conn)
        return run
