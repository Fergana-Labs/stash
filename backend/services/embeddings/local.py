"""Local embedding provider using sentence-transformers.

Runs on-device — no API key required. Downloads the model on first use.
Requires: pip install sentence-transformers
"""

import asyncio
import logging
import os

import numpy as np

from .base import BaseEmbedder

logger = logging.getLogger(__name__)


class LocalEmbedder(BaseEmbedder):
    name = "local"

    def __init__(
        self,
        model: str | None = None,
        dims: int | None = None,
    ):
        self.model_name = model or os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.dims = dims or int(os.getenv("EMBEDDING_DIMS", "384"))
        self._model = None

    def is_configured(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401

            return True
        except ImportError:
            return False

    def _load(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "Local embeddings require sentence-transformers. "
                "Install it with: pip install sentence-transformers"
            )
        logger.info("Loading local embedding model: %s", self.model_name)
        # CPU, explicitly: sentence-transformers picks Apple's Metal backend
        # (mps) when it can, and a Metal context cannot survive fork(). Celery
        # runs a prefork pool, so every child that embedded died on SIGABRT
        # ("Unable to get MPS kernel ... XPC_ERROR_CONNECTION_INVALID"), taking
        # the reconcile task — and any process that had touched the model —
        # down with it. This model is 22M params; CPU is fast enough.
        self._model = SentenceTransformer(self.model_name, device="cpu")

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray] | None:
        if not texts:
            return None
        try:
            self._load()
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, self._model.encode, texts)
            return [np.array(e, dtype=np.float32) for e in embeddings]
        except ImportError:
            raise
        except Exception as exc:
            logger.warning("Local embedding failed exception_type=%s", type(exc).__name__)
            return None

    async def close(self) -> None:
        self._model = None
