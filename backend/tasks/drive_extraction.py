"""Extract one Drive folder document's text, in a child process.

Trigger: `index_google_drive_folder` enqueues a task per file whose Drive
`modifiedTime` moved since we last extracted it.

Memory isolation mirrors `tasks/extraction.py`: pypdf on a 180 MB parts catalog
will exhaust whatever process it runs in, so the work happens in
`python -m backend.workers.extract_drive_one <row_id>` under RLIMIT_AS. A blowup
kills the child and the parent records it on the row.
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

# Scanned catalogs go to Claude vision ten pages at a time, with a 120s per-request
# timeout — a 100-page scan is ten of those.
CHILD_TIMEOUT_SECONDS = 1800
MAX_ATTEMPTS = 3


async def _run_child(row_id: UUID) -> int:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "backend.workers.extract_drive_one",
        str(row_id),
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


async def _claim(row_id: UUID) -> bool:
    """Take the row if nobody else has. A file can be enqueued twice — once by the
    sync walk, once by the Beat sweep — and OCR is too expensive to do twice."""
    row = await get_pool().fetchrow(
        f"""
        UPDATE drive_documents
        SET extraction_status = 'processing',
            locked_at = now(),
            extraction_attempts = extraction_attempts + 1
        WHERE id = $1
          AND deleted_at IS NULL
          AND (
                extraction_status = 'pending'
             OR (extraction_status = 'failed' AND extraction_attempts < {MAX_ATTEMPTS})
          )
        RETURNING id
        """,
        row_id,
    )
    return row is not None


async def _mark_failed_externally(row_id: UUID, error: str) -> None:
    """Only when the child died without recording its own reason — a SIGKILL has
    no chance to write anything."""
    await get_pool().execute(
        f"""
        UPDATE drive_documents SET
            extraction_status = CASE
                WHEN extraction_attempts >= {MAX_ATTEMPTS} THEN 'failed'
                ELSE 'pending'
            END,
            extraction_error = $2,
            locked_at = NULL
        WHERE id = $1 AND extraction_status = 'processing'
        """,
        row_id,
        error[:2000],
    )


async def _extract(row_id: UUID) -> str:
    if not await _claim(row_id):
        return "skipped"

    code = await _run_child(row_id)
    if code == 0:
        return "ok"

    reason = "extraction ran out of memory" if code in (-9, 137) else f"extraction exited {code}"
    if code == -1:
        reason = "extraction timed out"
    logger.warning("drive extraction child failed row=%s reason=%s", row_id, reason)
    await _mark_failed_externally(row_id, reason)
    return "failed"


@celery.task(name="backend.tasks.drive_extraction.extract_drive_document")
def extract_drive_document(row_id: str) -> str:
    return run_async(_extract(UUID(row_id)))


async def _enqueue_pending() -> int:
    """Rows the sync walk marked but whose task never ran — a dropped `.delay()`,
    a worker that died mid-extraction."""
    rows = await get_pool().fetch(
        f"""
        SELECT id FROM drive_documents
        WHERE deleted_at IS NULL
          AND (
                extraction_status = 'pending'
             OR (extraction_status = 'failed' AND extraction_attempts < {MAX_ATTEMPTS})
             OR (extraction_status = 'processing' AND locked_at < now() - INTERVAL '30 minutes')
          )
        LIMIT 100
        """,
    )
    for r in rows:
        extract_drive_document.delay(str(r["id"]))
    return len(rows)


@celery.task(name="backend.tasks.drive_extraction.enqueue_pending")
def enqueue_pending() -> int:
    return run_async(_enqueue_pending())
