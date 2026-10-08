"""Automatic Jev evaluations over immutable recorded trace versions."""

from __future__ import annotations

import logging

import asyncpg

from ...config import settings
from ...database import get_pool
from ...product_checkpoints import has_workbench
from . import workbench as legacy
from . import workbench_evaluation as policy
from . import workbench_grader as jev
from . import workbench_instructions as instructions

log = logging.getLogger(__name__)
MAX_CALLS_PER_PASS = 12
SCHEMA_CACHE_ERROR = (
    "cached statement plan is invalid due to a database schema or configuration change"
)
MISSING_REPOSITORY = (
    "The capture has no repository directory; instruction changes need a recorded repository scope"
)


def instruction_config():
    return jev.validate_config(
        {
            "criteria": [
                {
                    "id": "agent_behavior",
                    "name": "Fulfill the user request",
                    "description": "Propose agent instructions supported by the recorded requests, results and human corrections.",
                }
            ]
        }
    )


class LeaseLost(Exception):
    pass


async def ensure_instruction_scope(trace):
    """An internal release channel, never a user-created evaluation configuration."""
    scope = {"source_format": trace["source_format"]}
    cwd = (trace.get("metadata") or {}).get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        return None  # Interpretation is still possible; a safe release scope is not.
    scope["repository"] = cwd.strip().rstrip("/") or "/"
    owner = trace["owner_user_id"]
    async with get_pool().acquire() as conn, conn.transaction():
        await legacy.mutation_lock(conn, owner)
        row = await conn.fetchrow(
            "SELECT * FROM rm_wb_graders WHERE owner_user_id=$1 AND builtin AND scope=$2",
            owner,
            scope,
        )
        if not row:
            row = await conn.fetchrow(
                "INSERT INTO rm_wb_graders(owner_user_id,name,scope,builtin) VALUES($1,'Agent instructions',$2,true) RETURNING *",
                owner,
                scope,
            )
            config = instruction_config()
            version = await conn.fetchval(
                "INSERT INTO rm_wb_grader_versions(grader_id,version,config) VALUES($1,1,$2) RETURNING id",
                row["id"],
                config,
            )
            await conn.execute(
                "UPDATE rm_wb_graders SET active_version_id=$2 WHERE id=$1", row["id"], version
            )
        result = await conn.fetchrow(
            "SELECT g.*,to_jsonb(v.*) AS active_version FROM rm_wb_graders g JOIN rm_wb_grader_versions v ON v.id=g.active_version_id WHERE g.id=$1",
            row["id"],
        )
        return dict(result)


async def _read_trace(trace_id):
    async with get_pool().acquire() as conn, conn.transaction(isolation="repeatable_read"):
        row = await conn.fetchrow(
            "SELECT t.*,u.reward_models_enabled,u.product_checkpoint FROM rm_traces t JOIN users u ON u.id=t.owner_user_id WHERE t.id=$1",
            trace_id,
        )
        if not row:
            raise LookupError("Trace not found")
        steps = [
            dict(r)
            for r in await conn.fetch(
                "SELECT *,idx AS index FROM rm_trace_steps WHERE trace_id=$1 ORDER BY idx", trace_id
            )
        ]
    return dict(row), steps


