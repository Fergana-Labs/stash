"""One-shot child process: extract text for a single file and exit.

Invoked by the dispatcher as:

    python -m backend.workers.extract_one <file_id>

Isolated in its own OS process so an extraction blowup OOMs this child,
not the web parent. RLIMIT_AS bounds virtual memory before we load any
heavy libraries.

Exit codes:
    0  success (row already updated by the child)
    1  failure (error logged; row updated by the child)
    137 SIGKILL — typically OOM killer. Parent observes the non-zero exit
         and records a failure on its end.

The child does NOT run alembic or init the full DB module. It opens a
single asyncpg connection, does its work, closes, and exits.
"""

from __future__ import annotations

import asyncio
import logging
import os
import resource
import sys
import traceback
from uuid import UUID

# Cap address space BEFORE importing any extraction libs. 350 MB leaves
# headroom on Render Starter's 512 MB dyno while giving pypdf room for
# large arxiv-style documents.
_MEM_LIMIT_BYTES = int(os.getenv("EXTRACTION_MEMORY_LIMIT_MB", "350")) * 1024 * 1024
try:
    resource.setrlimit(resource.RLIMIT_AS, (_MEM_LIMIT_BYTES, _MEM_LIMIT_BYTES))
except (ValueError, OSError):
    # Some platforms (e.g. macOS for dev) reject RLIMIT_AS — ignore.
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s extract_one %(message)s")
logger = logging.getLogger(__name__)


async def _run(file_id: UUID) -> int:
    # Lazy imports so the RLIMIT above applies to everything heavy.
    import asyncpg

    from ..config import settings
    from ..services import storage_service
    from ..services.file_extraction import extract_text

    MAX_EXTRACTED_TEXT = 1 * 1024 * 1024

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT id, storage_key, content_type, extraction_attempts " "FROM files WHERE id = $1",
            file_id,
        )
        if not row:
            logger.error("file %s not found", file_id)
            return 1

        logger.info(
            "extracting %s (%s, attempt %d)",
            row["id"],
            row["content_type"],
            row["extraction_attempts"],
        )

        content = await storage_service.download_file(row["storage_key"])
        text = extract_text(content, row["content_type"])
        if text and len(text) > MAX_EXTRACTED_TEXT:
            text = text[:MAX_EXTRACTED_TEXT] + "\n\n[truncated]"

        await conn.execute(
            "UPDATE files SET "
            "extracted_text = $2, "
            "extraction_status = 'done', "
            "extraction_error = NULL, "
            "locked_at = NULL "
            "WHERE id = $1",
            file_id,
            text,
        )
        logger.info(
            "done %s text_len=%d",
            file_id,
            len(text) if text else 0,
        )
        return 0
    except Exception as e:
        # The dispatcher's parent-side fallback mark_failed will catch us
        # if we can't update the row ourselves (e.g. DB unreachable).
        error = f"{type(e).__name__}: {e}"
        logger.error("extract failed: %s\n%s", error, traceback.format_exc())
        try:
            await conn.execute(
                "UPDATE files SET "
                "extraction_status = CASE WHEN extraction_attempts >= 3 THEN 'failed' ELSE 'pending' END, "
                "extraction_error = $2, "
                "locked_at = NULL "
                "WHERE id = $1",
                file_id,
                error[:2000],
            )
        except Exception:
            pass
        return 1
    finally:
        await conn.close()
        await storage_service.close()


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m backend.workers.extract_one <file_id>", file=sys.stderr)
        sys.exit(2)
    try:
        file_id = UUID(sys.argv[1])
    except ValueError:
        print("invalid uuid", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(_run(file_id)))


if __name__ == "__main__":
    main()
