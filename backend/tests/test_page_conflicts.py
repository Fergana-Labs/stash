"""Optimistic-concurrency saves: expected_content_hash refuses stale writes."""

import uuid

import pytest
from httpx import AsyncClient


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> tuple[str, dict]:
    name = f"user_{uuid.uuid4().hex[:10]}"
    response = await client.post(
        "/api/v1/users/register",
        json={"name": name, "display_name": name, "password": "password123"},
    )
    assert response.status_code == 201
    body = response.json()
    return body["api_key"], body


@pytest.mark.asyncio
async def test_stale_expected_hash_409s_and_fresh_hash_saves(client: AsyncClient):
    """The editor saves on top of the version it loaded. A save carrying a
    stale expected_content_hash must 409 (someone saved since — reload), and
    one carrying the current hash must land and return the new hash."""
    api_key, _ = await _register(client)
    created = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Doc", "content": "v1"},
        headers=_auth(api_key),
    )
    page = created.json()

    fresh = await client.patch(
        f"/api/v1/me/pages/{page['id']}",
        json={"content": "v2", "expected_content_hash": page["content_hash"]},
        headers=_auth(api_key),
    )
    assert fresh.status_code == 200
    assert fresh.json()["content_markdown"] == "v2"

    stale = await client.patch(
        f"/api/v1/me/pages/{page['id']}",
        json={"content": "v3-from-stale-tab", "expected_content_hash": page["content_hash"]},
        headers=_auth(api_key),
    )
    assert stale.status_code == 409
    assert "reload" in stale.json()["detail"]

    untouched = await client.get(f"/api/v1/pages/{page['id']}", headers=_auth(api_key))
    assert untouched.json()["content_markdown"] == "v2"
    assert untouched.json()["can_write"] is True