async def process_trace(trace_id):
    pool = get_pool()
    claim = await pool.fetchrow(
        "UPDATE rm_wb_queue SET status='running',started_at=now(),attempts=attempts+1 WHERE trace_id=$1 AND status='queued' RETURNING *",
        trace_id,
    )
    if not claim:
        return
    evaluation = None
    try:
        trace, steps = await _read_trace(trace_id)
        if not has_workbench(trace):
            await _finish_queue(trace_id, claim, "completed")
            return
        await instructions.observe_trace(
            trace["owner_user_id"], trace["external_id"], trace_id, steps
        )
        if policy.boundary(steps) is None:
            await _finish_queue(trace_id, claim, "waiting")
            return
        fingerprint = policy.revision_hash(steps)
        evaluation = await pool.fetchrow(
            """INSERT INTO rm_wb_evaluations
            (owner_user_id,trace_id,revision_hash,policy_version,model,boundary,trace_snapshot,total_actions,trace_updated_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT(trace_id,revision_hash,policy_version,model) DO UPDATE SET trace_updated_at=greatest(rm_wb_evaluations.trace_updated_at,EXCLUDED.trace_updated_at) RETURNING *""",
            trace["owner_user_id"],
            trace_id,
            fingerprint,
            policy.POLICY_VERSION,
            settings.JEV_MODEL,
            policy.boundary(steps),
            legacy.serial(steps),
            sum(policy.action(s) for s in steps),
            trace["updated_at"],
        )
        # Reuse saved evidence on retries, including evidence after each target.
        frozen = evaluation["trace_snapshot"]
        work = policy.batches(frozen)
        completed = {
            r["batch_index"]
            for r in await pool.fetch(
                "SELECT batch_index FROM rm_wb_evaluation_calls WHERE evaluation_id=$1 AND status='completed'",
                evaluation["id"],
            )
        }
        pending = [i for i in range(len(work)) if i not in completed]
        for i in pending[:MAX_CALLS_PER_PASS]:
            snapshot = policy.build_input(frozen, work[i], model=evaluation["model"])
            await _call(evaluation, i, snapshot, claim)
        more = len(pending) > MAX_CALLS_PER_PASS
        if not more:
            await pool.execute(
                "UPDATE rm_wb_evaluations SET status='completed',error=NULL,finished_at=coalesce(finished_at,now()) WHERE id=$1 AND EXISTS(SELECT 1 FROM rm_wb_queue q WHERE q.trace_id=rm_wb_evaluations.trace_id AND q.status='running' AND q.started_at=$2)",
                evaluation["id"],
                claim["started_at"],
            )
        from . import workbench_capture

        capture = await workbench_capture.scan_trace(trace, steps)
        await _finish_queue(
            trace_id,
            claim,
            "queued" if more or capture["more"] or capture["budget_limited"] else "completed",
            tomorrow=capture["budget_limited"] and not more and not capture["more"],
        )
    except LeaseLost:
        return  # A replacement worker owns the queue and any further status changes.
    except Exception as exc:
        if evaluation:
            await pool.execute(
                "UPDATE rm_wb_evaluations SET status='failed',error=$2 WHERE id=$1 AND status<>'completed' AND EXISTS(SELECT 1 FROM rm_wb_queue q WHERE q.trace_id=rm_wb_evaluations.trace_id AND q.status='running' AND q.started_at=$3)",
                evaluation["id"],
                str(exc)[:1500],
                claim["started_at"],
            )
        log.warning("Automatic Jev evaluation failed: %s", type(exc).__name__)
        retry = (
            isinstance(exc, jev.GradingError) and exc.retryable and getattr(exc, "attempt", 1) < 3
        ) or (isinstance(exc, asyncpg.InvalidCachedStatementError) and claim["attempts"] < 3)
        await _finish_queue(trace_id, claim, "queued" if retry else "failed", str(exc)[:1500])


async def _finish_queue(trace_id, claim, status, error=None, *, tomorrow=False):
    await get_pool().execute(
        """UPDATE rm_wb_queue SET
        status=CASE WHEN requested_at>$2 THEN 'queued' ELSE $3 END,
        due_at=CASE WHEN $5 AND requested_at<=$2 THEN (date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')+interval '1 day' ELSE now()+interval '30 seconds' END,
        error=$4,attempts=CASE WHEN $4::text IS NULL THEN 0 ELSE attempts END,
        processed_at=now() WHERE trace_id=$1 AND status='running' AND started_at=$2""",
        trace_id,
        claim["started_at"],
        status,
        error,
        tomorrow,
    )


