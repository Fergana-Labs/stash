"""Pluggable embedding service.

Supports multiple providers out of the box:
  - **openai** — OpenAI, Gemini, Cohere, or any /v1/embeddings-compatible API
  - **huggingface** — Hugging Face Inference API (any HF Hub model)
  - **local** — sentence-transformers (on-device, free, no API key)

Set EMBEDDING_PROVIDER in your environment, or leave it as "auto" to
auto-detect from available API keys.

Bring your own::

    from backend.services.embeddings import BaseEmbedder, set_embedder

    class MyEmbedder(BaseEmbedder):
        name = "my-custom"
        dims = 768
        async def embed_batch(self, texts):
            return [my_model.encode(t) for t in texts]

    set_embedder(MyEmbedder())
"""

import asyncio
import logging
import os
import random

import numpy as np

from .auto import close_embedder, get_embedder, set_embedder
from .base import BaseEmbedder, TransientEmbeddingError

logger = logging.getLogger(__name__)

__all__ = [
    "BaseEmbedder",
    "get_embedder",
    "set_embedder",
    "embed_text",
    "embed_batch",
    "is_configured",
    "close",
]


# Public helpers wrap provider calls with a shared semaphore + retry on
# transient (429 / 5xx / network) failures. Persistent failures become
# `None` so callers can fall back to marking embed_stale.

_MAX_ATTEMPTS = int(os.getenv("EMBEDDING_MAX_ATTEMPTS", "3"))
_BASE_DELAY = float(os.getenv("EMBEDDING_RETRY_BASE_DELAY", "0.5"))
_MAX_DELAY = float(os.getenv("EMBEDDING_RETRY_MAX_DELAY", "10.0"))

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    # Lazy init: bind the semaphore to whatever loop runs the first embed
    # call, not the loop (if any) at import time.
    global _semaphore
    if _semaphore is None:
        limit = int(os.getenv("EMBEDDING_CONCURRENCY", "8"))
        _semaphore = asyncio.Semaphore(limit)
    return _semaphore


async def _with_retry(coro_factory):
    """Run an async call with bounded concurrency + retry on transient errors.

    `coro_factory` is a zero-arg callable returning a fresh coroutine each
    attempt (since a coroutine can only be awaited once).
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
                delay = (
                    exc.retry_after if exc.retry_after is not None else _BASE_DELAY * (2**attempt)
                )
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
    raise (
        last_exc
        if last_exc is not None
        else RuntimeError("_with_retry exhausted with no exception captured")
    )


async def embed_text(text: str) -> np.ndarray | None:
    """Embed a single text string."""
    embedder = get_embedder()
    try:
        return await _with_retry(lambda: embedder.embed_text(text))
    except TransientEmbeddingError:
        logger.warning("Embedding provider failed after retries", exc_info=True)
        return None


# OpenAI caps embedding requests at 300k tokens. We estimate ~1 token per
# 4 chars and use 240k tokens (~960k chars) as the per-shard budget to leave
# headroom for tokenizer variance.
_SHARD_CHAR_BUDGET = 960_000


def _shard_by_chars(texts: list[str], budget: int) -> list[list[int]]:
    """Group text indices into shards where total chars per shard <= budget."""
    shards: list[list[int]] = []
    current: list[int] = []
    current_size = 0
    for i, t in enumerate(texts):
        n = len(t)
        if current and current_size + n > budget:
            shards.append(current)
            current, current_size = [], 0
        current.append(i)
        current_size += n
    if current:
        shards.append(current)
    return shards


async def embed_batch(texts: list[str]) -> list[np.ndarray] | None:
    """Embed multiple texts in one call. Shards large batches under the
    provider's per-request token limit so giant agent-transcript uploads
    don't blow up the embedding API."""
    if not texts:
        return []
    embedder = get_embedder()
    shards = _shard_by_chars(texts, _SHARD_CHAR_BUDGET)
    out: list[np.ndarray | None] = [None] * len(texts)
    try:
        for shard in shards:
            batch = [texts[i] for i in shard]
            vecs = await _with_retry(lambda b=batch: embedder.embed_batch(b))
            if vecs is None:
                return None
            for idx, vec in zip(shard, vecs):
                out[idx] = vec
    except TransientEmbeddingError:
        logger.warning("Embedding provider failed after retries", exc_info=True)
        return None
    return out  # type: ignore[return-value]


def is_configured() -> bool:
    """Check if the active embedding provider is ready."""
    return get_embedder().is_configured()


async def close() -> None:
    """Shut down the active embedding provider."""
    await close_embedder()
