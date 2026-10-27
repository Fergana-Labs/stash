"""Operator-only bounded cleanup; run on the deployed worker, not a customer client.

Plan first, then apply exactly that manifest. Output contains identifiers/status,
never original or generated text. No automatic retry or persistent budget change.
"""

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

from backend import database
from backend.services import shared_wiki_cleanup as cleanup


def code_fingerprint():
    root = Path(__file__).resolve().parents[2]
    paths = [
        "backend/scripts/review_shared_wiki.py",
        "backend/services/shared_wiki_cleanup.py",
        "backend/services/shared_wiki_privacy.py",
        "backend/services/scoped_curation_service.py",
        "backend/services/vfs_service.py",
        "backend/routers/vfs.py",
        "backend/services/files_tree_service.py",
        "backend/tasks/embeddings.py",
        "backend/migrations/versions/0254_shared_wiki_reviews.py",
    ]
    hashes = [(path, hashlib.sha256((root / path).read_bytes()).hexdigest()) for path in paths]
    return hashlib.sha256(json.dumps(hashes).encode()).hexdigest()


async def run(args):
    code_sha256 = code_fingerprint()
    if args.apply and args.expected_code_sha256 != code_sha256:
        raise ValueError("Runtime code differs from the reviewed release")
    await database.init_pool()
    pool = database.get_pool()
    try:
        async with pool.acquire() as lock_conn:
            locked = await lock_conn.fetchval(
                "SELECT pg_try_advisory_lock(hashtextextended($1,0))",
                "shared-wiki-cleanup:" + str(args.workspace),
            )
            if not locked:
                raise RuntimeError("A cleanup is already running for this workspace")
            try:
                workspace, pages = await cleanup.snapshot(
                    lock_conn, args.workspace, args.owner, args.root
                )
                digest = cleanup.manifest_hash(pages)
                print(
                    json.dumps(
                        {
                            "event": "PLAN",
                            "pages": len(pages),
                            "manifest_sha256": digest,
                            "code_sha256": code_sha256,
                        }
                    ),
                    flush=True,
                )
                if not args.apply:
                    return
                if args.manifest_sha256 != digest or not 1 <= len(pages) <= args.max_pages:
                    raise ValueError("Manifest changed or page limit exceeded; make a fresh plan")
                counts = Counter()
                indexes = [p for p in pages if p["name"].strip().casefold() in {"index", "readme"}]
                index_ids = {p["id"] for p in indexes}
                queue = asyncio.Queue()
                for page in pages:
                    if page["id"] not in index_ids:
                        queue.put_nowait(page)

                async def process(source, *, refresh_index=False):
                    result = await cleanup.clean_page(
                        pool, workspace, source, refresh_index=refresh_index
                    )
                    counts[result["status"]] += 1
                    print(json.dumps({"event": "PAGE_REVIEWED", **result}), flush=True)

                async def worker():
                    while not queue.empty():
                        await process(queue.get_nowait())

                async with asyncio.TaskGroup() as group:
                    for _ in range(args.concurrency):
                        group.create_task(worker())
                # Refresh index links only after every ordinary page is reviewed.
                for source in indexes:
                    await process(source, refresh_index=True)
                print(json.dumps({"event": "CLEANUP_FINISHED", "counts": counts}), flush=True)
            finally:
                await lock_conn.execute(
                    "SELECT pg_advisory_unlock(hashtextextended($1,0))",
                    "shared-wiki-cleanup:" + str(args.workspace),
                )
    finally:
        await database.close_db()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument("--owner", type=UUID, required=True)
    parser.add_argument("--root", type=UUID, required=True)
    parser.add_argument("--max-pages", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--expected-code-sha256")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_pages <= 1000:
        parser.error("max-pages must be between 1 and 1000")
    if not 1 <= args.concurrency <= 4:
        parser.error("concurrency must be between 1 and 4")
    try:
        asyncio.run(run(args))
    except Exception as exc:
        # SDK/SQL validation exceptions can contain original private text.
        # Operators inspect archived data privately; job logs contain only type.
        print(json.dumps({"event": "CLEANUP_FAILED", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
