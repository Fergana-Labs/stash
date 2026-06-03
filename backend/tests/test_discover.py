"""Tests for the public Stash Discover catalog."""

import pytest
from httpx import AsyncClient

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


async def _create_workspace(client: AsyncClient, api_key: str, name: str) -> dict:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": name},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_page(client: AsyncClient, api_key: str, workspace_id: str, name: str) -> dict:
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/pages/new",
        json={"name": name, "content": f"# {name}"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_discover_lists_discoverable_public_product_stashes(client: AsyncClient):
    api_key, user = await _register(client)
    workspace = await _create_workspace(client, api_key, "Discovery workspace")
    public_page = await _create_page(client, api_key, workspace["id"], "Public brief")
    private_page = await _create_page(client, api_key, workspace["id"], "Private brief")

    private_cartridge = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/cartridges",
        json={
            "title": "Private notes",
            "items": [{"object_type": "page", "object_id": private_page["id"]}],
        },
        headers=_auth(api_key),
    )
    assert private_cartridge.status_code == 201

    public_unlisted = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/cartridges/publish",
        json={
            "title": "Public but unlisted",
            "workspace_permission": "read",
            "public_permission": "read",
            "items": [{"object_type": "page", "object_id": public_page["id"]}],
        },
        headers=_auth(api_key),
    )
    assert public_unlisted.status_code == 201

    published = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/cartridges/publish",
        json={
            "title": "Public notes",
            "description": "A public Stash",
            "workspace_permission": "read",
            "public_permission": "read",
            "discoverable": True,
            "items": [{"object_type": "page", "object_id": public_page["id"]}],
        },
        headers=_auth(api_key),
    )
    assert published.status_code == 201
    published_cartridge = published.json()["cartridge"]
    slug = published_cartridge["slug"]
    assert published_cartridge["owner_name"] == user["name"]
    assert published_cartridge["owner_display_name"] == user["display_name"]

    workspace_stashes = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/cartridges",
        headers=_auth(api_key),
    )
    assert workspace_stashes.status_code == 200
    workspace_cartridge = next(
        stash for stash in workspace_stashes.json()["cartridges"] if stash["slug"] == slug
    )
    assert workspace_cartridge["owner_name"] == user["name"]
    assert workspace_cartridge["owner_display_name"] == user["display_name"]

    catalog = await client.get("/api/v1/discover/cartridges")
    assert catalog.status_code == 200
    cartridges = catalog.json()["cartridges"]
    assert [stash["title"] for stash in cartridges] == ["Public notes"]
    assert cartridges[0]["slug"] == slug
    assert cartridges[0]["discoverable"] is True
    assert cartridges[0]["item_count"] == 1
    assert cartridges[0]["workspace_name"] == workspace["name"]

    detail = await client.get(f"/api/v1/cartridges/{slug}")
    assert detail.status_code == 200
    assert detail.json()["cartridge"]["discoverable"] is True
    assert detail.json()["cartridge"]["owner_name"] == user["name"]
    assert detail.json()["cartridge"]["owner_display_name"] == user["display_name"]

    unlisted_detail = await client.get(
        f"/api/v1/cartridges/{public_unlisted.json()['cartridge']['slug']}"
    )
    assert unlisted_detail.status_code == 200


@pytest.mark.asyncio
async def test_discover_opt_in_requires_public_product_cartridge(client: AsyncClient):
    api_key, _ = await _register(client)
    workspace = await _create_workspace(client, api_key, "Private Discover workspace")
    page = await _create_page(client, api_key, workspace["id"], "Private Discover brief")

    workspace_cartridge = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/cartridges",
        json={
            "title": "Workspace Discover attempt",
            "workspace_permission": "read",
            "public_permission": "none",
            "discoverable": True,
            "items": [{"object_type": "page", "object_id": page["id"]}],
        },
        headers=_auth(api_key),
    )
    assert workspace_cartridge.status_code == 400

    private_cartridge = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/cartridges",
        json={
            "title": "Private Discover attempt",
            "workspace_permission": "none",
            "public_permission": "none",
            "discoverable": True,
            "items": [{"object_type": "page", "object_id": page["id"]}],
        },
        headers=_auth(api_key),
    )
    assert private_cartridge.status_code == 400


@pytest.mark.asyncio
async def test_discover_search_filters_product_stashes(client: AsyncClient):
    api_key, _ = await _register(client)
    workspace = await _create_workspace(client, api_key, "Search workspace")
    alpha = await _create_page(client, api_key, workspace["id"], "Alpha")
    beta = await _create_page(client, api_key, workspace["id"], "Beta")

    for title, page in (("Alpha launch notes", alpha), ("Beta roadmap", beta)):
        resp = await client.post(
            f"/api/v1/workspaces/{workspace['id']}/cartridges/publish",
            json={
                "title": title,
                "workspace_permission": "read",
                "public_permission": "read",
                "discoverable": True,
                "items": [{"object_type": "page", "object_id": page["id"]}],
            },
            headers=_auth(api_key),
        )
        assert resp.status_code == 201

    filtered = await client.get("/api/v1/discover/cartridges?q=alpha")
    assert filtered.status_code == 200
    assert [stash["title"] for stash in filtered.json()["cartridges"]] == ["Alpha launch notes"]
