"""One-shot child process: extract one Drive folder document and exit.

Invoked by the dispatcher as:

    python -m backend.workers.extract_drive_one <drive_documents.id>

Isolated in its own OS process so pypdf on a 180 MB parts catalog OOMs this
child rather than the Celery worker. RLIMIT_AS is applied before any heavy
library loads, exactly as `extract_one` does for uploads.

The dispatcher discards stdout/stderr (parser libraries print document content),
so the child never logs: its only output channels are the exit code and the row
it updates.

Exit codes:
    0  success (the row carries the text, or a loud reason it has none)
    1  failure (the row records a redacted error)
    137 SIGKILL — typically the OOM killer. The parent records it.
"""

from __future__ import annotations

import asyncio
import os
import resource
import sys
from uuid import UUID

_MEM_LIMIT_BYTES = int(os.getenv("EXTRACTION_MEMORY_LIMIT_MB", "1024")) * 1024 * 1024

# A catalog that extracts to more than this is stored truncated rather than
# refused — the marker tells the reader the tail is missing.
MAX_EXTRACTED_TEXT = 4 * 1024 * 1024


def _apply_memory_limit() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_MEM_LIMIT_BYTES, _MEM_LIMIT_BYTES))
    except (ValueError, OSError):
        # macOS rejects RLIMIT_AS; dev boxes run without the bound.
        pass


async def _store_unreadable(conn, row_id: UUID, status: str, reason: str) -> None:
    """A document with no text is a fact about the document, not a crash. Record
    why, so a read of it can say so instead of returning an empty string."""
    await conn.execute(
        "UPDATE drive_documents SET extraction_status = $2, extraction_error = $3, "
        "locked_at = NULL WHERE id = $1",
        row_id,
        status,
        reason[:2000],
    )


async def _run(row_id: UUID) -> int:
    # Lazy imports so the RLIMIT above applies to everything heavy.
    import asyncpg

    from ..config import settings
    from ..database import close_db, init_pool
    from ..integrations.google.indexer import (
        MAX_EXTRACTION_DOWNLOAD_BYTES,
        DriveFileTooLarge,
        DriveFileUnsupported,
        extract_drive_text,
    )

    # get_valid_token refreshes the OAuth token through the shared pool.
    await init_pool()
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT d.id, d.external_ref, d.owner_user_id "
            "FROM drive_documents d WHERE d.id = $1 AND d.deleted_at IS NULL",
            row_id,
        )
        if not row or not row["external_ref"]:
            return 1

        try:
            text = await extract_drive_text(
                row["owner_user_id"],
                row["external_ref"],
                max_bytes=MAX_EXTRACTION_DOWNLOAD_BYTES,
                ocr_scanned_pdfs=True,
            )
        except DriveFileUnsupported as e:
            await _store_unreadable(conn, row_id, "unsupported", str(e))
            return 0
        except DriveFileTooLarge as e:
            await _store_unreadable(conn, row_id, "too_large", str(e))
            return 0

        if len(text) > MAX_EXTRACTED_TEXT:
            text = text[:MAX_EXTRACTED_TEXT] + "\n\n[truncated]"

        await conn.execute(
            "UPDATE drive_documents SET "
            "content = $2, content_hash = md5($2), extraction_status = 'done', "
            "extraction_error = NULL, locked_at = NULL, embed_stale = TRUE, updated_at = now() "
            "WHERE id = $1",
            row_id,
            text,
        )
        return 0
    except Exception as e:
        # The persisted error carries only the exception class — never the
        # message, which may embed document text or provider responses.
        try:
            await conn.execute(
                "UPDATE drive_documents SET "
                "extraction_status = CASE WHEN extraction_attempts >= 3 THEN 'failed' "
                "ELSE 'pending' END, "
                "extraction_error = $2, locked_at = NULL WHERE id = $1",
                row_id,
                f"Extraction failed: {type(e).__name__}",
            )
        except Exception:
            pass
        return 1
    finally:
        await conn.close()
        await close_db()


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m backend.workers.extract_drive_one <row_id>", file=sys.stderr)
        sys.exit(2)
    try:
        row_id = UUID(sys.argv[1])
    except ValueError:
        print("invalid uuid", file=sys.stderr)
        sys.exit(2)
    _apply_memory_limit()
    sys.exit(asyncio.run(_run(row_id)))


if __name__ == "__main__":
    main()
