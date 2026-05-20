"""Linear ticket enrichment tasks."""

from __future__ import annotations

from uuid import UUID

from ..celery_app import celery
from ..services import linear_api_service, linear_ticket_service
from ._celery_helpers import run_async

RECONCILE_BATCH_SIZE = 50


@celery.task(name="backend.tasks.linear_tickets.enrich_session")
def enrich_session_linear_tickets(_workspace_id: str, session_row_id: str) -> int:
    if not linear_api_service.is_configured():
        return 0
    return run_async(linear_ticket_service.enrich_session_labels(UUID(session_row_id)))


@celery.task(name="backend.tasks.linear_tickets.reconcile")
def reconcile() -> int:
    if not linear_api_service.is_configured():
        return 0
    return run_async(linear_ticket_service.enrich_stale_sessions(RECONCILE_BATCH_SIZE))
