"""OpenAI-compatible embedding provider.

Works with OpenAI, Gemini, Cohere, Nomic, and any API that exposes
a POST /v1/embeddings endpoint with the same request/response shape.
"""

import logging
import os

import httpx
import numpy as np

from .base import BaseEmbedder, TransientEmbeddingError

logger = logging.getLogger(__name__)

# OpenAI-compatible endpoints cap each input at 8192 tokens. Logs, code, and
# IDs can get close to one token per char, so keep a real margin.
_PER_INPUT_CHAR_CAP = 6_000


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

        inputs = [t[:_PER_INPUT_CHAR_CAP] for t in texts]

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
                    "input": inputs,
                    "dimensions": self.dims,
                },
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TransientEmbeddingError("network error from embedding API") from exc

        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            raise TransientEmbeddingError(
                f"{resp.status_code} from embedding API",
                retry_after=retry_after,
            )
        if resp.status_code >= 400:
            logger.warning("OpenAI-compat embedding rejected status_code=%s", resp.status_code)
            return None

        data = resp.json()
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [np.array(e["embedding"], dtype=np.float32) for e in embeddings]

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
