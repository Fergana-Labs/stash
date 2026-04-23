"""In-process extraction dispatcher.

Runs as an asyncio task inside the FastAPI lifespan. One dispatcher per
uvicorn worker. Concurrency is naturally bounded — each dispatcher runs at
most one child extraction at a time — and multiple dispatchers coordinate
via the queue's `FOR UPDATE SKIP LOCKED` claim.

Flow per iteration:
    1. claim_one()  → file row or None
    2. spawn `python -m backend.workers.extract_one <file_id>` as a child
    3. wait with a hard timeout
    4. on non-zero exit / timeout, mark_failed on the parent side so the
       row doesn't stay `processing` forever

The child updates the row directly on success; the parent only writes on
failure paths to guarantee a terminal state even if the child was killed.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from ..services import extraction_queue

logger = logging.getLogger(__name__)

# Longer than any reasonable per-file extraction; if we hit this the child
# is almost certainly stuck and we want to move on.
CHILD_TIMEOUT_SECONDS = 180
IDLE_SLEEP_SECONDS = 2.0
ERROR_SLEEP_SECONDS = 10.0


async def _run_child(file_id) -> tuple[int, str]:
    """Spawn the extract_one child and wait for it. Returns (exit_code, log_tail)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "backend.workers.extract_one",
        str(file_id),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout_b, _ = await asyncio.wait_for(
            proc.communicate(), timeout=CHILD_TIMEOUT_SECONDS
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "timeout"

    tail = (stdout_b or b"").decode("utf-8", errors="replace")[-2000:]
    return proc.returncode or 0, tail


async def _tick() -> bool:
    """Process one job if available. Returns True if a job was handled."""
    job = await extraction_queue.claim_one()
    if not job:
        return False

    logger.info("dispatcher: claimed file %s", job["id"])
    code, tail = await _run_child(job["id"])

    if code == 0:
        logger.info("dispatcher: extraction done for %s", job["id"])
        return True

    # Non-zero exit. The child tries to mark failure itself; but if it
    # was SIGKILLed (e.g. OOM) it couldn't. Rewrite terminal state here
    # to guarantee the row doesn't stay 'processing'.
    reason = "oom_or_kill" if code == -9 or code == 137 or code == -1 else f"exit_{code}"
    error = f"{reason}: {tail[-500:]}".strip()
    logger.warning("dispatcher: child exit=%s file=%s  %s", code, job["id"], error[:200])
    await extraction_queue.mark_failed(job["id"], error)
    return True


async def run() -> None:
    """Run until cancelled. Safe to start from FastAPI lifespan."""
    logger.info("extraction dispatcher started")
    while True:
        try:
            handled = await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("dispatcher tick failed")
            await asyncio.sleep(ERROR_SLEEP_SECONDS)
            continue
        await asyncio.sleep(0 if handled else IDLE_SLEEP_SECONDS)
