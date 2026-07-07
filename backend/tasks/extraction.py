"""File text extraction task.

Replaces `workers/dispatcher.py` and `services/extraction_queue.py`.

Trigger: the upload endpoint in `routers/files.py` calls
`extract_file_text.delay(file_id)` immediately after inserting the file
row. A periodic Beat task also re-dispatches any rows left in `pending`
or stuck `processing` state (covers Redis blips and existing pending
files at deploy time).

Memory isolation: we keep the existing subprocess pattern. The Celery
worker process spawns `python -m backend.workers.extract_one <file_id>`
under RLIMIT_AS so a runaway extraction OOMs the child, not the worker.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from uuid import UUID

from ..celery_app import celery
from ..database import get_pool
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

# Scanned-PDF OCR calls the Anthropic API with a 120s per-request timeout
# and SDK retries, so the child needs far more headroom than local parsing.
CHILD_TIMEOUT_SECONDS = 600
MAX_ATTEMPTS = 3


async def _run_child(file_id: UUID) -> int:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "backend.workers.extract_one",
        str(file_id),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=CHILD_TIMEOUT_SECONDS)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1
    return proc.returncode or 0


async def _claim_for_processing(file_id: UUID) -> bool:
    """Move a file row to processing if it's still pending/failed.

    The Celery task may run multiple times for the same file (Beat
    enqueue + .delay() from the upload endpoint); this guard prevents
    double work.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        UPDATE files
        SET extraction_status = 'processing',
            locked_at = now(),
            extraction_attempts = extraction_attempts + 1
        WHERE id = $1
          AND (
                extraction_status = 'pending'
             OR (extraction_status = 'failed' AND extraction_attempts < {MAX_ATTEMPTS})
          )
        RETURNING id
        """,
        file_id,
    )
    return row is not None


async def _mark_failed_externally(file_id: UUID, error: str) -> None:
    """Record a failure only if the child died without reporting one.

    When the child persists its own redacted error it also moves the row
    out of 'processing', so the guard keeps us from overwriting it with
    a bare exit-code marker.
    """
    pool = get_pool()
    await pool.execute(
        f"""
        UPDATE files SET
            extraction_status = CASE
                WHEN extraction_attempts >= {MAX_ATTEMPTS} THEN 'failed'
                ELSE 'pending'
            END,
            extraction_error = $2,
            locked_at = NULL
        WHERE id = $1
          AND extraction_status = 'processing'
        """,
        file_id,
        error[:2000],
    )


async def _extract(file_id: UUID) -> str:
    if not await _claim_for_processing(file_id):
        return "skipped"

    code = await _run_child(file_id)
    if code == 0:
        return "ok"

    reason = "oom_or_kill" if code in (-9, 137, -1) else f"exit_{code}"
    logger.warning("extraction child failed file=%s reason=%s", file_id, reason)
    await _mark_failed_externally(file_id, reason)
    return "failed"


@celery.task(name="backend.tasks.extraction.extract_file_text")
def extract_file_text(file_id: str) -> str:
    return run_async(_extract(UUID(file_id)))


async def _enqueue_pending() -> int:
    """Find rows that didn't get dispatched (or are stale) and enqueue them.

    Covers: existing pending rows at deploy, Redis blips that drop a
    `.delay()` call, and `processing` rows whose worker died.
    """
    pool = get_pool()
    rows = await pool.fetch(
        f"""
        SELECT id FROM files
        WHERE (
                extraction_status = 'pending'
             OR (extraction_status = 'failed' AND extraction_attempts < {MAX_ATTEMPTS})
             OR (extraction_status = 'processing' AND locked_at < now() - INTERVAL '10 minutes')
        )
        LIMIT 100
        """,
    )
    for r in rows:
        extract_file_text.delay(str(r["id"]))
    return len(rows)


@celery.task(name="backend.tasks.extraction.enqueue_pending")
def enqueue_pending() -> int:
    return run_async(_enqueue_pending())
