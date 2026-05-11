"""Backfill: parse legacy R2 transcript blobs into history_events rows.

Run once after PR 1 ships. Idempotent — sessions that already have
events are skipped, so re-runs are safe.

Sources scanned:
  - `session_transcripts` rows that still reference a storage_key
  - `stashes` rows with a non-null `transcript_storage_key`

For each: download blob → parse via transcript_import → insert events
for (workspace_id, session_id) if missing.

Usage:
    DATABASE_URL=postgres://... \
    S3_ENDPOINT=... S3_BUCKET=... S3_ACCESS_KEY=... S3_SECRET_KEY=... \
    python scripts/backfill_transcripts_to_events.py [--dry-run] [--limit N]

This script is meant to run from the project root with the backend
package importable. It uses the same asyncpg pool the API uses.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure the backend package is importable when run from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import asyncpg  # noqa: E402

from backend import database  # noqa: E402
from backend.services import memory_service, storage_service, transcript_import  # noqa: E402


def _get_pool():
    return database.pool


async def _init_pool_directly() -> None:
    """Skip the alembic-running init_db() — scripts should not migrate.
    Just open a pool with the same codecs the rest of the backend expects."""
    if database.pool is not None:
        return
    database.pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=1,
        max_size=4,
        init=database._init_connection,
    )


async def _close_pool() -> None:
    if database.pool is not None:
        await database.pool.close()
        database.pool = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("backfill")


async def _session_already_imported(workspace_id, session_id: str) -> bool:
    pool = _get_pool()
    return bool(await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM history_events "
        "WHERE workspace_id = $1 AND session_id = $2)",
        workspace_id, session_id,
    ))


async def _backfill_one(
    *,
    workspace_id,
    session_id: str,
    storage_key: str,
    agent_name: str,
    created_by,
    cwd: str | None,
    dry_run: bool,
) -> tuple[str, int]:
    """Returns (status, imported_count). status ∈ {skipped, imported, failed}."""
    if await _session_already_imported(workspace_id, session_id):
        return "skipped", 0
    try:
        blob = await storage_service.download_file(storage_key)
    except Exception as e:
        log.warning("download failed for %s: %s", storage_key, e)
        return "failed", 0
    events = transcript_import.parse_jsonl_to_events(
        blob, session_id=session_id, agent_name=agent_name,
    )
    if cwd:
        for e in events:
            e["metadata"] = {**(e.get("metadata") or {}), "cwd": cwd}
    if dry_run:
        return "imported", len(events)
    inserted = await memory_service.push_events_batch(
        workspace_id, created_by, events,
    )
    return "imported", len(inserted)


async def backfill_session_transcripts(dry_run: bool, limit: int | None) -> dict:
    pool = _get_pool()
    query = (
        "SELECT workspace_id, session_id, storage_key, agent_name, cwd, uploaded_by "
        "FROM session_transcripts ORDER BY uploaded_at"
    )
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = await pool.fetch(query)
    log.info("session_transcripts: %d candidate rows", len(rows))
    counts = {"skipped": 0, "imported": 0, "failed": 0, "events": 0}
    for r in rows:
        status, n = await _backfill_one(
            workspace_id=r["workspace_id"],
            session_id=r["session_id"],
            storage_key=r["storage_key"],
            agent_name=r["agent_name"] or "",
            created_by=r["uploaded_by"],
            cwd=r["cwd"],
            dry_run=dry_run,
        )
        counts[status] += 1
        counts["events"] += n
        if status == "imported":
            log.info("  imported %d events for session %s", n, r["session_id"])
    return counts


async def backfill_stash_transcripts(dry_run: bool, limit: int | None) -> dict:
    pool = _get_pool()
    query = (
        "SELECT workspace_id, session_id, transcript_storage_key, agent_name, "
        "cwd, created_by FROM stashes "
        "WHERE transcript_storage_key IS NOT NULL ORDER BY created_at"
    )
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = await pool.fetch(query)
    log.info("stashes: %d candidate rows", len(rows))
    counts = {"skipped": 0, "imported": 0, "failed": 0, "events": 0}
    for r in rows:
        status, n = await _backfill_one(
            workspace_id=r["workspace_id"],
            session_id=r["session_id"],
            storage_key=r["transcript_storage_key"],
            agent_name=r["agent_name"] or "",
            created_by=r["created_by"],
            cwd=r["cwd"],
            dry_run=dry_run,
        )
        counts[status] += 1
        counts["events"] += n
        if status == "imported":
            log.info("  imported %d events for session %s", n, r["session_id"])
    return counts


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and count but don't insert.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most N rows from each source table.",
    )
    parser.add_argument(
        "--source", choices=("both", "session_transcripts", "stashes"), default="both",
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        log.error("DATABASE_URL is required")
        return 2

    await _init_pool_directly()
    try:
        if args.source in ("both", "session_transcripts"):
            log.info("=== Backfilling session_transcripts ===")
            counts = await backfill_session_transcripts(args.dry_run, args.limit)
            log.info("session_transcripts: %s", counts)

        if args.source in ("both", "stashes"):
            log.info("=== Backfilling stashes ===")
            counts = await backfill_stash_transcripts(args.dry_run, args.limit)
            log.info("stashes: %s", counts)
    finally:
        await _close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
