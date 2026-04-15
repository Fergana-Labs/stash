"""Base embedding interface. Subclass this to bring your own provider."""

from abc import ABC, abstractmethod

import numpy as np


class BaseEmbedder(ABC):
    """Override embed_batch() to bring your own embedding provider.

    Example::

        from backend.services.embeddings import BaseEmbedder, set_embedder

        class MyEmbedder(BaseEmbedder):
            name = "my-custom"
            dims = 768

            async def embed_batch(self, texts):
                return [my_model.encode(t) for t in texts]

        set_embedder(MyEmbedder())
    """

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
