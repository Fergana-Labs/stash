"""Helpers for writing Celery tasks against the async backend.

The backend is asyncpg-based. Celery workers are sync by default. Each
worker process keeps one event loop alive for its lifetime, opens the
asyncpg pool once at process init, and uses `run_async()` to bridge each
task body. asyncio.run() per task would work but would re-create the pool
every time, which is wasteful.

Celery's prefork model means each forked worker process gets its own
loop and its own pool. Pool size in config.py is per-process; tune
DB_POOL_MIN/DB_POOL_MAX if running many concurrent workers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, TypeVar

from celery.signals import worker_process_init, worker_process_shutdown

from ..database import close_db, init_pool

logger = logging.getLogger(__name__)

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None


@worker_process_init.connect
def _on_worker_init(**_: Any) -> None:
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(init_pool())
    logger.info("celery worker process: db pool opened")


@worker_process_shutdown.connect
def _on_worker_shutdown(**_: Any) -> None:
    global _loop
    if _loop is None:
        return
    try:
        _loop.run_until_complete(close_db())
    finally:
        _loop.close()
        _loop = None


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine on the worker's persistent event loop."""
    assert _loop is not None, "Celery worker loop not initialised"
    return _loop.run_until_complete(coro)
