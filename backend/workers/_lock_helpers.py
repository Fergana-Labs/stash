"""Postgres advisory-lock helpers for workers.

Pattern: each worker has a constant namespace (a 32-bit int) and locks
per-resource by hashing the resource id with hashtextextended. Multiple
uvicorn workers in the same process pool then can't double-process the
same resource on the same tick.

Advisory locks are connection-scoped, so we hold a dedicated connection
for the duration of the lock. Use `advisory_lock` as a context manager:

    async with advisory_lock(LOCK_NAMESPACE, str(uuid)) as conn:
        if conn is None:
            continue  # someone else got it
        await do_work(conn)  # or just call pool methods — lock is global
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from ..database import get_pool


@asynccontextmanager
async def advisory_lock(namespace: int, resource: str):
    """Yield the connection holding the lock, or None if not acquired.

    Releases on exit even if work raises.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        got = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1, hashtextextended($2, 0)::int)",
            namespace,
            resource,
        )
        if not got:
            yield None
            return
        try:
            yield conn
        finally:
            try:
                await conn.execute(
                    "SELECT pg_advisory_unlock($1, hashtextextended($2, 0)::int)",
                    namespace,
                    resource,
                )
            except Exception:
                # Best-effort release. If the connection is broken, the lock
                # will be released by Postgres when the session ends.
                pass
