"""Base embedding interface. Subclassed by the OpenAI-compatible embedder and test fakes."""

from abc import ABC, abstractmethod

import numpy as np


class TransientEmbeddingError(Exception):
    """Provider call failed in a way that's worth retrying (429 / 5xx / network)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class BaseEmbedder(ABC):
    """Interface for the OpenAI-compatible embedder; tests subclass it for fakes."""

    name: str = "base"
    dims: int = 384

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[np.ndarray] | None:
        """Embed multiple texts. Returns None on error or if not configured."""
        ...

    async def embed_text(self, text: str) -> np.ndarray | None:
        """Embed a single text. Default implementation delegates to embed_batch."""
        result = await self.embed_batch([text])
        return result[0] if result else None

    def is_configured(self) -> bool:
        """Return True if this provider is ready to embed."""
        return True

    async def close(self) -> None:
        """Clean up resources (HTTP clients, models, etc.)."""
        pass
