from uuid import uuid4

import numpy as np
import pytest

from backend.services import embeddings as embedding_service
from backend.services.embeddings.base import BaseEmbedder
from backend.services.embeddings.openai_compat import OpenAICompatEmbedder
from backend.tasks.embeddings import _reconcile_pages


class CapturingEmbedder(BaseEmbedder):
    name = "capturing"

    def __init__(self):
        self.batches: list[list[str]] = []

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        self.batches.append(texts)
        return [np.full(384, float(i), dtype=np.float32) for i, _text in enumerate(texts)]


@pytest.mark.asyncio
async def test_embedding_wrapper_clips_texts_before_provider_call():
    embedder = CapturingEmbedder()
    embedding_service.set_embedder(embedder)

    try:
        vectors = await embedding_service.embed_batch(
            ["x" * (embedding_service.MAX_TEXT_CHARS + 100), "short"]
        )
    finally:
        await embedding_service.close()

    assert vectors is not None
    assert [len(text) for text in embedder.batches[0]] == [
        embedding_service.MAX_TEXT_CHARS,
        len("short"),
    ]


@pytest.mark.asyncio
async def test_reconcile_pages_clears_empty_pages_without_embedding_call(pool):
    """An empty input 400s the whole OpenAI batch, so empty pages must be
    cleared (embedding NULL, embed_stale FALSE) instead of sent — otherwise
    one empty page wedges every other page in its batch forever."""
    user_id = uuid4()
    await pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    empty_id, full_id = uuid4(), uuid4()
    for page_id, content in ((empty_id, ""), (full_id, "real content")):
        await pool.execute(
            "INSERT INTO pages (id, owner_user_id, name, content_markdown, created_by, "
            "embed_stale) VALUES ($1, $2, $3, $4, $5, TRUE)",
            page_id,
            user_id,
            f"p_{page_id.hex[:6]}",
            content,
            user_id,
        )

    embedder = CapturingEmbedder()
    embedding_service.set_embedder(embedder)
    try:
        done = await _reconcile_pages()
    finally:
        await embedding_service.close()

    assert done == 2
    # Only the non-empty page reached the provider.
    assert embedder.batches == [["real content"]]
    rows = {
        r["id"]: r
        for r in await pool.fetch(
            "SELECT id, embedding, embed_stale FROM pages WHERE id = ANY($1)",
            [empty_id, full_id],
        )
    }
    assert rows[empty_id]["embed_stale"] is False
    assert rows[empty_id]["embedding"] is None
    assert rows[full_id]["embed_stale"] is False
    assert rows[full_id]["embedding"] is not None


@pytest.mark.asyncio
async def test_openai_embedder_clips_inputs_before_http_request():
    class FakeResponse:
        status_code = 200
        headers: dict[str, str] = {}

        def json(self):
            return {"data": [{"index": 0, "embedding": [1.0]}]}

    class FakeClient:
        def __init__(self):
            self.payload = None

        async def post(self, _url, *, headers, json):
            self.payload = json
            return FakeResponse()

    client = FakeClient()
    embedder = OpenAICompatEmbedder(api_key="test-key")
    embedder._get_client = lambda: client

    vectors = await embedder.embed_batch(["x" * (embedding_service.MAX_TEXT_CHARS + 100)])

    assert vectors is not None
    assert len(client.payload["input"][0]) == embedding_service.MAX_TEXT_CHARS
