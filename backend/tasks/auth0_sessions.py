"""Expired Auth0 session cleanup (managed-only).

Server-side sessions live in auth0_sessions (managed migration m0002; written
by frontend/managed/auth0/sessionStore.ts). Expired rows are already unusable —
the store's get() filters on expires_at — this task just keeps the table from
growing forever. Beat-scheduled only when AUTH0_ENABLED (the table does not
exist in OSS deployments).
"""

from __future__ import annotations

import logging

from ..celery_app import celery
from ..database import get_pool
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)


async def _delete_expired() -> int:
    pool = get_pool()
    result = await pool.execute("DELETE FROM auth0_sessions WHERE expires_at < now()")
    # asyncpg returns a status string like "DELETE 3".
    return int(result.split()[-1])


@celery.task(name="backend.tasks.auth0_sessions.delete_expired")
def delete_expired() -> int:
    deleted = run_async(_delete_expired())
    if deleted:
        logger.info("Deleted %d expired Auth0 sessions", deleted)
    return deleted
