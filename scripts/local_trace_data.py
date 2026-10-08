"""Copy authorized trace snapshots with saved grades, or run local API scoring.

Both commands require a loopback destination DATABASE_URL. Snapshot reads use a
read-only source connection; only the local database is written. Scoring calls
the configured remote classifier, never a local model or training worker.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import database  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.services.rm import workbench_auto  # noqa: E402


def require_local_database(url: str) -> None:
    if urlsplit(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("The destination DATABASE_URL must point to a loopback host")


async def json_codecs(conn):
    for kind in ("json", "jsonb"):
        await conn.set_type_codec(kind, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def copy_snapshot(local, source, source_owner: UUID, trace_id: UUID, local_owner: UUID):
    """Preserve source IDs and immutable grading requests; never remap evidence."""
    async with source.transaction(isolation="repeatable_read", readonly=True):
        trace = await source.fetchrow(
            "SELECT * FROM rm_traces WHERE id=$1 AND owner_user_id=$2", trace_id, source_owner
        )
        if not trace:
            raise ValueError("Source trace not found for the specified owner")
        steps = await source.fetch(
            "SELECT * FROM rm_trace_steps WHERE trace_id=$1 ORDER BY idx", trace_id
        )
        evaluations = await source.fetch(
            "SELECT * FROM rm_wb_evaluations WHERE trace_id=$1 ORDER BY created_at DESC LIMIT 3",
            trace_id,
        )
        calls = await source.fetch(
            "SELECT * FROM rm_wb_evaluation_calls WHERE evaluation_id=ANY($1::uuid[])",
            [row["id"] for row in evaluations],
        )
    async with local.transaction():
        # A fresh import has different IDs. Do not attach grades to unrelated IDs
        # or overwrite existing local edits; score that local copy instead.
        exists = await local.fetchval(
            "SELECT 1 FROM rm_traces WHERE id=$1 OR (owner_user_id=$2 AND external_id=$3 AND source_format=$4)",
            trace_id,
            local_owner,
            trace["external_id"],
            trace["source_format"],
        )
        if exists:
            raise ValueError("Trace already exists locally; use the score command for that copy")
        for table, records in (
            ("rm_traces", [trace]),
            ("rm_trace_steps", steps),
            ("rm_wb_evaluations", evaluations),
            ("rm_wb_evaluation_calls", calls),
        ):
            for record in records:
                row = dict(record)
                if "owner_user_id" in row:
                    row["owner_user_id"] = local_owner
                columns = ",".join('"' + key + '"' for key in row)
                placeholders = ",".join(f"${i}" for i in range(1, len(row) + 1))
                await local.execute(
                    f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", *row.values()
                )
    return {"steps": len(steps), "evaluations": len(evaluations), "calls": len(calls)}


async def run(args):
    require_local_database(settings.DATABASE_URL)
    # A small pool also bounds the memory footprint of the local API worker.
    pool = await asyncpg.create_pool(
        settings.DATABASE_URL, min_size=1, max_size=2, init=json_codecs
    )
    database.pool = pool
    try:
        owner = await pool.fetchval("SELECT id FROM users WHERE name=$1", args.user)
        if not owner:
            raise ValueError("Local user not found")
        if args.command == "copy":
            source_url = os.environ.get("STASH_SOURCE_DATABASE_URL")
            if not source_url:
                raise ValueError("Set STASH_SOURCE_DATABASE_URL for the read-only source")
            source = await asyncpg.connect(
                source_url, server_settings={"default_transaction_read_only": "on"}
            )
            try:
                await json_codecs(source)
                async with pool.acquire() as local:
                    result = await copy_snapshot(
                        local, source, args.source_owner, args.trace_id, owner
                    )
                print(json.dumps(result), flush=True)
            finally:
                await source.close()
            return
        if not settings.TYPESAFE_API_KEY:
            raise ValueError("Configure TYPESAFE_API_KEY in the local backend/.env")
        while True:
            pending = await pool.fetch(
                """SELECT q.trace_id FROM rm_wb_queue q JOIN rm_traces t ON t.id=q.trace_id
                WHERE t.owner_user_id=$1 AND q.status='queued' AND q.due_at<=now()
                ORDER BY q.due_at LIMIT 1""",
                owner,
            )
            for row in pending:
                await workbench_auto.process_trace(row["trace_id"])
                status = await pool.fetchval(
                    "SELECT status FROM rm_wb_queue WHERE trace_id=$1", row["trace_id"]
                )
                print(json.dumps({"trace_id": str(row["trace_id"]), "status": status}), flush=True)
            if not args.watch:
                return
            await asyncio.sleep(5)
    finally:
        await pool.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True, help="Local account name")
    commands = parser.add_subparsers(dest="command", required=True)
    copy = commands.add_parser("copy", help="Copy one authorized snapshot with its saved grades")
    copy.add_argument("--trace-id", type=UUID, required=True)
    copy.add_argument("--source-owner", type=UUID, required=True)
    score = commands.add_parser("score", help="Process local queued traces using the remote API")
    score.add_argument("--watch", action="store_true", help="Continue scoring new queued imports")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
