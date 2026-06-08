import pytest

from backend.services import embeddings
from backend.services.embeddings import huggingface, local, openai_compat
from backend.services.embeddings.base import BaseEmbedder, TransientEmbeddingError


class _TransientFailureEmbedder(BaseEmbedder):
    name = "redaction-test"

    async def embed_batch(self, texts: list[str]):
        raise TransientEmbeddingError(
            "customer transcript text with token=secret-token",
            retry_after=0,
        )


class _FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text
        self.headers = {}


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self.response = response

    async def post(self, *args, **kwargs):
        return self.response


def _capture_logs(target_logger, monkeypatch):
    captured_logs: list[tuple[str, tuple, dict]] = []

    def capture(message, *args, **kwargs):
        captured_logs.append((message, args, kwargs))

    monkeypatch.setattr(target_logger, "info", capture)
    monkeypatch.setattr(target_logger, "warning", capture)
    return captured_logs


@pytest.mark.asyncio
async def test_embedding_retry_logs_only_metadata(monkeypatch):
    captured_logs = _capture_logs(embeddings.logger, monkeypatch)

    async def skip_sleep(delay):
        return None

    monkeypatch.setattr(embeddings, "_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(embeddings, "_semaphore", None)
    monkeypatch.setattr(embeddings.asyncio, "sleep", skip_sleep)
    embeddings.set_embedder(_TransientFailureEmbedder())
    try:
        result = await embeddings.embed_text("customer transcript text token=secret-token")
    finally:
        await embeddings.close()
        monkeypatch.setattr(embeddings, "_semaphore", None)

    assert result is None
    assert captured_logs == [
        (
            "Embedding provider transient failure provider=%s operation=%s attempt=%d/%d exception_type=%s retry_delay=%.2fs",
            ("redaction-test", "embed_text", 1, 2, "TransientEmbeddingError", 0),
            {},
        ),
        (
            "Embedding provider failed after retries provider=%s operation=embed_text exception_type=%s",
            ("redaction-test", "TransientEmbeddingError"),
            {},
        ),
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_openai_compat_rejection_logs_only_status(monkeypatch):
    captured_logs = _capture_logs(openai_compat.logger, monkeypatch)
    embedder = openai_compat.OpenAICompatEmbedder(api_key="secret-api-key")
    monkeypatch.setattr(
        embedder,
        "_get_client",
        lambda: _FakeClient(_FakeResponse(400, "customer transcript text with token=secret-token")),
    )

    result = await embedder.embed_batch(["customer transcript text token=secret-token"])

    assert result is None
    assert captured_logs == [("OpenAI-compat embedding rejected status_code=%s", (400,), {})]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_huggingface_rejection_logs_only_status(monkeypatch):
    captured_logs = _capture_logs(huggingface.logger, monkeypatch)
    embedder = huggingface.HuggingFaceEmbedder(api_key="secret-api-key")
    monkeypatch.setattr(
        embedder,
        "_get_client",
        lambda: _FakeClient(_FakeResponse(400, "customer transcript text with token=secret-token")),
    )

    result = await embedder.embed_batch(["customer transcript text token=secret-token"])

    assert result is None
    assert captured_logs == [("HuggingFace embedding rejected status_code=%s", (400,), {})]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_local_embedding_failure_logs_only_exception_type(monkeypatch):
    captured_logs = _capture_logs(local.logger, monkeypatch)

    class BadModel:
        def encode(self, texts):
            raise RuntimeError("customer transcript text with token=secret-token")

    embedder = local.LocalEmbedder()
    embedder._model = BadModel()

    result = await embedder.embed_batch(["customer transcript text token=secret-token"])

    assert result is None
    assert captured_logs == [("Local embedding failed exception_type=%s", ("RuntimeError",), {})]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
