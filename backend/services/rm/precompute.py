"""Eager scoring after readiness, with bounded cost and durable dispatch."""

from ...database import get_pool

MAX_ACTIVE_BATCHES = 2
TRACES_PER_BATCH = 8
MAX_ATTEMPTS = 3


async def schedule() -> None:
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Serialize overlapping beat ticks, not GPU inference. New explicit
        # runs keep standalone dispatch; queued batch requests get priority.
        if not await conn.fetchval("SELECT pg_try_advisory_xact_lock(73628361)"):
            return
        active = await conn.fetchval(
            "SELECT count(*) FROM rm_scoring_batches WHERE status IN ('queued','running')"
        )
        for _ in range(max(0, MAX_ACTIVE_BATCHES - active)):
            pending = await conn.fetch(
                """WITH candidate AS (
                    SELECT m.id,m.owner_user_id,m.finished_at,m.metrics
                    FROM rm_reward_models m
                    WHERE m.scope='personal' AND m.compute='modal' AND m.status='succeeded'
                    AND m.artifact_key IS NOT NULL AND m.finished_at IS NOT NULL
                    AND (m.metrics->>'action_scoring_version'='1' OR m.metrics->>'trace_scoring_version'='1')
                    AND NOT EXISTS (SELECT 1 FROM rm_scoring_batches b WHERE b.reward_model_id=m.id
                        AND b.status IN ('queued','running'))
                ), work AS (
                    SELECT m.id AS model_id,m.owner_user_id,t.id AS trace_id,t.updated_at
                    FROM candidate m JOIN rm_traces t ON t.owner_user_id=m.owner_user_id
                    WHERE t.updated_at < now()-interval '30 seconds'
                    AND EXISTS (SELECT 1 FROM rm_trace_steps s WHERE s.trace_id=t.id AND s.role='assistant'
                        AND (s.tool_name IS NOT NULL OR btrim(s.content)<>'')
                        AND (m.metrics->>'trace_scoring_version'='1' OR coalesce(m.metrics->>'input_version','1')<>'3'
                            OR coalesce(s.metadata->>'thinking','false')<>'true'))
                    AND NOT EXISTS (SELECT 1 FROM rm_scoring_runs r WHERE r.trace_id=t.id AND r.reward_model_id=m.id
                        AND (r.status IN ('queued','running') OR (r.status='succeeded'
                            AND r.trace_updated_at=t.updated_at AND r.model_finished_at=m.finished_at)))
                    AND (SELECT count(*) FROM rm_scoring_runs r WHERE r.trace_id=t.id AND r.reward_model_id=m.id
                        AND r.automatic AND r.status='failed' AND r.trace_updated_at=t.updated_at
                        AND r.created_at>=m.finished_at) < $1
                ), next_model AS (
                    SELECT w.model_id FROM work w GROUP BY w.model_id
                    ORDER BY (SELECT max(b.created_at) FROM rm_scoring_batches b
                        WHERE b.reward_model_id=w.model_id) NULLS FIRST,w.model_id LIMIT 1
                )
                SELECT w.* FROM work w JOIN next_model n ON n.model_id=w.model_id
                ORDER BY w.updated_at DESC,w.trace_id LIMIT $2""",
                MAX_ATTEMPTS,
                TRACES_PER_BATCH,
            )
            if not pending:
                break
            first = pending[0]
            batch_id = await conn.fetchval(
                "INSERT INTO rm_scoring_batches(owner_user_id,reward_model_id) VALUES($1,$2) RETURNING id",
                first["owner_user_id"],
                first["model_id"],
            )
            count = 0
            for trace in pending:
                # The unique active-run index also resolves a race with Run.
                created = await conn.fetchval(
                    """INSERT INTO rm_scoring_runs(owner_user_id,trace_id,reward_model_id,automatic,trace_updated_at,batch_id,model_finished_at)
                    SELECT $1,t.id,$3,true,t.updated_at,$4,m.finished_at FROM rm_traces t
                    JOIN rm_reward_models m ON m.id=$3 WHERE t.id=$2 AND t.owner_user_id=$1
                    ON CONFLICT(trace_id,reward_model_id)
                    WHERE status IN ('queued','running') DO NOTHING RETURNING id""",
                    trace["owner_user_id"],
                    trace["trace_id"],
                    trace["model_id"],
                    batch_id,
                )
                count += created is not None
            if not count:
                await conn.execute(
                    "UPDATE rm_scoring_batches SET status='succeeded',finished_at=now() WHERE id=$1",
                    batch_id,
                )


async def fail(batch_id, error) -> None:
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """UPDATE rm_scoring_runs SET status='failed',error=$2,finished_at=now()
            WHERE batch_id=$1 AND status IN ('queued','running')""",
            batch_id,
            error[-2000:],
        )
        await conn.execute(
            """UPDATE rm_scoring_batches SET status='failed',error=$2,finished_at=now()
            WHERE id=$1 AND status IN ('queued','running')""",
            batch_id,
            error[-2000:],
        )


async def reconcile() -> None:
    from ...tasks import reward_models as tasks

    pool = get_pool()
    # A worker can finish the last trace just before its container/connection
    # disappears. The trace publications are the source of truth for completion.
    await pool.execute("""UPDATE rm_scoring_batches b SET finished_at=now(),
        status=CASE WHEN EXISTS (SELECT 1 FROM rm_scoring_runs r WHERE r.batch_id=b.id AND r.status='failed')
            THEN 'failed' ELSE 'succeeded' END
        WHERE b.status='running' AND NOT EXISTS (SELECT 1 FROM rm_scoring_runs r
            WHERE r.batch_id=b.id AND r.status IN ('queued','running'))""")
    expired = await pool.fetch(
        "SELECT id FROM rm_scoring_batches WHERE status='running' AND started_at<now()-interval '35 minutes'"
    )
    for batch in expired:
        await fail(batch["id"], "Background scoring worker exceeded its recovery deadline")
    await schedule()
    batches = await pool.fetch(
        "SELECT id FROM rm_scoring_batches WHERE status='queued' ORDER BY created_at LIMIT $1",
        MAX_ACTIVE_BATCHES,
    )
    for batch in batches:
        tasks.score_batch.delay(str(batch["id"]))
