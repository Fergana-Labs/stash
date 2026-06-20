"""Recents: shared objects can be stamped by non-members and read back via /me/recents."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, prefix: str) -> tuple[str, str]:
    name = unique_name(prefix)
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1", "email": f"{name}@test.local"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"], name


async def _workspace(client: AsyncClient, api_key: str, name: str) -> dict:
    resp = await client.post("/api/v1/workspaces", json={"name": name}, headers=_auth(api_key))
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_shared_page_recent_is_recordable_and_listed(client: AsyncClient):
    owner_key, _ = await _register(client, "recents_owner")
    viewer_key, viewer_name = await _register(client, "recents_viewer")
    workspace = await _workspace(client, owner_key, "Recents Source")

    page_resp = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/pages/new",
        json={"name": "Shared Doc"},
        headers=_auth(owner_key),
    )
    assert page_resp.status_code == 201
    page_id = page_resp.json()["id"]

    # Before the share, the viewer (a non-member) can't stamp a recent there.
    denied = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/recents",
        json={"object_id": page_id, "kind": "page"},
        headers=_auth(viewer_key),
    )
    assert denied.status_code == 403

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": f"{viewer_name}@test.local",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    recorded = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/recents",
        json={"object_id": page_id, "kind": "page"},
        headers=_auth(viewer_key),
    )
    assert recorded.status_code == 204

    resp = await client.get("/api/v1/me/recents", headers=_auth(viewer_key))
    assert resp.status_code == 200
    recents = resp.json()
    assert [r["object_id"] for r in recents] == [page_id]
    assert recents[0]["kind"] == "page"
    assert recents[0]["owner_user_id"] == workspace["id"]
