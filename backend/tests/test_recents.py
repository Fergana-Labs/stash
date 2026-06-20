"""Recents: a shared object can be stamped and read back via the caller's own /me/recents."""

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


@pytest.mark.asyncio
async def test_shared_page_recent_is_recordable_and_listed(client: AsyncClient):
    owner_key, _ = await _register(client, "recents_owner")
    viewer_key, viewer_name = await _register(client, "recents_viewer")

    page_resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Shared Doc"},
        headers=_auth(owner_key),
    )
    assert page_resp.status_code == 201
    page_id = page_resp.json()["id"]

    # Share the owner's page with the viewer so they can open it cross-user.
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

    # The viewer can read the shared page via the canonical object route.
    seen = await client.get(f"/api/v1/pages/{page_id}", headers=_auth(viewer_key))
    assert seen.status_code == 200

    # Stamping a recent records it in the viewer's OWN /me scope.
    recorded = await client.post(
        "/api/v1/me/recents",
        json={"object_id": page_id, "kind": "page"},
        headers=_auth(viewer_key),
    )
    assert recorded.status_code == 204

    resp = await client.get("/api/v1/me/recents", headers=_auth(viewer_key))
    assert resp.status_code == 200
    recents = resp.json()
    assert [r["object_id"] for r in recents] == [page_id]
    assert recents[0]["kind"] == "page"
