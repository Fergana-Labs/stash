"""Janitor for the landing-page demo scope.

Anonymous visitors can create pages and sessions via the demo router
without ever publishing a Stash (they might bail after step 4). Those
orphans would otherwise accumulate forever in the singleton Demo
scope. This task deletes anything older than the retention window
that isn't referenced by a Stash.

Pages/sessions/folders that *are* referenced by a Stash are kept
indefinitely so the public links keep working — published artifacts
are not garbage.

The canonical `Stash knowledge base/` folder (seeded by
demo_service.seed_demo) is also kept indefinitely because
new Skills need to attach it.
"""

from __future__ import annotations

import logging

from ..celery_app import celery
from ..database import get_pool
from ..services.demo_content import DEMO_KB_FOLDER_NAME
from ..services.demo_service import DEMO_SYSTEM_USERNAME
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

# Anything older than this with no Stash reference gets deleted.
ORPHAN_AGE_HOURS = 24


async def _demo_owner_user_id() -> str | None:
    pool = get_pool()
    return await pool.fetchval(
        "SELECT id FROM users WHERE name = $1 LIMIT 1",
        DEMO_SYSTEM_USERNAME,
    )


async def _purge_demo_orphans() -> dict:
    pool = get_pool()
    owner_user_id = await _demo_owner_user_id()
    if owner_user_id is None:
        return {"pages": 0, "sessions": 0, "skipped": "no demo scope"}

    # A page is orphaned when it sits outside every published skill folder
    # subtree (published demo skills are folder-shaped) and outside the KB.
    page_result = await pool.execute(
        "WITH RECURSIVE skill_tree AS ("
        "  SELECT folder_id AS id FROM skills WHERE owner_user_id = $1"
        "  UNION"
        "  SELECT f.id FROM folders f JOIN skill_tree st ON f.parent_folder_id = st.id"
        ") "
        "DELETE FROM pages p "
        "WHERE p.owner_user_id = $1 "
        f"  AND p.created_at < now() - interval '{ORPHAN_AGE_HOURS} hours' "
        "  AND (p.folder_id IS NULL OR p.folder_id NOT IN (SELECT id FROM skill_tree)) "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM folders f "
        "    WHERE f.id = p.folder_id AND f.name = $2"
        "  )",
        owner_user_id,
        DEMO_KB_FOLDER_NAME,
    )
    # Sessions can't live in skills anymore — published demos materialize the
    # transcript as a page, so old sessions purge unconditionally by age.
    session_result = await pool.execute(
        "DELETE FROM sessions s "
        "WHERE s.owner_user_id = $1 "
        f"  AND s.started_at < now() - interval '{ORPHAN_AGE_HOURS} hours'",
        owner_user_id,
    )

    def _count(result: str) -> int:
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    pages_deleted = _count(page_result)
    sessions_deleted = _count(session_result)
    if pages_deleted or sessions_deleted:
        logger.info(
            "demo janitor: purged %d pages, %d sessions",
            pages_deleted,
            sessions_deleted,
        )
    return {"pages": pages_deleted, "sessions": sessions_deleted}


@celery.task(name="backend.tasks.demo_janitor.purge_orphans")
def purge_orphans() -> dict:
    """Celery entry-point; runs on the beat schedule."""
    return run_async(_purge_demo_orphans())
