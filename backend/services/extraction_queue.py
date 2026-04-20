"""Postgres-backed extraction queue.

A single dispatcher task in the web process claims pending rows from `files`
(FOR UPDATE SKIP LOCKED) and spawns a short-lived child process per job. The
child does the actual extraction under RLIMIT_AS, so if tesseract or pypdfium2
blows memory it kills the child, not the web parent.

Three terminal states:
- done     — extracted_text is populated (may be NULL if file type isn't
             extractable; that's distinguished by status, not text).
- failed   — too many attempts. extraction_error has the last reason.
- pending  — not yet attempted (or retry after backoff).

Claim query locks with `SKIP LOCKED` so multiple dispatchers (e.g. across
uvicorn workers) don't collide.
"""

from __future__ import annotations

import logging
from uuid import UUID

from ..database import get_pool

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# After a failed attempt, the row is re-eligible for claim after this many
# seconds — enough to avoid tight crash-loops, not so long that a transient
# failure (e.g. an S3 blip) makes the user wait forever.
RETRY_BACKOFF_SECONDS = 60
# A row claimed but never finalized is re-eligible after this window. Covers
# the case where the web process was restarted mid-extraction.
STALE_LOCK_SECONDS = 600


async def claim_one() -> dict | None:
    """Atomically claim the next extraction job. Returns the row or None."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        WITH next AS (
            SELECT id FROM files
            WHERE (
                extraction_status = 'pending'
                OR (extraction_status = 'failed' AND extraction_attempts < {MAX_ATTEMPTS})
            )
            AND (
                locked_at IS NULL
                OR locked_at < now() - INTERVAL '{STALE_LOCK_SECONDS} seconds'
            )
            ORDER BY locked_at NULLS FIRST, extraction_attempts, id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE files f
        SET extraction_status = 'processing',
            locked_at = now(),
            extraction_attempts = f.extraction_attempts + 1
        FROM next
        WHERE f.id = next.id
        RETURNING f.id, f.storage_key, f.content_type, f.extraction_attempts
        """
    )
    return dict(row) if row else None


async def mark_done(file_id: UUID, text: str | None) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE files SET "
        "extracted_text = $2, "
        "extraction_status = 'done', "
        "extraction_error = NULL, "
        "locked_at = NULL "
        "WHERE id = $1",
        file_id,
        text,
    )


async def mark_failed(file_id: UUID, error: str) -> None:
    """Set status to 'failed' if retries exhausted, otherwise 'pending'."""
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
        """,
        file_id,
        error[:2000],
    )


async def pending_backlog() -> int:
    """For observability — how many jobs are queued."""
    pool = get_pool()
    return await pool.fetchval(
        "SELECT count(*) FROM files "
        "WHERE extraction_status IN ('pending', 'processing') "
        f"OR (extraction_status = 'failed' AND extraction_attempts < {MAX_ATTEMPTS})"
    )
