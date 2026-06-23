"""Linear ticket enrichment tasks."""

from __future__ import annotations

from uuid import UUID

from ..celery_app import celery
from ..services import github_pr_service, linear_api_service, linear_ticket_service
from ._celery_helpers import run_async

RECONCILE_BATCH_SIZE = 50
GITHUB_PR_RECONCILE_BATCH_SIZE = 50


@celery.task(name="backend.tasks.linear_tickets.enrich_session")
def enrich_session_linear_tickets(_owner_user_id: str, session_row_id: str) -> int:
    if not linear_api_service.is_configured():
        return 0
    return run_async(linear_ticket_service.enrich_session_labels(UUID(session_row_id)))


@celery.task(name="backend.tasks.linear_tickets.enrich_ticket")
def enrich_ticket(ticket_identifier: str) -> int:
    if not linear_api_service.is_configured():
        return 0
    return run_async(linear_ticket_service.enrich_ticket(ticket_identifier))


@celery.task(name="backend.tasks.linear_tickets.discover_session_github_prs")
def discover_session_github_prs(session_row_id: str) -> int:
    return run_async(github_pr_service.discover_session_labels(UUID(session_row_id)))


@celery.task(name="backend.tasks.linear_tickets.reconcile")
def reconcile() -> int:
    if not linear_api_service.is_configured():
        return 0
    return run_async(linear_ticket_service.enrich_stale_sessions(RECONCILE_BATCH_SIZE))


@celery.task(name="backend.tasks.linear_tickets.reconcile_github_prs")
def reconcile_github_prs() -> int:
    return run_async(
        github_pr_service.discover_unprocessed_sessions(GITHUB_PR_RECONCILE_BATCH_SIZE)
    )
