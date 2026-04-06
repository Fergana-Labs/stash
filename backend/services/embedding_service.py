"""Embedding service: async text embedding via external API.

Supports any OpenAI-compatible embedding endpoint (OpenAI, local sentence-transformers, etc.).
Configured via environment variables.
"""

import logging
import os

import httpx
import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "https://api.openai.com/v1/embeddings")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "384"))

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


def is_configured() -> bool:
    """Check if embedding service has the required API key."""
    return bool(EMBEDDING_API_KEY)


async def embed_text(text: str) -> np.ndarray | None:
    """Embed a single text string. Returns None if not configured or on error."""
    if not EMBEDDING_API_KEY:
        return None
    result = await embed_batch([text])
    return result[0] if result else None


async def embed_batch(texts: list[str]) -> list[np.ndarray] | None:
    """Embed multiple texts in one API call. Returns None if not configured or on error."""
    if not EMBEDDING_API_KEY or not texts:
        return None

    client = _get_client()
    try:
        resp = await client.post(
            EMBEDDING_API_URL,
            headers={
                "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": texts,
                "dimensions": EMBEDDING_DIMS,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenAI-compatible response: {"data": [{"embedding": [...], "index": 0}, ...]}
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [np.array(e["embedding"], dtype=np.float32) for e in embeddings]
    except Exception:
        logger.warning("Embedding API call failed", exc_info=True)
        return None


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
