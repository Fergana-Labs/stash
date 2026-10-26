"""Run scheduled agents on their cron.

The beat task fires every minute and is a pure dispatcher: it finds agents
whose cron tick is due, consumes the tick, applies the cheap gates (credits,
credential, pending changes), and hands each eligible run to
`run_scheduled_agent` on the heavy queue — a headless agent turn runs for
minutes and must not hold a default-queue slot. The agent's own turn lock
(Redis) prevents overlap with an in-flight run.
"""

from __future__ import annotations

import logging
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from uuid import UUID

from croniter import croniter

from ..celery_app import celery
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

# Each pass keeps the existing event and time limits. Queue the next pass
# separately so a busy developer account does not wait another day for its
# next 500 inputs, or monopolize one worker indefinitely. In addition to this
# per-chain bound, executions share seven automatic continuations per 24h.
CURATOR_CATCHUP_PASSES = 8


def _is_due(cron: str, last_run: datetime | None, now: datetime) -> bool:
    """True if a cron tick falls in (last_run, now]. Never fires on the very
    first sight of an agent — the baseline is 'now', so it starts next tick."""
    base = last_run or now
    try:
        nxt = croniter(cron, base).get_next(datetime)
    except (ValueError, KeyError):
        logger.warning("agent schedule: bad cron %r", cron)
        return False
    return nxt <= now


@celery.task(name="backend.tasks.agent_schedules.run_due")
def run_due() -> int:
    return run_async(_run_due())


@celery.task(name="backend.tasks.agent_schedules.run_scheduled_agent")
def run_scheduled_agent(agent_id: str, stamp: str) -> None:
    run_async(_run_scheduled_agent(UUID(agent_id), stamp))


@celery.task(name="backend.tasks.agent_schedules.run_curator_now")
def run_curator_now(
    agent_id: str,
    full_history: bool = False,
    metered: bool = True,
    catchup_remaining: int = CURATOR_CATCHUP_PASSES - 1,
    catchup: bool = False,
) -> None:
    run_async(_run_curator_now(UUID(agent_id), full_history, metered, catchup_remaining, catchup))


async def _run_curator_now(
    agent_id: UUID,
    full_history: bool = False,
    metered: bool = True,
    catchup_remaining: int = CURATOR_CATCHUP_PASSES - 1,
    catchup: bool = False,
) -> None:
    """A user-requested curator run: same execution as the daily tick, minus
    the due-check — the user is the trigger. The router already enforced the
    free-tier allowance and resolved credentials.

    `full_history` is the backfill: the run reads with no watermark, but the
    stored watermark is only advanced after success — a failed backfill must
    not have thrown away the incremental position.

    `metered=False` is for runs the platform initiates on its own (the
    first-day curator): they must not eat the user's free monthly allowance."""
    from ..services import (
        agent_service,
        scoped_curation_service,
        sprite_agent_service,
    )

    agent = await agent_service.get_agent_by_id(agent_id)
    workspace = await scoped_curation_service.workspace_for_agent(agent)
    try:
        async with _run_lock(agent, workspace):
            agent = await agent_service.get_agent_by_id(agent_id)
            await _run_curator_locked(
                agent, workspace, full_history, metered, catchup_remaining, catchup
            )
    except sprite_agent_service.TurnInProgress:
        # Only the scoped lock above means "busy". A personal curator's own
        # turn lock fails inside the run, which already recorded the failure.
        if workspace is None:
            raise
        # No mark_run and no charge happened: leave the active run untouched.
        logger.info("agent schedule: curator %s is busy; skipping", agent_id)


# The scheduler's lock also covers the gates before the run and the bookkeeping
# after it, so it must outlive the run's own timeout.
_RUN_LOCK_MARGIN_SECONDS = 600


