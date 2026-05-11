"""Tests for the curated public Discover catalog."""

import pytest
from httpx import AsyncClient

from backend.config import settings

from .conftest import unique_name


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    name = name or unique_name()
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _admin() -> dict:
    return {"X-Admin-Token": "test-admin"}


@pytest.mark.asyncio
async def test_discover_lists_only_curated_public_workspaces(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-admin")
    key, _ = await _register(client)

    public_ws = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Public candidate", "is_public": True},
            headers=_auth(key),
        )
    ).json()
    private_ws = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Private workspace", "is_public": False},
            headers=_auth(key),
        )
    ).json()

    empty = await client.get("/api/v1/discover/workspaces")
    assert empty.status_code == 200
    assert empty.json()["workspaces"] == []

    direct_public = await client.get(f"/api/v1/public/workspaces/{public_ws['id']}")
    assert direct_public.status_code == 200
    unlisted_detail = await client.get(f"/api/v1/discover/workspaces/{public_ws['id']}")
    assert unlisted_detail.status_code == 404

    curate = await client.patch(
        f"/api/v1/admin/discover/workspaces/{public_ws['id']}",
        json={"discoverable": True, "featured": True, "summary": "Worth browsing"},
        headers=_admin(),
    )
    assert curate.status_code == 200
    assert curate.json()["discoverable"] is True
    assert curate.json()["featured"] is True

    reject_private = await client.patch(
        f"/api/v1/admin/discover/workspaces/{private_ws['id']}",
        json={"discoverable": True},
        headers=_admin(),
    )
    assert reject_private.status_code == 400

    catalog = await client.get("/api/v1/discover/workspaces")
    assert catalog.status_code == 200
    workspaces = catalog.json()["workspaces"]
    assert [w["id"] for w in workspaces] == [public_ws["id"]]
    assert workspaces[0]["summary"] == "Worth browsing"
    listed_detail = await client.get(f"/api/v1/discover/workspaces/{public_ws['id']}")
    assert listed_detail.status_code == 200


@pytest.mark.asyncio
async def test_admin_discover_candidates_are_public_only(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-admin")
    key, _ = await _register(client)

    public_ws = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Public candidate", "is_public": True},
            headers=_auth(key),
        )
    ).json()
    await client.post(
        "/api/v1/workspaces",
        json={"name": "Private workspace", "is_public": False},
        headers=_auth(key),
    )

    res = await client.get("/api/v1/admin/discover/workspaces", headers=_admin())
    assert res.status_code == 200
    workspaces = res.json()["workspaces"]
    assert [w["id"] for w in workspaces] == [public_ws["id"]]
    assert workspaces[0]["discoverable"] is False

    unauthorized = await client.get("/api/v1/admin/discover/workspaces")
    assert unauthorized.status_code == 401
