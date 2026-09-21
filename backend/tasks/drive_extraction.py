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
import os
import subprocess
import sys
import tempfile
from uuid import UUID, uuid4

from ..celery_app import celery
from ..database import get_pool
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

# PDFs go to Claude vision ten pages at a time, with a 120s per-request
# timeout — a 100-page catalog is ten of those.
CHILD_TIMEOUT_SECONDS = 1800
MAX_ATTEMPTS = 3

# A 'processing' lock older than this belongs to a worker that died: a live
# extraction is killed at CHILD_TIMEOUT_SECONDS (30 min), so no healthy child
# holds a lock longer. The sweep and the claim must agree on this cutoff, or
# the sweep enqueues rows the claim then refuses.
STALE_LOCK = "35 minutes"

_CHILD_MODULE = "backend.workers.extract_drive_one"

# Enough stderr to hold the child's crash report (a redacted traceback), small
# enough that parser-library noise ahead of it can't bloat a log line.
STDERR_TAIL_BYTES = 2000


async def _run_child(row_id: UUID, task_id: str) -> tuple[int, str]:
    """Run the child; return its exit code and the tail of its stderr.

    stderr goes to a temp file, not a pipe: parser libraries can spew
    megabytes of warnings, and a pipe would buffer all of it inside this
    worker — the exact exposure the child process exists to avoid. Only the
    tail comes back, which is where the child's own crash report lands.
    stdout stays discarded (parser libraries print document content there).
    """
    with tempfile.TemporaryFile() as errf:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            _CHILD_MODULE,
            str(row_id),
            task_id,
            stdout=subprocess.DEVNULL,
            stderr=errf,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=CHILD_TIMEOUT_SECONDS)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, ""
        errf.seek(0, os.SEEK_END)
        size = errf.tell()
        errf.seek(max(0, size - STDERR_TAIL_BYTES))
        tail = errf.read().decode(errors="replace").strip()
    return proc.returncode or 0, tail


async def enqueue_extraction(row_id: UUID) -> str | None:
    task_id = str(uuid4())
    row = await get_pool().fetchval(
        f"""
        UPDATE drive_documents SET extraction_task_id = $2,
            extraction_claimed_at = now(), extraction_status = 'pending', locked_at = NULL
        WHERE id = $1 AND deleted_at IS NULL AND extraction_retry_at <= now()
          AND (extraction_task_id IS NULL
               OR extraction_claimed_at < now() - interval '{STALE_LOCK}')
          AND (extraction_status = 'pending'
               OR (extraction_status = 'failed' AND extraction_attempts < {MAX_ATTEMPTS})
               OR (extraction_status = 'processing' AND extraction_attempts < {MAX_ATTEMPTS}
                   AND locked_at < now() - interval '{STALE_LOCK}'))
        RETURNING id
        """,
        row_id,
        task_id,
    )
    if row is None:
        return None
    try:
        await asyncio.to_thread(
            extract_drive_document.apply_async,
            args=[str(row_id)],
            task_id=task_id,
        )
    except Exception:
        await _release(row_id, task_id)
        raise
    return task_id


async def _release(row_id: UUID, task_id: str) -> None:
    await get_pool().execute(
        "UPDATE drive_documents SET extraction_task_id = NULL, extraction_claimed_at = NULL "
        "WHERE id = $1 AND extraction_task_id = $2",
        row_id,
        task_id,
    )


async def _claim(row_id: UUID, task_id: str) -> bool:
    row = await get_pool().fetchval(
        "UPDATE drive_documents SET extraction_status = 'processing', locked_at = now(), "
        "extraction_claimed_at = now(), extraction_attempts = extraction_attempts + 1 "
        "WHERE id = $1 AND extraction_task_id = $2 AND deleted_at IS NULL "
        "AND extraction_status = 'pending' AND extraction_retry_at <= now() RETURNING id",
        row_id,
        task_id,
    )
    return row is not None


async def _mark_failed_externally(row_id: UUID, task_id: str, error: str) -> None:
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
            locked_at = NULL, extraction_retry_at = now() + interval '5 minutes'
        WHERE id = $1 AND extraction_task_id = $3 AND extraction_status = 'processing'
        """,
        row_id,
        error[:2000],
        task_id,
    )


async def _extract(row_id: UUID, task_id: str) -> str:
    code, err_tail = await _run_child(row_id, task_id)
    if code == 0:
        return "ok"

    reason = "extraction ran out of memory" if code in (-9, 137) else f"extraction exited {code}"
    if code == -1:
        reason = "extraction timed out"
    logger.warning(
        "drive extraction child failed row=%s reason=%s stderr=%s",
        row_id,
        reason,
        err_tail or "<empty>",
    )
    await _mark_failed_externally(row_id, task_id, reason)
    return "failed"


async def _run_claimed(row_id: UUID, task_id: str) -> str:
    if not await _claim(row_id, task_id):
        return "skipped"
    try:
        return await _extract(row_id, task_id)
    finally:
        await _release(row_id, task_id)


@celery.task(bind=True, name="backend.tasks.drive_extraction.extract_drive_document")
def extract_drive_document(self, row_id: str) -> str:
    return run_async(_run_claimed(UUID(row_id), self.request.id))


async def _enqueue_pending() -> int:
    """Rows the sync walk marked but whose task never ran — a dropped `.delay()`,
    a worker that died mid-extraction."""
    await get_pool().execute(
        f"""
        UPDATE drive_documents SET extraction_status = 'failed',
            extraction_error = 'Extraction worker stopped; retry limit reached',
            extraction_task_id = NULL, extraction_claimed_at = NULL, locked_at = NULL
        WHERE extraction_status = 'processing' AND extraction_attempts >= {MAX_ATTEMPTS}
          AND locked_at < now() - interval '{STALE_LOCK}'
        """
    )
    rows = await get_pool().fetch(
        f"""
        SELECT id FROM drive_documents
        WHERE deleted_at IS NULL AND extraction_retry_at <= now()
          AND (extraction_task_id IS NULL
               OR extraction_claimed_at < now() - interval '{STALE_LOCK}')
          AND (
                extraction_status = 'pending'
             OR (extraction_status = 'failed' AND extraction_attempts < {MAX_ATTEMPTS})
             OR (extraction_status = 'processing' AND extraction_attempts < {MAX_ATTEMPTS}
                 AND locked_at < now() - INTERVAL '{STALE_LOCK}')
          )
        ORDER BY extraction_retry_at, id LIMIT 100
        """,
    )
    dispatched = 0
    for r in rows:
        if await enqueue_extraction(r["id"]) is not None:
            dispatched += 1
    return dispatched


@celery.task(name="backend.tasks.drive_extraction.enqueue_pending")
def enqueue_pending() -> int:
    return run_async(_enqueue_pending())