def _run_lock(agent: dict, workspace):
    from ..config import settings
    from ..services import sprite_agent_service

    return (
        sprite_agent_service._TurnLock(
            f"scoped-curator-{agent['id']}",
            ttl=settings.AGENT_TURN_TIMEOUT_SECONDS + _RUN_LOCK_MARGIN_SECONDS,
        )
        if workspace is not None
        else nullcontext()
    )


async def _run_turn(agent, stamp, workspace):
    from ..services import sprite_agent_service

    if workspace is None:
        return await sprite_agent_service.run_scheduled(agent, stamp)
    return await sprite_agent_service.run_scheduled(
        agent, stamp, workspace=workspace, scoped_lock_held=True
    )


async def _pending_input(agent: dict, workspace) -> bool:
    from ..services import curation_service, scoped_curation_inputs

    if workspace is not None:
        return await scoped_curation_inputs.has_pending(agent, workspace)
    owner = UUID(str(agent["user_id"]))
    return await curation_service.has_changes_since(owner, owner, agent["curated_through"])


async def _run_curator_locked(agent, workspace, full_history, metered, catchup_remaining, catchup):
    from ..services import (
        agent_service,
        billing_service,
        curation_service,
        scoped_curation_service,
        sprite_agent_service,
    )

    agent_id = UUID(str(agent["id"]))
    if not metered and agent["run_mode"] != "scheduled":
        return
    if catchup:
        if workspace is None:
            return
        await scoped_curation_service.require_run_auth(agent, workspace=workspace)
        owner = UUID(str(agent["user_id"]))
        if not await billing_service.is_pro(owner) or not await _pending_input(agent, workspace):
            return
        if not await agent_service.claim_catchup(agent_id, CURATOR_CATCHUP_PASSES - 1):
            return
    if full_history:
        agent = {**agent, "curated_through": None, "curation_cursor": {}}
    now = datetime.now(UTC)
    await agent_service.mark_run(agent_id, metered=metered)
    try:
        # Seconds-resolution stamp so a manual run never shares a session with
        # the beat's minute-stamped run.
        await _run_turn(agent, now.strftime("%Y%m%d%H%M%S"), workspace)
        if workspace is None:
            through = await curation_service.complete_through(
                UUID(str(agent["user_id"])), agent["curated_through"], now
            )
            await agent_service.mark_curated(agent_id, through)
        await agent_service.mark_run_succeeded(agent_id)
    except Exception as e:
        if workspace is not None and isinstance(e, sprite_agent_service.TurnInProgress):
            await _skip_busy_curator(agent_id, metered=metered)
            return
        await agent_service.mark_run_failed(agent_id, str(e), metered=metered)
        raise
    await _dispatch_curator_catchup(agent, now, catchup_remaining, workspace=workspace)


async def _skip_busy_curator(agent_id: UUID, *, metered: bool) -> None:
    """The active run owns the shared outcome; refund only this skipped charge."""
    from ..services import agent_service

    if metered:
        await agent_service.refund_run(agent_id)
    logger.info(
        "agent schedule: curator %s is already running; skipping overlapping pass", agent_id
    )


_WORKSPACE_UNSET = object()


async def _dispatch_curator_catchup(
    agent: dict, run_started: datetime, remaining: int, *, workspace=_WORKSPACE_UNSET
) -> None:
    """A dispatch failure must not undo a successfully completed batch."""
    from ..services import alert_service

    try:
        await _queue_curator_catchup(agent, run_started, remaining, workspace=workspace)
    except Exception:
        logger.exception("agent schedule: catch-up dispatch failed for agent %s", agent["id"])
        await alert_service.send_alert(
            f"Curator catch-up dispatch failed for agent {agent['id']}; "
            "the completed batch and its checkpoint are preserved."
        )


