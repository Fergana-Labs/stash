"""Hugging Face Inference API embedding provider.

Supports any model on HF Hub (Qwen3-Embedding, nomic-embed, etc.)
via the hosted inference endpoint — no local GPU required.
"""

import logging
import os

import httpx
import numpy as np

from ._retry import TransientEmbeddingError
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
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TransientEmbeddingError(f"network error: {exc}") from exc

        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            raise TransientEmbeddingError(
                f"{resp.status_code} from HF API",
                retry_after=retry_after,
            )
        if resp.status_code >= 400:
            logger.warning(
                "HuggingFace embedding rejected: %s %s", resp.status_code, resp.text[:200]
            )
            return None

        data = resp.json()
        # Single input returns a flat list of floats; batch returns list of lists.
        if data and not isinstance(data[0], list):
            return [np.array(data, dtype=np.float32)]
        return [np.array(e, dtype=np.float32) for e in data]

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


def _parse_retry_after(header: str | None) -> float | None:
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None