async def _call(evaluation, index, snapshot, claim):
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        if not await conn.fetchval(
            "SELECT 1 FROM rm_wb_queue WHERE trace_id=$1 AND status='running' AND started_at=$2 FOR UPDATE",
            evaluation["trace_id"],
            claim["started_at"],
        ):
            raise LeaseLost()
        if await conn.fetchval(
            "SELECT 1 FROM rm_wb_evaluation_calls WHERE evaluation_id=$1 AND batch_index=$2 AND status='completed'",
            evaluation["id"],
            index,
        ):
            return
        attempt = await conn.fetchval(
            "SELECT coalesce(max(attempt),0)+1 FROM rm_wb_evaluation_calls WHERE evaluation_id=$1 AND batch_index=$2",
            evaluation["id"],
            index,
        )
        call_id = await conn.fetchval(
            "INSERT INTO rm_wb_evaluation_calls(evaluation_id,owner_user_id,batch_index,attempt,input_snapshot,status) VALUES($1,$2,$3,$4,$5,'running') RETURNING id",
            evaluation["id"],
            evaluation["owner_user_id"],
            index,
            attempt,
            snapshot,
        )
        await conn.execute(
            "UPDATE rm_wb_evaluations SET status='running',error=NULL WHERE id=$1", evaluation["id"]
        )
    # Nothing can reach the provider before the exact request is durably saved.
    try:
        result = await jev.grade(snapshot)
        async with pool.acquire() as conn, conn.transaction():
            if not await conn.fetchval(
                "SELECT 1 FROM rm_wb_queue WHERE trace_id=$1 AND status='running' AND started_at=$2 FOR UPDATE",
                evaluation["trace_id"],
                claim["started_at"],
            ):
                raise LeaseLost()
            written = await conn.fetchval(
                "UPDATE rm_wb_evaluation_calls SET status='completed',raw_output=$2,result=$3,finished_at=now() WHERE id=$1 AND status='running' RETURNING id",
                call_id,
                result["raw_output"],
                result,
            )
            if not written:
                raise LeaseLost()
            if index == 0:
                answer = result["results"][0]
                await conn.execute(
                    "UPDATE rm_wb_evaluations SET outcome=$2,outcome_confidence=$3,outcome_probabilities=$4 WHERE id=$1",
                    evaluation["id"],
                    answer["verdict"],
                    answer["confidence"],
                    answer["probabilities"],
                )
            else:
                await conn.execute(
                    "UPDATE rm_wb_evaluations SET credited_actions=credited_actions+$2 WHERE id=$1",
                    evaluation["id"],
                    len(snapshot["targets"]),
                )
    except Exception as exc:
        if isinstance(exc, jev.GradingError):
            exc.attempt = attempt
        await pool.execute(
            "UPDATE rm_wb_evaluation_calls SET status='failed',error=$2,raw_output=$3,finished_at=now() WHERE id=$1 AND status='running'",
            call_id,
            str(exc)[:1500],
            legacy.serial(getattr(exc, "raw_output", None)),
        )
        raise


async def detail(user, trace_id):
    await legacy.trace_access(user, trace_id)
    trace, steps = await _read_trace(trace_id)
    fingerprint = policy.revision_hash(steps)
    rows = await get_pool().fetch(
        "SELECT id,revision_hash,policy_version,model,status,outcome,created_at,boundary,credited_actions FROM rm_wb_evaluations WHERE trace_id=$1 ORDER BY created_at DESC",
        trace_id,
    )
    current = next(
        (
            r
            for r in rows
            if r["revision_hash"] == fingerprint
            and r["policy_version"] == policy.POLICY_VERSION
            and r["model"] == settings.JEV_MODEL
        ),
        None,
    )
    queue = await get_pool().fetchrow(
        "SELECT status,error FROM rm_wb_queue WHERE trace_id=$1", trace_id
    )
    result = {
        "provider": "jev",
        "model": settings.JEV_MODEL,
        "configured": bool(settings.TYPESAFE_API_KEY),
        "policy_version": policy.POLICY_VERSION,
        "boundary": policy.boundary(steps),
        "owner_user_id": trace["owner_user_id"],
        "queue": dict(queue) if queue else None,
        "current": None,
        "history": [
            {
                k: r[k]
                for k in ("id", "revision_hash", "status", "outcome", "created_at", "boundary")
            }
            for r in rows
        ],
    }
    if current:
        result["current"] = await historical(user, trace_id, current["id"])
    result["previous_credits"] = await _previous_credits(rows, steps, result["current"])
    return result


