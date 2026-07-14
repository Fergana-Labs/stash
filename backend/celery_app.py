"""Celery application.

One process model:
  - `backend` (uvicorn)         — HTTP API, dispatches tasks via `.delay()`.
  - `worker`  (celery worker)   — executes tasks.
  - `beat`    (celery beat)     — fires the periodic tasks in `beat_schedule`.

Each task module is added to `include` when it lands. Adding a module to
`include` makes Celery import it on worker startup, which is what triggers
task registration. Importer/exporter tasks live alongside their providers,
not in a central tasks/ directory.

Beat must run as exactly one instance — multiple beat processes will fire
the same scheduled task multiple times.
"""

from celery import Celery

from .config import settings

celery = Celery(
    "stash",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "backend.tasks.extraction",
        "backend.tasks.drive_extraction",
        "backend.tasks.embeddings",
        "backend.tasks.linear_tickets",
        "backend.tasks.session_titles",
        "backend.tasks.viz",
        "backend.tasks.demo_janitor",
        "backend.tasks.cli_auth",
        "backend.tasks.auth0_sessions",
        "backend.tasks.sources",
        "backend.tasks.agent_schedules",
        "backend.integrations.google.exporters.slides",
        "backend.exports.pdf",
        "backend.exports.pptx",
    ],
)

celery.conf.update(
    task_default_queue="default",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Long-running tasks (Playwright renders, zip downloads) shouldn't be
    # cancelled by a soft timeout mid-render. Hard cap at 30 min.
    task_time_limit=1800,
    task_soft_time_limit=1500,
    # Redis is the result backend — GC old results so memory doesn't grow.
    result_expires=86400,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "embedding-reconcile": {
            "task": "backend.tasks.embeddings.reconcile",
            "schedule": 60.0,
        },
        "viz-precompute": {
            "task": "backend.tasks.viz.precompute",
            "schedule": 300.0,
        },
        "extraction-enqueue-pending": {
            "task": "backend.tasks.extraction.enqueue_pending",
            "schedule": 60.0,
        },
        "drive-extraction-enqueue-pending": {
            "task": "backend.tasks.drive_extraction.enqueue_pending",
            "schedule": 60.0,
        },
        "session-title-reconcile": {
            "task": "backend.tasks.session_titles.reconcile_missing",
            "schedule": 60.0,
        },
        "linear-ticket-reconcile": {
            "task": "backend.tasks.linear_tickets.reconcile",
            "schedule": 300.0,
        },
        "github-pr-linear-ticket-reconcile": {
            "task": "backend.tasks.linear_tickets.reconcile_github_prs",
            "schedule": 300.0,
        },
        "demo-janitor-purge-orphans": {
            "task": "backend.tasks.demo_janitor.purge_orphans",
            "schedule": 3600.0,
        },
        "agent-schedules-run-due": {
            "task": "backend.tasks.agent_schedules.run_due",
            "schedule": 60.0,
        },
        "sources-reconcile-due": {
            "task": "backend.tasks.sources.reconcile_due",
            "schedule": 120.0,
        },
        "sources-reconcile-github-sync-all": {
            "task": "backend.tasks.sources.reconcile_github_sync_all",
            "schedule": 3600.0,
        },
        "cli-auth-cleanup-expired": {
            "task": "backend.tasks.cli_auth.cleanup_expired_sessions",
            "schedule": 300.0,
        },
        # The auth0_sessions table only exists in managed deployments
        # (managed migration m0002), so only schedule its cleanup there.
        **(
            {
                "auth0-sessions-cleanup-expired": {
                    "task": "backend.tasks.auth0_sessions.delete_expired",
                    "schedule": 3600.0,
                }
            }
            if settings.AUTH0_ENABLED
            else {}
        ),
    },
)