async def _queue_curator_catchup(
    agent: dict, run_started: datetime, remaining: int, *, workspace=_WORKSPACE_UNSET
) -> None:
    from ..services import agent_service, billing_service, scoped_curation_service

    if workspace is _WORKSPACE_UNSET:
        workspace = await scoped_curation_service.workspace_for_agent(agent)
    if remaining <= 0 or workspace is None:
        return
    current = await agent_service.get_agent_by_id(UUID(str(agent["id"])))
    through = current["curated_through"]
    before = agent["curated_through"]
    if (
        current["run_mode"] != "scheduled"
        or current["last_run_outcome"] != "ran"
        or through is None
        # An empty cursor means the batch drained everything up to its start.
        # Input that arrived during the run waits for the next scheduled run
        # rather than starting a platform-funded chain on every busy account.
        or not current.get("curation_cursor")
        or (
            before is not None
            and through <= before
            and current.get("curation_cursor") == agent.get("curation_cursor")
        )
        or not await billing_service.is_pro(UUID(str(current["user_id"])))
    ):
        return
    if not await _pending_input(current, workspace):
        return
    # Only successful, advancing, bounded batches can continue. No retry
    # chain on failure or permission revocation, and no paid personal runs.
    run_curator_now.apply_async(
        args=[str(agent["id"])],
        kwargs={"metered": False, "catchup_remaining": remaining - 1, "catchup": True},
        countdown=15,
    )


# During a scope's first day its wiki updates after every conversation, not
# just on the nightly tick — a user who just signed up (or a developer who
# just activated the platform) watches the wiki grow while they get set up.
# Debounced so a stream of event batches coalesces into at most one run per
# window; the agent's Redis turn lock already prevents overlapping runs.
FIRST_DAY_HOURS = 24
FIRST_DAY_DEBOUNCE = timedelta(minutes=10)


@celery.task(name="backend.tasks.agent_schedules.first_day_curator_tick")
def first_day_curator_tick(scope_user_id: str) -> None:
    run_async(_first_day_curator_tick(UUID(scope_user_id)))


def _within_first_day(created_at: datetime, now: datetime) -> bool:
    return created_at >= now - timedelta(hours=FIRST_DAY_HOURS)


async def _first_day_curator_tick(scope_user_id: UUID) -> None:
    from ..services import agent_service, end_user_service, user_service

    now = datetime.now(UTC)

    # Personal (and workspace-internal) Memory wiki, anchored to signup time.
    scope_user = await user_service.get_user_by_id(scope_user_id)
    if scope_user is not None and _within_first_day(scope_user["created_at"], now):
        agent = await agent_service.get_or_create_curator(scope_user_id)
        await _maybe_dispatch_first_day_run(scope_user_id, agent, now)

    # External cross-user wiki, anchored to developer-platform activation.
    workspace = await end_user_service.workspace_for_scope(scope_user_id)
    if (
        workspace is not None
        and workspace["external_wiki_folder_id"] is not None
        and _within_first_day(workspace["created_at"], now)
    ):
        agent = await agent_service.get_or_create_curator(scope_user_id, wiki="external")
        await _maybe_dispatch_first_day_run(scope_user_id, agent, now)


async def _maybe_dispatch_first_day_run(scope_user_id: UUID, agent: dict, now: datetime) -> None:
    from ..services import agent_auth, scoped_curation_service

    if agent["run_mode"] != "scheduled":
        return
    # A curator that has never run skips the debounce: its seeded last_run_at
    # is the backfill point (~account creation), which would otherwise mute
    # the very first conversations after signup.
    if (
        agent["last_run_outcome"] is not None
        and agent["last_run_at"]
        and agent["last_run_at"] > now - FIRST_DAY_DEBOUNCE
    ):
        return
    workspace = await scoped_curation_service.workspace_for_agent(agent)
    try:
        await scoped_curation_service.require_run_auth(agent, workspace=workspace)
    except (agent_auth.NeedsAuth, agent_auth.ProviderNotConfigured):
        return
    if not await _pending_input(agent, workspace):
        return
    # Unmetered: the platform is the trigger, so the run must not eat the
    # scope's free monthly curator allowance.
    run_curator_now.delay(str(agent["id"]), metered=False)


