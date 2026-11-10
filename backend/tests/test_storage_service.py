import httpx
import pytest

from backend.services import storage_service


def test_object_uri_encodes_key_path_segments(monkeypatch):
    monkeypatch.setattr(storage_service, "S3_BUCKET", "stash")

    uri = storage_service._object_uri("scope/abc123/Screen Shot #1.png")

    assert uri == "/stash/scope/abc123/Screen%20Shot%20%231.png"


async def test_presigned_file_url_encodes_key(monkeypatch):
    monkeypatch.setattr(storage_service, "S3_BUCKET", "stash")
    monkeypatch.setattr(storage_service, "S3_ENDPOINT", "https://r2.example.com")
    monkeypatch.setattr(storage_service, "S3_ACCESS_KEY", "access")
    monkeypatch.setattr(storage_service, "S3_SECRET_KEY", "secret")
    monkeypatch.setattr(storage_service, "S3_REGION", "auto")

    url = await storage_service.get_file_url(
        "scope/abc123/Screen Shot #1.png",
        expires_in=300,
    )

    assert url.startswith("https://r2.example.com/stash/scope/abc123/Screen%20Shot%20%231.png?")
    assert "X-Amz-Expires=300" in url
    assert "X-Amz-Signature=" in url


def _store(monkeypatch, answers):
    """A fake store: each PUT takes the next answer, a status code or an exception to raise."""
    for name, value in {"S3_BUCKET": "stash", "S3_ENDPOINT": "https://r2.example.com"}.items():
        monkeypatch.setattr(storage_service, name, value)
    monkeypatch.setattr(storage_service, "S3_ACCESS_KEY", "access")
    monkeypatch.setattr(storage_service, "S3_SECRET_KEY", "secret")
    monkeypatch.setattr(storage_service, "PUT_BACKOFF", 0)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer, text="SlowDown" if answer >= 400 else "")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(storage_service, "_get_client", lambda: client)
    return seen


async def test_upload_retries_a_store_error_and_a_dropped_connection(monkeypatch):
    seen = _store(monkeypatch, [503, httpx.ConnectError("reset"), 200])

    key = await storage_service.upload_file("owner", "shot.png", b"png", "image/png")

    assert key.startswith("owner/") and key.endswith("/shot.png")
    assert len(seen) == 3 and all(r.method == "PUT" and r.content == b"png" for r in seen)


async def test_upload_gives_up_after_three_store_errors_and_logs_the_status(monkeypatch):
    seen = _store(monkeypatch, [503, 503, 503])
    logged: list[str] = []
    monkeypatch.setattr(
        storage_service.logger, "error", lambda msg, *args: logged.append(msg % args)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await storage_service.upload_file("owner", "shot.png", b"png", "image/png")

    assert len(seen) == 3
    assert logged == ["Storage PUT failed with status 503 after 3 attempts: SlowDown"]


async def test_upload_does_not_retry_a_refused_request(monkeypatch):
    seen = _store(monkeypatch, [403, 200])

    with pytest.raises(httpx.HTTPStatusError):
        await storage_service.upload_file("owner", "shot.png", b"png", "image/png")

    assert len(seen) == 1
