import numpy as np
import pytest

from backend.services import embeddings as embedding_service
from backend.services.embeddings.base import BaseEmbedder
from backend.services.embeddings.openai_compat import OpenAICompatEmbedder


class CapturingEmbedder(BaseEmbedder):
    name = "capturing"

    def __init__(self):
        self.batches: list[list[str]] = []

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        self.batches.append(texts)
        return [np.array([float(i)], dtype=np.float32) for i, _text in enumerate(texts)]


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
