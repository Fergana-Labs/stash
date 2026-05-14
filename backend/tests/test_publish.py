"""Tests for /api/v1/publish — the one-call publish endpoint used by AI agents.

Covers the workspace_id-optional fallback added so a fresh user can call
publish without first looking up their workspace id.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    name = unique_name()
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_publish_falls_back_to_primary_workspace(client: AsyncClient):
    key = await _register(client)
    resp = await client.post(
        "/api/v1/publish",
        json={
            "title": "Hello",
            "content": "<h1>Hello</h1>",
            "content_type": "html",
            "audience": "link",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["url"].endswith(f"/v/{body['view_slug']}")
    assert body["page_id"]
    assert body["workspace_id"]


@pytest.mark.asyncio
async def test_publish_with_explicit_workspace_id_still_works(client: AsyncClient):
    key = await _register(client)
    mine = await client.get("/api/v1/workspaces/mine", headers=_auth(key))
    workspace_id = mine.json()["workspaces"][0]["id"]

    resp = await client.post(
        "/api/v1/publish",
        json={
            "workspace_id": workspace_id,
            "title": "Hello explicit",
            "content": "<h1>Hi</h1>",
            "content_type": "html",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200
    assert resp.json()["workspace_id"] == workspace_id


@pytest.mark.asyncio
async def test_publish_rejects_non_member_workspace(client: AsyncClient):
    """An explicit workspace_id the caller doesn't belong to is forbidden,
    even if they have a primary workspace they could fall back to."""
    owner_key = await _register(client)
    other_key = await _register(client)
    owner_ws = (
        await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))
    ).json()["workspaces"][0]["id"]

    resp = await client.post(
        "/api/v1/publish",
        json={
            "workspace_id": owner_ws,
            "title": "Sneaky",
            "content": "x",
            "content_type": "html",
        },
        headers=_auth(other_key),
    )
    assert resp.status_code == 403
