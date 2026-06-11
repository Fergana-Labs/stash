"""Scheduled revocation of expired CLI auth sessions.

The cli-auth endpoints run this cleanup lazily on each request, but an
approved-but-never-claimed device key would otherwise stay live (with its
plaintext at rest in cli_auth_sessions) until the next cli-auth request on
the whole instance — on a quiet deployment, possibly never. Beat bounds
that window.
"""

from __future__ import annotations

import logging

from ..celery_app import celery
from ..services import user_service
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)


@celery.task(name="backend.tasks.cli_auth.cleanup_expired_sessions")
def cleanup_expired_sessions() -> int:
    revoked = run_async(user_service.cleanup_expired_cli_auth_sessions())
    if revoked:
        logger.info("revoked %d expired unclaimed CLI auth keys", revoked)
    return revoked
