"""Run scheduled agents on their cron.

The beat task fires every minute; for each scheduled agent it checks whether a
cron tick is due since the agent's last run and, if so, runs it headless. The
agent's own turn lock (Redis) prevents overlap with an in-flight run.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from croniter import croniter

from ..celery_app import celery
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)


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


@celery.task(name="backend.tasks.agent_schedules.run_curator_now")
def run_curator_now(agent_id: str) -> None:
    run_async(_run_curator_now(UUID(agent_id)))


async def _run_curator_now(agent_id: UUID) -> None:
    """A user-requested curator run: same execution as the daily tick, minus
    the due-check — the user is the trigger. The router already enforced the
    free-tier allowance and resolved credentials."""
    from ..services import agent_service, curation_service, sprite_agent_service

    agent = await agent_service.get_agent_by_id(agent_id)
    now = datetime.now(UTC)
    await agent_service.mark_run(agent_id)
    try:
        # Seconds-resolution stamp so a manual run never shares a session with
        # the beat's minute-stamped run.
        await sprite_agent_service.run_scheduled(agent, now.strftime("%Y%m%d%H%M%S"))
    except Exception as e:
        await agent_service.mark_run_failed(agent_id, str(e))
        raise
    through = await curation_service.complete_through(
        UUID(str(agent["user_id"])), agent["curated_through"], now
    )
    await agent_service.mark_curated(agent_id, through)


async def _run_due() -> int:
    from ..config import settings
    from ..database import get_pool
    from ..services import (
        agent_auth,
        agent_service,
        alert_service,
        curation_service,
        sprite_agent_service,
    )

    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%d%H%M")
    ran = 0
    for agent in await agent_service.list_scheduled():
        if not _is_due(agent["schedule_cron"], agent["last_run_at"], now):
            continue
        user_id = UUID(str(agent["user_id"]))
        # Consume the tick up front so a skipped, slow, or failing run can't be
        # re-fired by the next beat. The curator's delta watermark is separate
        # (curated_through) and only advances after a successful run, so a
        # skipped or failed run never discards un-curated changes.
        month_runs = await agent_service.mark_run(agent["id"])
        # Sleep-time compute is metered: free accounts get a monthly curator
        # allowance; the enterprise plan is unlimited.
        if agent["is_curator"] and month_runs > settings.FREE_CURATOR_RUNS_PER_MONTH:
            plan = await get_pool().fetchval("SELECT plan FROM users WHERE id = $1", user_id)
            if plan != "enterprise":
                logger.info(
                    "agent schedule: curator credits exhausted for user %s — skipping", user_id
                )
                continue
        # No runnable credential (unconnected free user) → nothing can run.
        try:
            await agent_auth.resolve(user_id, agent["model_provider"])
        except (agent_auth.NeedsAuth, agent_auth.ProviderNotConfigured):
            logger.info("agent schedule: no credential for agent %s — skipping", agent["id"])
            continue
        # Cost gate: skip the curator (and the sprite wake) when nothing changed
        # since its watermark. Idle users cost one EXISTS per day.
        if agent["is_curator"] and not await curation_service.has_changes_since(
            user_id, user_id, agent["curated_through"]
        ):
            continue
        try:
            await sprite_agent_service.run_scheduled(agent, stamp)
            if agent["is_curator"]:
                # `now` predates the run, so changes made during it stay ahead
                # of the watermark and are picked up next time. If the delta
                # overflowed the event cap, the watermark stops at the last
                # event that fit — the overflow drains on subsequent runs.
                through = await curation_service.complete_through(
                    user_id, agent["curated_through"], now
                )
                await agent_service.mark_curated(agent["id"], through)
            ran += 1
        except Exception as e:
            logger.exception("agent schedule: run failed for agent %s", agent["id"])
            await agent_service.mark_run_failed(agent["id"], str(e))
            email = await get_pool().fetchval("SELECT email FROM users WHERE id = $1", user_id)
            await alert_service.send_alert(
                f"Scheduled agent run failed: {agent['name']!r} for {email}: {str(e)[:300]}"
            )
    return ran


# A curator whose watermark is older than this while changes are pending has
# been failing for multiple nightly runs — one bad night must not page.
STALE_CURATOR_HOURS = 48


@celery.task(name="backend.tasks.agent_schedules.alert_stale_curators")
def alert_stale_curators() -> int:
    return run_async(_alert_stale_curators())


async def _alert_stale_curators() -> int:
    """Alert on curators whose watermark stopped advancing despite pending
    changes. Alerting on the stale *outcome* catches every cause — dead
    provider keys, harness bugs, a wedged beat — where per-run failure alerts
    only catch runs that started. `last_run_error IS NOT NULL` scopes this to
    curators whose last attempted run actually failed; curators skipped by
    design (credit allowance, no credential) keep a NULL error and stay quiet.
    """
    from ..database import get_pool
    from ..services import alert_service, curation_service

    cutoff = datetime.now(UTC) - timedelta(hours=STALE_CURATOR_HOURS)
    rows = await get_pool().fetch(
        """
        SELECT a.user_id, a.curated_through, a.last_run_error, u.email
        FROM agents a JOIN users u ON u.id = a.user_id
        WHERE a.is_curator AND a.run_mode = 'scheduled'
          AND a.curated_through IS NOT NULL AND a.curated_through < $1
          AND a.last_run_error IS NOT NULL
        """,
        cutoff,
    )
    stale = [
        r
        for r in rows
        if await curation_service.has_changes_since(
            r["user_id"], r["user_id"], r["curated_through"]
        )
    ]
    if not stale:
        return 0
    lines = [
        f"- {r['email']}: last curated {r['curated_through']:%Y-%m-%d %H:%M} UTC "
        f"({r['last_run_error'][:200]})"
        for r in stale
    ]
    await alert_service.send_alert(
        f"{len(stale)} Memory curator(s) stale >{STALE_CURATOR_HOURS}h with pending changes:\n"
        + "\n".join(lines)
    )
    return len(stale)
