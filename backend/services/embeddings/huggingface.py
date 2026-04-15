"""Hugging Face Inference API embedding provider.

Supports any model on HF Hub (Qwen3-Embedding, nomic-embed, etc.)
via the hosted inference endpoint — no local GPU required.
"""

import logging
import os

import httpx
import numpy as np

from .base import BaseEmbedder

logger = logging.getLogger(__name__)

_HF_BASE = "https://router.huggingface.co/hf-inference/models"


class HuggingFaceEmbedder(BaseEmbedder):
    name = "huggingface"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        dims: int | None = None,
    ):
        self.model = model or os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        self.api_key = api_key or os.getenv("HF_TOKEN", "")
        self.dims = dims or int(os.getenv("EMBEDDING_DIMS", "384"))
        self.api_url = f"{_HF_BASE}/{self.model}"
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray] | None:
        if not self.api_key or not texts:
            return None

        client = self._get_client()
        try:
            resp = await client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"inputs": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            # Single input returns a flat list of floats; batch returns list of lists.
            if data and not isinstance(data[0], list):
                return [np.array(data, dtype=np.float32)]
            return [np.array(e, dtype=np.float32) for e in data]
        except Exception:
            logger.warning("HuggingFace embedding call failed", exc_info=True)
            return None

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
