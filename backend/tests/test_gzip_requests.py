"""Gzipped request bodies must be transparently decompressed.

The Cloudflare WAF fronting Render 403s raw agent shell text as command
injection ("stash share" was blocked entirely). Clients therefore gzip JSON
bodies; GzipRequestMiddleware must restore them so routing sees plain JSON,
and a body that lies about its encoding must fail loud with a 400.
"""

import gzip
import json

import pytest
from httpx import AsyncClient

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("gzip"),
            "display_name": "Gzip Tester",
            "password": "securepassword1",
        },
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


# Shell text that the edge WAF rejects when sent raw — the exact class of
# content that motivated gzipping (command substitution + curl auth header).
_WAF_HOSTILE = (
    "```bash\n"
    '$ TOKEN=$(gcloud auth print-access-token); curl -s -H "Authorization: '
    'Bearer $TOKEN" https://example.com | python3 -c "import sys"\n'
    "```"
)


@pytest.mark.asyncio
async def test_gzipped_page_create_round_trips(client: AsyncClient):
    api_key = await _register(client)

    body = json.dumps({"name": "WAF-hostile page", "content": _WAF_HOSTILE}).encode()
    resp = await client.post(
        "/api/v1/me/pages/new",
        content=gzip.compress(body),
        headers={
            **_auth(api_key),
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )
    assert resp.status_code == 201
    page_id = resp.json()["id"]

    read = await client.get(f"/api/v1/me/pages/{page_id}", headers=_auth(api_key))
    assert read.status_code == 200
    assert read.json()["content_markdown"] == _WAF_HOSTILE


@pytest.mark.asyncio
async def test_plain_requests_are_untouched(client: AsyncClient):
    api_key = await _register(client)

    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Plain page", "content": "no encoding header"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_invalid_gzip_body_is_a_400(client: AsyncClient):
    api_key = await _register(client)

    resp = await client.post(
        "/api/v1/me/pages/new",
        content=b"this is not gzip",
        headers={
            **_auth(api_key),
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )
    assert resp.status_code == 400
    assert "gzip" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_truncated_gzip_body_is_a_400(client: AsyncClient):
    """A body cut off mid-stream inflates without error but is incomplete.

    zlib returns the bytes it managed to inflate rather than raising, so
    without an explicit end-of-stream check a half-received request would
    reach routing as silently truncated JSON.
    """
    api_key = await _register(client)

    whole = gzip.compress(json.dumps({"name": "Truncated", "content": _WAF_HOSTILE}).encode())
    resp = await client.post(
        "/api/v1/me/pages/new",
        content=whole[: len(whole) // 2],
        headers={
            **_auth(api_key),
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_gzip_bomb_is_refused_before_it_is_buffered(client: AsyncClient):
    """Compression amplifies, so an uncapped decompressor is a memory DoS.

    A few hundred kilobytes on the wire inflate to gigabytes; the request must
    be refused on size rather than accepted because it arrived small.
    """
    api_key = await _register(client)

    bomb = gzip.compress(b"\0" * (200 * 1024 * 1024))
    assert len(bomb) < 1024 * 1024, "the point of the test is a small body that inflates hugely"

    resp = await client.post(
        "/api/v1/me/pages/new",
        content=bomb,
        headers={
            **_auth(api_key),
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )
    assert resp.status_code == 413
