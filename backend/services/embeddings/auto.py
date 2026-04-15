"""Auto-detection and global singleton for the active embedding provider."""

import logging
import os

from .base import BaseEmbedder

logger = logging.getLogger(__name__)

_embedder: BaseEmbedder | None = None


def get_embedder() -> BaseEmbedder:
    """Return the active embedder, creating one if needed.

    Detection order (when EMBEDDING_PROVIDER=auto or unset):
      1. OPENAI_API_KEY or EMBEDDING_API_KEY set → OpenAI-compatible
      2. HF_TOKEN set → Hugging Face Inference API
      3. Otherwise → local sentence-transformers
    """
    global _embedder
    if _embedder is not None:
        return _embedder

    provider = os.getenv("EMBEDDING_PROVIDER", "auto").lower()

    if provider == "openai":
        from .openai_compat import OpenAICompatEmbedder
        _embedder = OpenAICompatEmbedder()

    elif provider == "huggingface":
        from .huggingface import HuggingFaceEmbedder
        _embedder = HuggingFaceEmbedder()

    elif provider == "local":
        from .local import LocalEmbedder
        _embedder = LocalEmbedder()

    elif provider == "auto":
        if os.getenv("OPENAI_API_KEY") or os.getenv("EMBEDDING_API_KEY"):
            from .openai_compat import OpenAICompatEmbedder
            _embedder = OpenAICompatEmbedder()
        elif os.getenv("HF_TOKEN"):
            from .huggingface import HuggingFaceEmbedder
            _embedder = HuggingFaceEmbedder()
        else:
            from .local import LocalEmbedder
            _embedder = LocalEmbedder()

    else:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER={provider!r}. "
            "Choose: openai, huggingface, local, or auto."
        )

    logger.info("Embedding provider: %s", _embedder.name)
    return _embedder


def set_embedder(embedder: BaseEmbedder) -> None:
    """Replace the active embedder. Call at startup before any embedding happens."""
    global _embedder
    _embedder = embedder
    logger.info("Embedding provider set to: %s", embedder.name)


async def close_embedder() -> None:
    """Shut down the active embedder."""
    global _embedder
    if _embedder is not None:
        await _embedder.close()
        _embedder = None
