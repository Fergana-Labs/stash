"""Bounded repair preserves human decisions, provenance, and original drafts."""

import asyncio
from uuid import UUID, uuid4

import pytest

from backend.services.rm import workbench as service
from backend.services.rm import workbench_feedback_recovery as recovery

from .test_rm_workbench import account, grader, model_and_queue_boundaries, upload  # noqa: F401


async def setup(client, pool):
    user = await account(client)
    tid = await upload(
        client,
        user,
        messages=[
            ("user", "Fix the parser and check the result."),
            ("assistant", "All tests pass."),
            ("user", "No, the zero case failed. Read the actual result."),
        ],
    )
    g = await grader(client, user)
    steps = await pool.fetch("SELECT id FROM rm_trace_steps WHERE trace_id=$1 ORDER BY idx", tid)
    return user, tid, UUID(g["id"]), steps[1]["id"], steps[2]["id"]


async def feedback(pool, fixture, *, status="completed", source_id=None):
    user, tid, _, target, source = fixture
    return dict(
        await pool.fetchrow(
            """INSERT INTO rm_wb_feedback(owner_user_id,author_user_id,trace_id,target_step_id,
        comment,change_kind,proposed_verdict,source,source_event_id,status,interpretation,error)
        VALUES($1,$1,$2,$3,'No, the zero case failed. Read the actual result.',
        'agent_error','violates','trace_extraction',$4,$5,$6,$7) RETURNING *""",
            user["uuid"],
            tid,
            target,
            source_id or source,
            status,
            {
                "explanation": "Old interpretation",
                "input_snapshot": {"target_step_id": str(target)},
            },
            "Old drafting failure" if status == "failed" else None,
        )
    )


async def change(pool, fixture, fid, *, status="draft"):
    user, _, gid, _, _ = fixture
    return dict(
        await pool.fetchrow(
            """INSERT INTO rm_wb_changes(owner_user_id,grader_id,feedback_id,kind,title,content,
        status,check_report,error) VALUES($1,$2,$3,'instruction','Original draft',$4,$5,$6,$7)
        RETURNING *""",
            user["uuid"],
            gid,
            fid,
            {"text": "Inspect test results."},
            status,
            {"passed": True, "original_evidence": "Keep this in history"},
            "Old check message",
        )
    )


async def finish_legacy_repair(pool, fixture, original):
    """An older worker consumed the repair and completed with legacy context."""
    await pool.execute(
        """UPDATE rm_wb_feedback SET status='completed',interpretation=$2,
        change_kind='agent_error',proposed_verdict='violates',updated_at=now() WHERE id=$1""",
        original["id"],
        original["interpretation"],
    )
    return await change(pool, fixture, original["id"])


async def expire_repair_cooldown(pool, fid):
    # Feedback markers determine retry cooldown; change-archive timestamps must
    # remain paired with the automatic rejection's updated_at for provenance.
    await pool.execute(
        """UPDATE rm_wb_history SET created_at=now()-interval '61 seconds'
        WHERE record_type='feedback' AND record_id=$1 AND action=$2 AND actor_user_id IS NULL""",
        fid,
        recovery.REPAIR_ACTION,
    )


