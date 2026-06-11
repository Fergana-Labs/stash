"""Tests for the /api/v1/publish single-call publish endpoint.

The interesting behaviour is the workspace_id fallback: a brand-new user can
publish without first looking up their workspace, because register_user marks
the auto-provisioned signup workspace primary.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_publish_falls_back_to_primary_workspace(client: AsyncClient):
    """A new user can call /publish without supplying workspace_id."""
    key = await _register(client)

    resp = await client.post(
        "/api/v1/publish",
        json={
            "title": "Untitled HTML",
            "content_type": "html",
            "content": "<h1>hi</h1>",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_id"]
    assert body["workspace_id"]
    assert body["url"].endswith(f"/skills/{body['skill_slug']}")


@pytest.mark.asyncio
async def test_publish_with_explicit_workspace(client: AsyncClient):
    """Explicit workspace_id works the same as before for members."""
    key = await _register(client)

    mine = await client.get("/api/v1/workspaces/mine", headers=_auth(key))
    workspace_id = mine.json()["workspaces"][0]["id"]

    resp = await client.post(
        "/api/v1/publish",
        json={
            "workspace_id": workspace_id,
            "title": "Explicit-WS publish",
            "content_type": "markdown",
            "content": "# hello",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["workspace_id"] == workspace_id


@pytest.mark.asyncio
async def test_publish_rejects_non_member_workspace(client: AsyncClient):
    """If the user passes a workspace_id they don't belong to, return 403."""
    key_a = await _register(client)
    key_b = await _register(client)

    mine_b = await client.get("/api/v1/workspaces/mine", headers=_auth(key_b))
    foreign_workspace = mine_b.json()["workspaces"][0]["id"]

    resp = await client.post(
        "/api/v1/publish",
        json={
            "workspace_id": foreign_workspace,
            "title": "Foreign publish",
            "content_type": "markdown",
            "content": "# nope",
        },
        headers=_auth(key_a),
    )
    assert resp.status_code == 403
