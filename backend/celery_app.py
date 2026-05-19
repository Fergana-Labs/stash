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
        "backend.tasks.embeddings",
        "backend.tasks.viz",
        "backend.tasks.summarize",
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
        "summarize-enqueue-pending": {
            "task": "backend.tasks.summarize.enqueue_pending",
            "schedule": 10.0,
        },
    },
)