@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_repair_preserves_feedback_and_drafts_without_retrying_failed_replacements(
    client,
    pool,
    model_and_queue_boundaries,  # noqa: F811 — imported pytest fixture
    status,
):
    fixture = await setup(client, pool)
    original = await feedback(pool, fixture, status=status)
    originals = [
        await change(pool, fixture, original["id"], status=s) for s in ("draft", "checked")
    ]
    calls_before = list(model_and_queue_boundaries)

    assert await recovery.recover() == 1
    assert model_and_queue_boundaries == calls_before  # Recovery never invokes inference.
    queued = dict(await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", original["id"]))
    assert queued["status"] == "queued" and queued["review_status"] == "pending"
    assert queued["change_kind"] == "unclear"
    assert queued["proposed_verdict"] is queued["interpretation"] is queued["error"] is None
    for key in (
        "id",
        "owner_user_id",
        "author_user_id",
        "trace_id",
        "target_step_id",
        "source_event_id",
        "source",
        "comment",
        "created_at",
    ):
        assert queued[key] == original[key]
    saved = await pool.fetchrow(
        "SELECT * FROM rm_wb_history WHERE record_type='feedback' AND record_id=$1", original["id"]
    )
    assert saved["action"] == recovery.REPAIR_ACTION and saved["actor_user_id"] is None
    assert saved["snapshot"] == service.serial(original)
    for old in originals:
        archived = await pool.fetchrow("SELECT * FROM rm_wb_changes WHERE id=$1", old["id"])
        assert archived["status"] == "rejected" and archived["check_report"] is None
        assert archived["content"] == old["content"]
        assert await pool.fetchval(
            "SELECT snapshot FROM rm_wb_history WHERE record_type='change' AND record_id=$1",
            old["id"],
        ) == service.serial(old)

    assert await recovery.recover() == 0
    # Even a failed replacement with no new interpretation is never requeued twice.
    await pool.execute(
        "UPDATE rm_wb_feedback SET status='failed',error='New failure' WHERE id=$1", original["id"]
    )
    await expire_repair_cooldown(pool, original["id"])
    assert await recovery.recover() == 0
    assert (
        await pool.fetchval("SELECT count(*) FROM rm_wb_history WHERE record_type='feedback'") == 1
    )


async def test_rolling_deployment_legacy_completion_retries_then_v2_stops(client, pool):
    fixture = await setup(client, pool)
    original = await feedback(pool, fixture)
    old_draft = await change(pool, fixture, original["id"])
    assert await recovery.recover() == 1
    first_archive = await pool.fetchrow(
        "SELECT * FROM rm_wb_history WHERE record_type='change' AND record_id=$1", old_draft["id"]
    )
    first_rejection = await pool.fetchrow(
        "SELECT * FROM rm_wb_changes WHERE id=$1", old_draft["id"]
    )

    recreated = await finish_legacy_repair(pool, fixture, original)
    assert await recovery.recover() == 0  # An overlapping old worker cannot burn the retry cap.
    await expire_repair_cooldown(pool, original["id"])
    assert sum(await asyncio.gather(recovery.recover(), recovery.recover())) == 1
    assert (
        await pool.fetchrow("SELECT * FROM rm_wb_changes WHERE id=$1", old_draft["id"])
        == first_rejection
    )
    assert (
        await pool.fetchrow(
            "SELECT * FROM rm_wb_history WHERE record_type='change' AND record_id=$1",
            old_draft["id"],
        )
        == first_archive
    )
    assert (
        await pool.fetchval("SELECT status FROM rm_wb_changes WHERE id=$1", recreated["id"])
        == "rejected"
    )
    assert await pool.fetchval(
        "SELECT snapshot FROM rm_wb_history WHERE record_type='change' AND record_id=$1",
        recreated["id"],
    ) == service.serial(recreated)
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_wb_history WHERE record_type='feedback' AND record_id=$1",
            original["id"],
        )
        == 2
    )

    await pool.execute(
        "UPDATE rm_wb_feedback SET status='completed',interpretation=$2 WHERE id=$1",
        original["id"],
        {"draft_context_version": 2, "explanation": "Corrected with source context"},
    )
    current = await change(pool, fixture, original["id"])
    await expire_repair_cooldown(pool, original["id"])
    assert await recovery.recover() == 0
    assert (
        await pool.fetchval("SELECT status FROM rm_wb_changes WHERE id=$1", current["id"])
        == "draft"
    )


async def test_legacy_worker_retries_stop_at_three_repairs(client, pool):
    fixture = await setup(client, pool)
    original = await feedback(pool, fixture)
    await change(pool, fixture, original["id"])
    for _ in range(recovery.MAX_REPAIR_ATTEMPTS):
        assert await recovery.recover() == 1
        latest = await finish_legacy_repair(pool, fixture, original)
        await expire_repair_cooldown(pool, original["id"])
    assert recovery.MAX_REPAIR_ATTEMPTS == 3
    assert await recovery.recover() == 0
    assert (
        await pool.fetchval("SELECT status FROM rm_wb_changes WHERE id=$1", latest["id"]) == "draft"
    )
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_wb_history WHERE record_type='feedback' AND record_id=$1",
            original["id"],
        )
        == 3
    )


