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
    assert len(captured_logs) == 1
    _, args = captured_logs[0]
    assert args[:3] == ("GET", "/__test_unhandled_error_redaction", "RuntimeError")
    filename, line, function = args[3][-1]
    assert filename.endswith("test_security_headers.py")
    assert line > 0
    assert function == "_raise_secret_error"
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


async def test_startup_restores_request_error_logging_after_migrations(monkeypatch, caplog):
    from unittest.mock import AsyncMock

    from backend import main

    async def migrations_disable_logger():
        main.logger.disabled = True

    monkeypatch.setattr(main.logger, "disabled", False)
    monkeypatch.setattr(main, "init_db", migrations_disable_logger)
    monkeypatch.setattr(main, "close_db", AsyncMock())
    monkeypatch.setattr(main.demo_service, "seed_demo", AsyncMock())

    async with main.lifespan(main.app):
        main.logger.error("Request errors remain visible after startup")

    assert "Request errors remain visible after startup" in caplog.text
