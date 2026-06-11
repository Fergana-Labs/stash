"""Anyone-with-the-link access over HTTP.

The public toggle (PUT /api/v1/share/public) writes a public-principal share;
the canonical resource GETs then serve anonymous viewers. Toggling it off cuts
anonymous access immediately.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_public_link_toggle_gates_anonymous_page_access(client: AsyncClient):
    owner_key, _ = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "ws"}, headers=_auth(owner_key))
    ).json()
    page = (
        await client.post(
            f"/api/v1/workspaces/{ws['id']}/pages/new",
            json={"name": "linkable", "content": "hello world"},
            headers=_auth(owner_key),
        )
    ).json()

    anonymous = await client.get(f"/api/v1/pages/{page['id']}")
    assert anonymous.status_code == 404

    toggled = await client.put(
        "/api/v1/share/public",
        json={"object_type": "page", "object_id": page["id"], "enabled": True},
        headers=_auth(owner_key),
    )
    assert toggled.status_code == 200

    shared = await client.get(f"/api/v1/pages/{page['id']}")
    assert shared.status_code == 200
    assert shared.json()["content_markdown"] == "hello world"

    # The public grant shows up in the owner's share list.
    listed = (
        await client.get(
            f"/api/v1/share?object_type=page&object_id={page['id']}",
            headers=_auth(owner_key),
        )
    ).json()["shares"]
    assert any(s["principal_type"] == "public" for s in listed)

    await client.put(
        "/api/v1/share/public",
        json={"object_type": "page", "object_id": page["id"], "enabled": False},
        headers=_auth(owner_key),
    )
    assert (await client.get(f"/api/v1/pages/{page['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_public_toggle_requires_workspace_membership(client: AsyncClient):
    owner_key, _ = await _register(client)
    outsider_key, _ = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "ws"}, headers=_auth(owner_key))
    ).json()
    page = (
        await client.post(
            f"/api/v1/workspaces/{ws['id']}/pages/new",
            json={"name": "mine", "content": "private"},
            headers=_auth(owner_key),
        )
    ).json()

    denied = await client.put(
        "/api/v1/share/public",
        json={"object_type": "page", "object_id": page["id"], "enabled": True},
        headers=_auth(outsider_key),
    )
    assert denied.status_code == 404
    assert (await client.get(f"/api/v1/pages/{page['id']}")).status_code == 404
