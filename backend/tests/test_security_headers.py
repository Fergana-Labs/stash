import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_responses_include_security_headers(client: AsyncClient):
    resp = await client.get("/health")

    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )


@pytest.mark.asyncio
async def test_unhandled_errors_are_redacted_and_keep_security_headers(
    client: AsyncClient, monkeypatch
):
    from backend import main

    captured_logs: list[tuple[str, tuple]] = []

    def capture_error(message: str, *args, **kwargs) -> None:
        captured_logs.append((message, args))

    monkeypatch.setattr(main.logger, "error", capture_error)

    @main.app.get("/__test_unhandled_error_redaction")
    async def _raise_secret_error():
        raise RuntimeError("token=secret-token and customer transcript")

    resp = await client.get("/__test_unhandled_error_redaction")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "secret-token" not in resp.text
    assert "customer transcript" not in resp.text
    assert captured_logs == [
        (
            "Unhandled request failed method=%s path=%s exception_type=%s",
            ("GET", "/__test_unhandled_error_redaction", "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