async def _previous_credits(rows, steps, current):
    """Display-only annotations while an appended trace is being evaluated.

    Current results (including insufficient evidence) always take precedence.
    Earlier annotations never become current labels or training data.
    """
    if current and current["status"] == "completed":
        return []
    judged = {c["step_id"] for c in current["credits"]} if current else set()
    missing = {
        str(s["id"]): i
        for i, s in enumerate(s for s in steps if policy.action(s))
        if str(s["id"]) not in judged
    }
    credits = []
    for row in rows:
        if not missing:
            break
        if (
            (current and row["id"] == current["id"])
            or row["policy_version"] != policy.POLICY_VERSION
            or row["model"] != settings.JEV_MODEL
            # Calls are completed in action order. Skip prefixes already covered.
            or row["credited_actions"] <= min(missing.values())
        ):
            continue
        previous = await get_pool().fetchrow(
            "SELECT * FROM rm_wb_evaluations WHERE id=$1", row["id"]
        )
        snapshot = previous["trace_snapshot"]
        if (
            len(snapshot) > len(steps)
            or policy.revision_hash(steps[: len(snapshot)]) != row["revision_hash"]
        ):
            continue
        for credit in (await _evaluation_detail(previous))["credits"]:
            if credit["step_id"] in missing:
                missing.pop(credit["step_id"])
                credits.append(
                    {**credit, "evaluation_id": row["id"], "created_at": row["created_at"]}
                )
    return credits


async def historical(user, trace_id, evaluation_id):
    await legacy.trace_access(user, trace_id)
    row = await get_pool().fetchrow(
        "SELECT * FROM rm_wb_evaluations WHERE id=$1 AND trace_id=$2", evaluation_id, trace_id
    )
    if not row:
        raise LookupError("Evaluation not found")
    return await _evaluation_detail(row)


async def _evaluation_detail(row):
    calls = [
        dict(c)
        for c in await get_pool().fetch(
            "SELECT * FROM rm_wb_evaluation_calls WHERE evaluation_id=$1 ORDER BY batch_index,attempt",
            row["id"],
        )
    ]
    credits = []
    for call in calls:
        if call["status"] != "completed":
            continue
        answers = {r["criterion_id"]: r for r in call["result"]["results"]}
        for target in call["input_snapshot"]["targets"]:
            answer = answers[target["question_id"]]
            credits.append(
                {
                    **target,
                    "credit": policy.CREDIT_VALUES[answer["verdict"]],
                    "expected_credit": policy.expected_credit(answer),
                    "credit_method": policy.CREDIT_METHOD,
                    "label": answer["verdict"],
                    "confidence": answer["confidence"],
                    "probabilities": answer["probabilities"],
                    "call_id": call["id"],
                }
            )
    return {
        **{k: v for k, v in dict(row).items() if k != "trace_snapshot"},
        "actions": [
            {
                "id": str(s["id"]),
                "index": s.get("idx", s.get("index")),
                "content": (s.get("content") or "")[:500],
                "tool_name": s.get("tool_name"),
            }
            for s in row["trace_snapshot"]
            if policy.action(s)
        ],
        "credits": sorted(credits, key=lambda c: c["index"]),
        "calls": calls,
    }


