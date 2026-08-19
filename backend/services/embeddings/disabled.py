"""Embeddings explicitly turned off (EMBEDDING_PROVIDER=none).

Semantic search returns 503 and the reconcile task skips — every callsite
already gates on is_configured(). For local dev where embeddings are not
worth a torch install (or its crashes).
"""

import numpy as np

from .base import BaseEmbedder


class DisabledEmbedder(BaseEmbedder):
    name = "none"

    def is_configured(self) -> bool:
        return False

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray] | None:
        raise RuntimeError(
            "Embeddings are disabled (EMBEDDING_PROVIDER=none) — "
            "callers must check is_configured() before embedding."
        )

    async def close(self) -> None:
        pass
