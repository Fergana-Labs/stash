"""Retry + bounded-concurrency wrapper for embedding provider calls.

Providers raise `TransientEmbeddingError` for 429 / 5xx / network blips.
Everything else (auth failures, bad input, etc.) is not retried — the
provider returns None and we surface None.
"""

import asyncio
import logging
import os
import random

logger = logging.getLogger(__name__)


class TransientEmbeddingError(Exception):
    """Provider call failed in a way that's worth retrying."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


_MAX_ATTEMPTS = int(os.getenv("EMBEDDING_MAX_ATTEMPTS", "3"))
_BASE_DELAY = float(os.getenv("EMBEDDING_RETRY_BASE_DELAY", "0.5"))
_MAX_DELAY = float(os.getenv("EMBEDDING_RETRY_MAX_DELAY", "10.0"))

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    # Lazy init: we want the semaphore bound to whatever loop is running
    # the first embed call, not whatever loop exists at import time.
    global _semaphore
    if _semaphore is None:
        limit = int(os.getenv("EMBEDDING_CONCURRENCY", "8"))
        _semaphore = asyncio.Semaphore(limit)
    return _semaphore


async def with_retry(coro_factory):
    """Run the async call with bounded concurrency + retry on transient errors.

    `coro_factory` is a zero-arg callable that returns a fresh coroutine
    each attempt (since a coroutine can only be awaited once).
    """
    sem = _get_semaphore()
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        async with sem:
            try:
                return await coro_factory()
            except TransientEmbeddingError as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    break
                delay = exc.retry_after if exc.retry_after is not None else _BASE_DELAY * (2**attempt)
                delay = min(delay, _MAX_DELAY)
                delay += random.uniform(0, delay * 0.25)
                logger.info(
                    "Embedding provider transient failure (attempt %d/%d): %s — retrying in %.2fs",
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    exc,
                    delay,
                )
        await asyncio.sleep(delay)
    raise last_exc if last_exc is not None else RuntimeError("with_retry exhausted with no exception captured")
