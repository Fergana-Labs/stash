"""Run scheduled agents on their cron.

The beat task fires every minute; for each scheduled agent it checks whether a
cron tick is due since the agent's last run and, if so, runs it headless. The
agent's own turn lock (Redis) prevents overlap with an in-flight run.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
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
    from ..services import agent_auth, agent_service, curation_service, sprite_agent_service

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
    return ran
