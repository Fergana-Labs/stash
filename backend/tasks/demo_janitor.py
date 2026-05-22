"""Janitor for the landing-page demo workspace.

Anonymous visitors can create pages and sessions via the demo router
without ever publishing a Stash (they might bail after step 4). Those
orphans would otherwise accumulate forever in the singleton Demo
workspace. This task deletes anything older than the retention window
that isn't referenced by a Stash.

Pages/sessions/folders that *are* referenced by a Stash are kept
indefinitely so the public links keep working — published artifacts
are not garbage.

The canonical `Stash knowledge base/` folder (seeded by
demo_service.seed_demo_workspace) is also kept indefinitely because
new Stashes need to attach it.
"""

from __future__ import annotations

import logging

from ..celery_app import celery
from ..database import get_pool
from ..services.demo_content import DEMO_KB_FOLDER_NAME
from ..services.demo_service import (
    DEMO_SYSTEM_USERNAME,
    DEMO_WORKSPACE_NAME,
)
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

# Anything older than this with no Stash reference gets deleted.
ORPHAN_AGE_HOURS = 24


async def _demo_workspace_id() -> str | None:
    pool = get_pool()
    return await pool.fetchval(
        "SELECT w.id FROM workspaces w "
        "JOIN users u ON u.id = w.creator_id "
        "WHERE u.name = $1 AND w.name = $2 LIMIT 1",
        DEMO_SYSTEM_USERNAME,
        DEMO_WORKSPACE_NAME,
    )


async def _purge_demo_orphans() -> dict:
    pool = get_pool()
    workspace_id = await _demo_workspace_id()
    if workspace_id is None:
        return {"pages": 0, "sessions": 0, "skipped": "no demo workspace"}

    page_result = await pool.execute(
        "DELETE FROM pages p "
        "WHERE p.workspace_id = $1 "
        f"  AND p.created_at < now() - interval '{ORPHAN_AGE_HOURS} hours' "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM stash_items si "
        "    WHERE si.object_type = 'page' AND si.object_id = p.id"
        "  ) "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM folders f "
        "    WHERE f.id = p.folder_id AND f.name = $2"
        "  )",
        workspace_id,
        DEMO_KB_FOLDER_NAME,
    )
    session_result = await pool.execute(
        "DELETE FROM sessions s "
        "WHERE s.workspace_id = $1 "
        f"  AND s.started_at < now() - interval '{ORPHAN_AGE_HOURS} hours' "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM stash_items si "
        "    WHERE si.object_type = 'session' AND si.object_id = s.id"
        "  )",
        workspace_id,
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