async def _run_due() -> int:
    from ..services import (
        agent_service,
        scoped_curation_service,
        sprite_agent_service,
    )

    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%d%H%M")
    dispatched = 0
    for agent in await agent_service.list_scheduled():
        if not _is_due(agent["schedule_cron"], agent["last_run_at"], now):
            continue
        workspace = await scoped_curation_service.workspace_for_agent(agent)
        try:
            async with _run_lock(agent, workspace):
                agent = await agent_service.get_agent_by_id(UUID(str(agent["id"])))
                eligible = _is_due(
                    agent["schedule_cron"], agent["last_run_at"], now
                ) and await _consume_due_tick(agent, workspace)
        except sprite_agent_service.TurnInProgress:
            continue
        # Queue only after releasing the lock: the worker takes the same lock
        # and would otherwise skip a run whose tick was already consumed.
        if eligible:
            run_scheduled_agent.delay(str(agent["id"]), stamp)
            dispatched += 1
    return dispatched


async def _consume_due_tick(agent, workspace) -> bool:
    """Consume the tick and apply the cheap gates; True when the run should be queued."""
    from ..config import settings
    from ..services import agent_auth, agent_service, billing_service, scoped_curation_service

    user_id = UUID(str(agent["user_id"]))
    # Consume the tick up front so a skipped, slow, or failing run can't be
    # re-fired by the next beat. The curator's delta watermark is separate
    # (curated_through) and only advances after a successful run, so a
    # skipped or failed run never discards un-curated changes.
    month_runs = await agent_service.mark_run(agent["id"])
    # Sleep-time compute is metered: free accounts get a monthly curator
    # allowance; Pro and enterprise are unlimited.
    if (
        agent["is_curator"]
        and month_runs > settings.FREE_CURATOR_RUNS_PER_MONTH
        and not await billing_service.is_pro(user_id)
    ):
        logger.info("agent schedule: curator credits exhausted for user %s — skipping", user_id)
        await agent_service.mark_run_skipped(agent["id"], "credits")
        return False
    # No runnable credential (unconnected free user) → nothing can run.
    try:
        await scoped_curation_service.require_run_auth(agent, workspace=workspace)
    except (agent_auth.NeedsAuth, agent_auth.ProviderNotConfigured):
        logger.info("agent schedule: no credential for agent %s — skipping", agent["id"])
        await agent_service.mark_run_skipped(agent["id"], "no_credential")
        return False
    # Cost gate: skip the curator (and the sprite wake) when nothing changed
    # since its watermark. Idle users cost one EXISTS per day.
    if agent["is_curator"] and not await _pending_input(agent, workspace):
        await agent_service.mark_run_skipped(agent["id"], "no_changes")
        return False
    return True


async def _run_scheduled_agent(agent_id: UUID, stamp: str) -> None:
    from ..services import (
        agent_service,
        scoped_curation_service,
        sprite_agent_service,
    )

    try:
        agent = await agent_service.get_agent_by_id(agent_id)
    except ValueError:
        # Deleted between the beat tick and this run — nothing to do, and no
        # agent row left to record a failure on.
        logger.info("agent schedule: agent %s deleted before its run", agent_id)
        return
    workspace = await scoped_curation_service.workspace_for_agent(agent)
    try:
        async with _run_lock(agent, workspace):
            agent = await agent_service.get_agent_by_id(agent_id)
            await _run_scheduled_locked(agent, stamp, workspace)
    except sprite_agent_service.TurnInProgress:
        await _skip_busy_curator(agent_id, metered=True)


