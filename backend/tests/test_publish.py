"""Tests for the /api/v1/publish single-call publish endpoint.

The interesting behaviour is the workspace_id fallback: a brand-new user can
publish without first looking up their workspace, because register_user marks
the auto-provisioned signup workspace primary.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register_user(client: AsyncClient) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body["id"]


async def _register(client: AsyncClient) -> str:
    api_key, _user_id = await _register_user(client)
    return api_key


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
            "public_permission": "read",
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
            "public_permission": "read",
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
            "public_permission": "read",
        },
        headers=_auth(key_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_publish_rejects_viewer_without_creating_page(client: AsyncClient, pool):
    """Publishing is a write action; viewers cannot create private draft pages."""
    owner_key = await _register(client)
    viewer_key, viewer_id = await _register_user(client)

    mine = await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))
    workspace_id = mine.json()["workspaces"][0]["id"]
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'viewer')",
        workspace_id,
        viewer_id,
    )

    resp = await client.post(
        "/api/v1/publish",
        json={
            "workspace_id": workspace_id,
            "title": "Viewer draft",
            "content": "# should not persist",
            "workspace_permission": "none",
            "public_permission": "none",
        },
        headers=_auth(viewer_key),
    )

    assert resp.status_code == 403
    page_count = await pool.fetchval(
        "SELECT COUNT(*) FROM pages WHERE workspace_id = $1", workspace_id
    )
    assert page_count == 0


@pytest.mark.asyncio
async def test_publish_rejects_editor_public_stash_without_creating_page(client: AsyncClient, pool):
    """Non-owner editors can write drafts, but cannot publish workspace/public Stashes."""
    owner_key = await _register(client)
    editor_key, editor_id = await _register_user(client)

    mine = await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))
    workspace_id = mine.json()["workspaces"][0]["id"]
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        workspace_id,
        editor_id,
    )

    resp = await client.post(
        "/api/v1/publish",
        json={
            "workspace_id": workspace_id,
            "title": "Editor public draft",
            "content": "# should not persist",
            "public_permission": "read",
        },
        headers=_auth(editor_key),
    )

    assert resp.status_code == 403
    page_count = await pool.fetchval(
        "SELECT COUNT(*) FROM pages WHERE workspace_id = $1", workspace_id
    )
    assert page_count == 0


@pytest.mark.asyncio
async def test_publish_defaults_let_editor_create_private_draft(client: AsyncClient, pool):
    """A bare publish (the CLI/MCP defaults path, no permission fields) must
    work for non-owner editors — the owner gate only guards broader
    visibility, not private drafts."""
    owner_key = await _register(client)
    editor_key, editor_id = await _register_user(client)

    mine = await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))
    workspace_id = mine.json()["workspaces"][0]["id"]
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        workspace_id,
        editor_id,
    )

    resp = await client.post(
        "/api/v1/publish",
        json={
            "workspace_id": workspace_id,
            "title": "Editor private draft",
            "content": "# mine alone",
        },
        headers=_auth(editor_key),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workspace_permission"] == "none"
    assert body["public_permission"] == "none"
    assert body["visibility"] == "private"
