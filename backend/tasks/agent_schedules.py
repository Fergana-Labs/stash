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


async def _run_due() -> int:
    from ..services import agent_service, curation_service, sprite_agent_service

    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%d%H%M")
    ran = 0
    for agent in await agent_service.list_scheduled():
        if not _is_due(agent["schedule_cron"], agent["last_run_at"], now):
            continue
        # Cost gate: skip the curator (and the sprite wake) when nothing changed
        # since its watermark — and DON'T advance the watermark, so a change
        # later today is still caught. Idle users cost one EXISTS per day.
        if agent["is_curator"]:
            user_id = UUID(str(agent["user_id"]))
            if not await curation_service.has_changes_since(
                user_id, user_id, agent["last_run_at"]
            ):
                continue
        # Mark before running so a slow/failing run can't be re-fired by the
        # next beat; a lost tick on failure is acceptable (the next tick runs).
        await agent_service.mark_run(agent["id"])
        try:
            await sprite_agent_service.run_scheduled(agent, stamp)
            ran += 1
        except Exception:
            logger.exception("agent schedule: run failed for agent %s", agent["id"])
    return ran
