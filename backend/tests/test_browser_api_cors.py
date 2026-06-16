"""CORS for the browser-facing data/AI API, and the llms.txt pointer."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_preflight_allows_any_origin(client: AsyncClient):
    resp = await client.options(
        "/rest/v1/Anything",
        headers={
            "Origin": "https://some-dashboard.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 204
    assert resp.headers["access-control-allow-origin"] == "*"
    assert "GET" in resp.headers["access-control-allow-methods"]
    assert "Content-Range" in resp.headers["access-control-expose-headers"]


@pytest.mark.asyncio
async def test_actual_request_carries_cors_header(client: AsyncClient):
    # Even an unauthenticated 401 from the data API gets the open-CORS header,
    # so the browser can read the response instead of seeing an opaque failure.
    resp = await client.get("/rest/v1/Anything", headers={"Origin": "https://x.example"})
    assert resp.headers["access-control-allow-origin"] == "*"


@pytest.mark.asyncio
async def test_llms_txt(client: AsyncClient):
    resp = await client.get("/llms.txt")
    assert resp.status_code == 200
    body = resp.text
    assert "/rest/v1/{table}" in body
    assert "useChat" in body
    assert "/openapi.json" in body