async def _run_scheduled_locked(agent, stamp, workspace):
    from ..database import get_pool
    from ..services import agent_service, alert_service, curation_service, sprite_agent_service

    agent_id = UUID(str(agent["id"]))
    if agent["run_mode"] != "scheduled":
        return
    user_id = UUID(str(agent["user_id"]))
    now = datetime.now(UTC)
    try:
        await _run_turn(agent, stamp, workspace)
        if agent["is_curator"] and workspace is None:
            # `now` predates the run, so changes made during it stay ahead of
            # the watermark and are picked up next time. If the delta
            # overflowed the event cap, the watermark stops at the last event
            # that fit — the overflow drains on subsequent runs. Bookkeeping
            # failures share the run's try so they also record last_run_error
            # and alert, instead of dying as a bare task error.
            through = await curation_service.complete_through(
                user_id, agent["curated_through"], now
            )
            await agent_service.mark_curated(agent_id, through)
        await agent_service.mark_run_succeeded(agent_id)
    except Exception as e:
        if workspace is not None and isinstance(e, sprite_agent_service.TurnInProgress):
            await _skip_busy_curator(agent_id, metered=True)
            return
        logger.exception("agent schedule: run failed for agent %s", agent_id)
        await agent_service.mark_run_failed(agent_id, str(e))
        email = await get_pool().fetchval("SELECT email FROM users WHERE id = $1", user_id)
        await alert_service.send_alert(
            f"Scheduled agent run failed: {agent['name']!r} for {email}: {str(e)[:300]}"
        )
    else:
        await _dispatch_curator_catchup(agent, now, CURATOR_CATCHUP_PASSES - 1, workspace=workspace)


# Pending input older than this is stale even when individual batches succeed.
# One bad night must not page.
STALE_CURATOR_HOURS = 48


@celery.task(name="backend.tasks.agent_schedules.alert_stale_curators")
def alert_stale_curators() -> int:
    return run_async(_alert_stale_curators())


async def _alert_stale_curators() -> int:
    """Alert on curators whose watermark stopped advancing despite pending
    changes. Alerting on the stale *outcome* catches every cause — dead
    provider keys, harness bugs, a wedged beat — where per-run failure alerts
    only catch runs that started. Successful runs with an undrained backlog
    also qualify. Designed skips resolve explicitly and stay quiet.
    """
    from ..database import get_pool
    from ..services import alert_service

    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=STALE_CURATOR_HOURS)
    rows = await get_pool().fetch(
        """
        SELECT a.*, u.email
        FROM agents a JOIN users u ON u.id = a.user_id
        WHERE a.is_curator AND a.run_mode = 'scheduled'
          AND a.curated_through IS NOT NULL AND a.curated_through < $1
          AND a.last_run_outcome IN ('started', 'failed', 'ran')
        """,
        cutoff,
    )
    from ..services import scoped_curation_service

    stale = []
    for row in rows:
        # A slow cron gets one full interval plus a day's grace, measured
        # against the watermark. A daily curator with an old undrained backlog
        # still alerts after 48 hours, even though every nightly run succeeds.
        if row["last_run_outcome"] == "ran":
            try:
                firings = croniter(row["schedule_cron"], now)
                first = firings.get_next(datetime)
                interval = firings.get_next(datetime) - first
                grace = max(timedelta(hours=STALE_CURATOR_HOURS), interval + timedelta(hours=24))
                if row["curated_through"] >= now - grace:
                    continue
            except (ValueError, KeyError, TypeError):
                pass
        workspace = await scoped_curation_service.workspace_for_agent(dict(row))
        if await _pending_input(dict(row), workspace):
            stale.append(row)
    if not stale:
        return 0
    lines = []
    for row in stale:
        outcome = {
            "ran": "backlog remains after a successful batch",
            "failed": "last run failed without an error message",
            "started": "run started but never resolved",
        }[row["last_run_outcome"]]
        detail = row["last_run_error"] or outcome
        lines.append(
            f"- {row['email']}: last curated {row['curated_through']:%Y-%m-%d %H:%M} UTC "
            f"({detail[:200]})"
        )
    await alert_service.send_alert(
        f"{len(stale)} Memory curator(s) stale >{STALE_CURATOR_HOURS}h with pending changes:\n"
        + "\n".join(lines)
    )
    return len(stale)
