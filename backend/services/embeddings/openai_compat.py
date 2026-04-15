"""OpenAI-compatible embedding provider.

Works with OpenAI, Gemini, Cohere, Nomic, and any API that exposes
a POST /v1/embeddings endpoint with the same request/response shape.
"""

import logging
import os

import httpx
import numpy as np

from .base import BaseEmbedder

logger = logging.getLogger(__name__)


class OpenAICompatEmbedder(BaseEmbedder):
    name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        model: str | None = None,
        dims: int | None = None,
    ):
        self.api_key = api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.api_url = api_url or os.getenv(
            "EMBEDDING_API_URL", "https://api.openai.com/v1/embeddings"
        )
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.dims = dims or int(os.getenv("EMBEDDING_DIMS", "384"))
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
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
                json={
                    "model": self.model,
                    "input": texts,
                    "dimensions": self.dims,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [np.array(e["embedding"], dtype=np.float32) for e in embeddings]
        except Exception:
            logger.warning("OpenAI-compat embedding call failed", exc_info=True)
            return None

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