async def recover():
    pool = get_pool()
    # Resume work deferred by the removed daily Jev cap, retaining saved calls.
    await pool.execute(
        """UPDATE rm_wb_queue q SET due_at=now(),error=NULL
        FROM rm_traces t JOIN users u ON u.id=t.owner_user_id
        WHERE q.trace_id=t.id AND u.reward_models_enabled AND u.product_checkpoint='latest'
        AND q.status='queued' AND q.error='Daily Jev evaluation budget reached; resumes tomorrow'"""
    )
    await pool.execute(
        "UPDATE rm_wb_evaluation_calls SET status='failed',error='Worker lease expired',finished_at=now() WHERE status='running' AND created_at<now()-interval '20 minutes'"
    )
    # Configuration can arrive after the application deployment. Repair these
    # queued traces automatically once the worker actually has a provider key.
    if settings.TYPESAFE_API_KEY:
        await pool.execute(
            """UPDATE rm_wb_queue q SET status='queued',due_at=now(),attempts=0
            FROM rm_traces t JOIN users u ON u.id=t.owner_user_id
            WHERE q.trace_id=t.id AND u.reward_models_enabled AND u.product_checkpoint='latest'
            AND q.status='failed' AND q.error LIKE 'TYPESAFE_API_KEY is not configured%'"""
        )

    # A pre-upgrade worker could consume migration backfill without creating a
    # fixed-policy evaluation. A completed queue row is not evidence of grading.
    # This sweep preserves running leases, waiting responses and queued work.
    # The removed Jev-cap deferrals are handled separately above.
    # Old malformed-response failures resume only below the per-batch attempt cap.
    await pool.execute(
        """WITH repairable AS (
            SELECT q.trace_id FROM rm_wb_queue q
            JOIN rm_traces t ON t.id=q.trace_id JOIN users u ON u.id=t.owner_user_id
            WHERE u.reward_models_enabled AND u.product_checkpoint='latest' AND (
                (q.status='completed' AND NOT EXISTS (
                    SELECT 1 FROM rm_wb_evaluations e WHERE e.trace_id=t.id
                    AND e.policy_version=$1 AND e.model=$2
                    AND e.trace_updated_at>=t.updated_at AND e.status='completed'
                )) OR (q.status='failed' AND q.error=$3 AND q.attempts<3)
                OR (q.status='failed' AND q.error=ANY($4::text[]) AND EXISTS (
                    SELECT 1 FROM (
                        SELECT e.status AS evaluation_status,c.status,c.error,c.attempt
                        FROM rm_wb_evaluations e JOIN rm_wb_evaluation_calls c ON c.evaluation_id=e.id
                        WHERE e.trace_id=t.id AND e.policy_version=$1 AND e.model=$2
                        AND e.trace_updated_at>=t.updated_at
                        ORDER BY e.created_at DESC,c.created_at DESC LIMIT 1
                    ) last_call WHERE evaluation_status='failed' AND status='failed'
                    AND error=ANY($4::text[]) AND attempt<3
                ))
            ) ORDER BY q.due_at,q.trace_id LIMIT 30 FOR UPDATE OF q SKIP LOCKED
        ) UPDATE rm_wb_queue q SET status='queued',due_at=now(),requested_at=now(),error=NULL
        FROM repairable r WHERE q.trace_id=r.trace_id""",
        policy.POLICY_VERSION,
        settings.JEV_MODEL,
        SCHEMA_CACHE_ERROR,
        [jev.INVALID_RESPONSE, jev.NON_JSON_RESPONSE],
    )
    # Earlier code incorrectly failed the whole interpretation when only the
    # instruction-release scope was unavailable. Preserve review decisions.
    await pool.execute(
        """UPDATE rm_wb_feedback f SET status='queued',error=NULL,updated_at=now()
        FROM users u WHERE f.owner_user_id=u.id AND u.reward_models_enabled
        AND u.product_checkpoint='latest'
        AND f.status='failed' AND f.review_status='pending' AND f.error=$1""",
        MISSING_REPOSITORY,
    )
