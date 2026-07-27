"""Seed default skills into scopes that predate them.

`seed_default_skills` runs at signup, so a skill added later never reaches
anyone who signed up before it. That is fine for a one-off, and wrong as a
permanent property — we will add skills again.

A sweep is used rather than a migration because the problem recurs: adding a
directory under `backend/skills/` should be the whole change, with existing
users picking it up on the next pass. Seeding is already idempotent per
skill, so this re-running is harmless — a scope that has everything does one
cheap query and stops.

Users who deleted a seeded skill get it back. That is the trade for having
this at all; the alternative is remembering per user which skills they have
declined, which is more state than the feature is worth.
"""

from __future__ import annotations

import logging

from ..celery_app import celery
from ..database import get_pool
from ..services import skill_seeds
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

# Bounded so one sweep can't spend minutes writing folders for a large
# instance; the next tick picks up where this one stopped.
USERS_PER_SWEEP = 50


async def _reconcile() -> int:
    """Seed missing default skills for scopes that are short of at least one.

    The candidate query counts how many of the default skill folders each
    owner already has, so scopes that are complete never reach the seeding
    code at all.
    """
    names = [name for name, _ in skill_seeds.default_skills()]
    if not names:
        return 0

    owners = await get_pool().fetch(
        """
        SELECT u.id
        FROM users u
        WHERE (
            SELECT count(DISTINCT lower(f.name))
            FROM folders f
            JOIN pages p ON p.folder_id = f.id
            WHERE f.owner_user_id = u.id
              AND lower(f.name) = ANY($1)
              AND p.name = 'SKILL.md'
              AND p.deleted_at IS NULL
        ) < $2
        LIMIT $3
        """,
        names,
        len(names),
        USERS_PER_SWEEP,
    )

    seeded = 0
    for owner in owners:
        seeded += await skill_seeds.seed_default_skills(owner["id"], owner["id"])
    if seeded:
        logger.info("backfilled %s default skill pages across %s scopes", seeded, len(owners))
    return seeded


@celery.task(name="backend.tasks.skill_backfill.reconcile")
def reconcile() -> int:
    return run_async(_reconcile())
