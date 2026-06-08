import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_responses_include_security_headers(client: AsyncClient):
    resp = await client.get("/health")

    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
