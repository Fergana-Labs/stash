"""Bounded repair of unreviewed corrections drafted without their user context."""

from ...database import get_pool

REPAIR_ACTION = "context_repair_v2"
MAX_REPAIRS_PER_PASS = 30
MAX_REPAIR_ATTEMPTS = 3
REPAIR_COOLDOWN_SECONDS = 60

# Repeat these predicates after taking the owner's mutation lock: the first
# query only chooses a bounded batch, and human review can happen before claim.
_ELIGIBLE = f"""
    f.source='trace_extraction' AND f.review_status='pending'
    AND f.status IN ('completed','failed')
    AND f.reviewed_by IS NULL AND f.reviewed_at IS NULL
    AND u.reward_models_enabled AND u.product_checkpoint='latest'
    AND coalesce(f.interpretation->>'draft_context_version','') <> '2'
    AND EXISTS (
        SELECT 1 FROM rm_trace_steps s WHERE s.id=f.source_event_id
        AND s.trace_id=f.trace_id AND s.role='user'
    )
    AND NOT EXISTS (
        SELECT 1 FROM rm_wb_history h WHERE h.record_type='feedback'
        AND h.record_id=f.id AND h.action IN ('accept','reject')
    )
    AND (SELECT count(*) FROM rm_wb_history h WHERE h.record_type='feedback'
        AND h.record_id=f.id AND h.action='context_repair_v2' AND h.actor_user_id IS NULL
    ) < {MAX_REPAIR_ATTEMPTS}
    AND (f.status='completed' OR NOT EXISTS (
        SELECT 1 FROM rm_wb_history h WHERE h.record_type='feedback'
        AND h.record_id=f.id AND h.action='context_repair_v2' AND h.actor_user_id IS NULL
    ))
    AND NOT EXISTS (
        SELECT 1 FROM rm_wb_history h WHERE h.record_type='feedback'
        AND h.record_id=f.id AND h.action='context_repair_v2' AND h.actor_user_id IS NULL
        AND h.created_at > now()-make_interval(secs => {REPAIR_COOLDOWN_SECONDS})
    )
    AND NOT EXISTS (
        SELECT 1 FROM rm_wb_changes c WHERE c.feedback_id=f.id AND (
            c.status IN ('checking','released') OR c.released_at IS NOT NULL
            OR (c.status='rejected' AND NOT EXISTS (
                SELECT 1 FROM rm_wb_history h WHERE h.record_type='change'
                AND h.record_id=c.id AND h.action='context_repair_v2' AND h.actor_user_id IS NULL
                AND h.created_at=c.updated_at
            ))
            OR EXISTS (SELECT 1 FROM rm_wb_history h WHERE h.record_type='change'
                AND h.record_id=c.id AND h.action='edited')
            OR EXISTS (SELECT 1 FROM rm_wb_instruction_releases r WHERE r.change_id=c.id)
        )
    )
"""


async def recover() -> int:
    """Queue at most 30 legacy drafts, preserving their complete audit history.

    No model call happens here. The existing feedback dispatcher processes the
    queued rows. During rolling deployment an older worker may complete a repair
    using legacy context again. Only those completed legacy outputs can retry,
    at least a minute apart and at most three repairs total. Failed replacements
    and any v2 attempt remain untouched; this is not a provider-failure retry.
    """
    from .workbench import history, mutation_lock

    pool = get_pool()
    candidates = await pool.fetch(
        f"""SELECT f.id,f.owner_user_id FROM rm_wb_feedback f
        JOIN users u ON u.id=f.owner_user_id WHERE {_ELIGIBLE}
        ORDER BY f.created_at,f.id LIMIT $1""",
        MAX_REPAIRS_PER_PASS,
    )
    repaired = 0
    for candidate in candidates:
        async with pool.acquire() as conn, conn.transaction():
            # Review, draft edits and release all take this lock before row locks.
            # Taking the feedback lock first would invert their lock ordering.
            await mutation_lock(conn, candidate["owner_user_id"])
            feedback = await conn.fetchrow(
                f"""SELECT f.* FROM rm_wb_feedback f JOIN users u ON u.id=f.owner_user_id
                WHERE f.id=$1 AND {_ELIGIBLE} FOR UPDATE OF f""",
                candidate["id"],
            )
            if feedback is None:
                continue
            changes = await conn.fetch(
                "SELECT * FROM rm_wb_changes WHERE feedback_id=$1 ORDER BY id FOR UPDATE",
                feedback["id"],
            )
            # Checking workers do not take the owner lock; preserve any claim
            # that became active between candidate selection and the row lock.
            if any(c["status"] in {"checking", "released"} for c in changes):
                continue
            await history(
                conn,
                feedback["owner_user_id"],
                None,
                "feedback",
                feedback["id"],
                REPAIR_ACTION,
                dict(feedback),
            )
            for change in changes:
                # Matching archive/update timestamps prove this is still the
                # automatic rejection, not a later explicit human rejection.
                if change["status"] == "rejected":
                    continue
                await history(
                    conn,
                    feedback["owner_user_id"],
                    None,
                    "change",
                    change["id"],
                    REPAIR_ACTION,
                    dict(change),
                )
                await conn.execute(
                    """UPDATE rm_wb_changes SET status='rejected',check_report=NULL,
                    error=NULL,updated_at=now() WHERE id=$1""",
                    change["id"],
                )
            await conn.execute(
                """UPDATE rm_wb_feedback SET status='queued',change_kind='unclear',
                proposed_verdict=NULL,interpretation=NULL,error=NULL,updated_at=now()
                WHERE id=$1""",
                feedback["id"],
            )
            repaired += 1
    return repaired