@pytest.mark.parametrize("status", ["running", "completed", "failed"])
async def test_v2_attempt_is_never_repaired_after_rolling_deployment(client, pool, status):
    fixture = await setup(client, pool)
    original = await feedback(pool, fixture)
    assert await recovery.recover() == 1
    await expire_repair_cooldown(pool, original["id"])
    await pool.execute(
        "UPDATE rm_wb_feedback SET status=$2,interpretation=$3 WHERE id=$1",
        original["id"],
        status,
        {"draft_context_version": 2, "drafting_input": {"saved": True}},
    )
    before = await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", original["id"])
    assert await recovery.recover() == 0
    assert await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", original["id"]) == before


@pytest.mark.parametrize("human_action", ["reject_archived", "reject_new", "edit_new", "review"])
async def test_human_intervention_after_automatic_repair_blocks_rollout_retry(
    client, pool, human_action
):
    fixture = await setup(client, pool)
    user = fixture[0]
    original = await feedback(pool, fixture)
    old_draft = await change(pool, fixture, original["id"])
    assert await recovery.recover() == 1
    recreated = await finish_legacy_repair(pool, fixture, original)
    await expire_repair_cooldown(pool, original["id"])
    if human_action == "reject_archived":
        await service.reject_change(user["uuid"], old_draft["id"])
    elif human_action == "reject_new":
        await service.reject_change(user["uuid"], recreated["id"])
    elif human_action == "edit_new":
        await service.edit_change(
            user["uuid"], recreated["id"], {"content": {"text": "Human revision"}}
        )
    else:
        await service.review_feedback(user["uuid"], original["id"], "accept")
    before_feedback = await pool.fetchrow(
        "SELECT * FROM rm_wb_feedback WHERE id=$1", original["id"]
    )
    before_changes = await pool.fetch("SELECT * FROM rm_wb_changes ORDER BY id")
    assert await recovery.recover() == 0
    assert (
        await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", original["id"])
        == before_feedback
    )
    assert await pool.fetch("SELECT * FROM rm_wb_changes ORDER BY id") == before_changes


