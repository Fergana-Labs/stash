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

import numpy as np

from .auto import close_embedder, get_embedder, set_embedder
from .base import BaseEmbedder

__all__ = [
    "BaseEmbedder",
    "get_embedder",
    "set_embedder",
    "embed_text",
    "embed_batch",
    "is_configured",
    "close",
]


# ---------------------------------------------------------------------------
# Backward-compatible module-level functions.
# Existing callers (memory_service, notebook_service, table_service, routers)
# can keep using `embedding_service.embed_text(...)` unchanged.
# ---------------------------------------------------------------------------


async def embed_text(text: str) -> np.ndarray | None:
    """Embed a single text string."""
    return await get_embedder().embed_text(text)


async def embed_batch(texts: list[str]) -> list[np.ndarray] | None:
    """Embed multiple texts in one call."""
    return await get_embedder().embed_batch(texts)


def is_configured() -> bool:
    """Check if the active embedding provider is ready."""
    return get_embedder().is_configured()


async def close() -> None:
    """Shut down the active embedding provider."""
    await close_embedder()