@pytest.mark.parametrize(
    "protection",
    [
        "accepted",
        "rejected",
        "reviewed",
        "review_history",
        "running",
        "queued",
        "new_context",
        "human_comment",
        "missing_source",
        "wrong_trace_source",
        "non_user_source",
        "released",
        "previously_released",
        "edited",
        "checking",
        "rejected_change",
        "disabled",
        "checkpoint",
    ],
)
async def test_repair_leaves_protected_feedback_and_changes_unchanged(client, pool, protection):
    fixture = await setup(client, pool)
    user, tid, _, target, _ = fixture
    old = await feedback(pool, fixture)
    draft = await change(pool, fixture, old["id"])
    fid, cid = old["id"], draft["id"]
    if protection in {"accepted", "rejected"}:
        await pool.execute(
            "UPDATE rm_wb_feedback SET review_status=$2 WHERE id=$1", fid, protection
        )
    elif protection == "reviewed":
        await pool.execute(
            "UPDATE rm_wb_feedback SET reviewed_by=$2,reviewed_at=now() WHERE id=$1",
            fid,
            user["uuid"],
        )
    elif protection == "review_history":
        await service.history(pool, user["uuid"], user["uuid"], "feedback", fid, "accept", old)
    elif protection in {"running", "queued"}:
        await pool.execute("UPDATE rm_wb_feedback SET status=$2 WHERE id=$1", fid, protection)
    elif protection == "new_context":
        await pool.execute(
            "UPDATE rm_wb_feedback SET interpretation=$2 WHERE id=$1",
            fid,
            {"draft_context_version": 2},
        )
    elif protection == "human_comment":
        await pool.execute("UPDATE rm_wb_feedback SET source='human_comment' WHERE id=$1", fid)
    elif protection == "missing_source":
        await pool.execute("UPDATE rm_wb_feedback SET source_event_id=$2 WHERE id=$1", fid, uuid4())
    elif protection == "wrong_trace_source":
        other_tid = await upload(client, user, "other-run")
        other_step = await pool.fetchval(
            "SELECT id FROM rm_trace_steps WHERE trace_id=$1 AND role='user'", other_tid
        )
        await pool.execute(
            "UPDATE rm_wb_feedback SET source_event_id=$2 WHERE id=$1", fid, other_step
        )
    elif protection == "non_user_source":
        await pool.execute("UPDATE rm_wb_feedback SET source_event_id=$2 WHERE id=$1", fid, target)
    elif protection in {"released", "checking", "rejected_change"}:
        await pool.execute(
            "UPDATE rm_wb_changes SET status=$2 WHERE id=$1",
            cid,
            "rejected" if protection == "rejected_change" else protection,
        )
    elif protection == "previously_released":
        await pool.execute("UPDATE rm_wb_changes SET released_at=now() WHERE id=$1", cid)
    elif protection == "edited":
        await service.history(pool, user["uuid"], user["uuid"], "change", cid, "edited", draft)
    elif protection == "disabled":
        await pool.execute("UPDATE users SET reward_models_enabled=false WHERE id=$1", user["uuid"])
    elif protection == "checkpoint":
        await pool.execute(
            "UPDATE users SET product_checkpoint='floodgate-2026-10-05' WHERE id=$1", user["uuid"]
        )
    before_feedback = await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", fid)
    before_change = await pool.fetchrow("SELECT * FROM rm_wb_changes WHERE id=$1", cid)
    assert await recovery.recover() == 0
    assert await pool.fetchrow("SELECT * FROM rm_wb_feedback WHERE id=$1", fid) == before_feedback
    assert await pool.fetchrow("SELECT * FROM rm_wb_changes WHERE id=$1", cid) == before_change
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_wb_history WHERE action=$1", recovery.REPAIR_ACTION
        )
        == 0
    )


async def test_repair_is_bounded_and_concurrent_sweeps_cannot_repair_twice(client, pool):
    fixture = await setup(client, pool)
    user, tid, _, _, _ = fixture
    for index in range(31):
        source = await pool.fetchval(
            "INSERT INTO rm_trace_steps(trace_id,idx,role,content) VALUES($1,$2,'user','No, that is incorrect.') RETURNING id",
            tid,
            index + 3,
        )
        await feedback(pool, fixture, source_id=source)
    assert await recovery.recover() == 30
    assert await pool.fetchval("SELECT count(*) FROM rm_wb_feedback WHERE status='completed'") == 1
    results = await asyncio.gather(recovery.recover(), recovery.recover())
    assert sum(results) == 1
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_wb_history WHERE record_type='feedback' AND action=$1",
            recovery.REPAIR_ACTION,
        )
        == 31
    )


async def test_review_committed_after_candidate_selection_wins_over_repair(
    client, pool, monkeypatch
):
    fixture = await setup(client, pool)
    user, _, _, _, _ = fixture
    old = await feedback(pool, fixture)
    await change(pool, fixture, old["id"])
    original_lock = service.mutation_lock
    waiting = asyncio.Event()

    async def observe_lock(conn, owner):
        waiting.set()
        await original_lock(conn, owner)

    monkeypatch.setattr(service, "mutation_lock", observe_lock)
    async with pool.acquire() as conn, conn.transaction():
        await original_lock(conn, user["uuid"])
        repair = asyncio.create_task(recovery.recover())
        await asyncio.wait_for(waiting.wait(), timeout=5)
        await conn.execute(
            "UPDATE rm_wb_feedback SET review_status='accepted',reviewed_by=$2,reviewed_at=now() WHERE id=$1",
            old["id"],
            user["uuid"],
        )
    assert await asyncio.wait_for(repair, timeout=5) == 0
    assert (
        await pool.fetchval("SELECT review_status FROM rm_wb_feedback WHERE id=$1", old["id"])
        == "accepted"
    )
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM rm_wb_history WHERE action=$1", recovery.REPAIR_ACTION
        )
        == 0
    )
