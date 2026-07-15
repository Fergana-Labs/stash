"""Tests for the /api/v1/publish single-call publish endpoint.

The interesting behaviour is the owner_user_id fallback: a brand-new user can
publish without first looking up their scope, because register_user marks
the auto-provisioned signup scope primary.
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
async def test_publish_uses_current_user_scope(client: AsyncClient):
    """A new user can call /publish without supplying owner_user_id."""
    key = await _register(client)

    resp = await client.post(
        "/api/v1/publish",
        json={
            "title": "Untitled HTML",
            "description": "Render a shared HTML page.",
            "content_type": "html",
            "content": "<h1>hi</h1>",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_id"]
    assert body["owner_user_id"]
    assert body["url"].endswith(f"/skills/{body['skill_slug']}")


@pytest.mark.asyncio
async def test_publish_with_explicit_scope(client: AsyncClient):
    """Explicit owner_user_id works the same as before for the owner."""
    key = await _register(client)

    mine = await client.get("/api/v1/users/me", headers=_auth(key))
    owner_user_id = mine.json()["id"]

    resp = await client.post(
        "/api/v1/publish",
        json={
            "owner_user_id": owner_user_id,
            "title": "Explicit-WS publish",
            "description": "Publish into an explicit scope.",
            "content_type": "markdown",
            "content": "# hello",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["owner_user_id"] == owner_user_id


@pytest.mark.asyncio
async def test_publish_rejects_non_owner_scope(client: AsyncClient):
    """If the user passes a owner_user_id they don't own, return 403."""
    key_a = await _register(client)
    key_b = await _register(client)

    mine_b = await client.get("/api/v1/users/me", headers=_auth(key_b))
    foreign_owner = mine_b.json()["id"]

    resp = await client.post(
        "/api/v1/publish",
        json={
            "owner_user_id": foreign_owner,
            "title": "Foreign publish",
            "description": "This request must be rejected.",
            "content_type": "markdown",
            "content": "# nope",
        },
        headers=_auth(key_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_publish_by_non_owner_creates_no_page(client: AsyncClient, pool):
    """Publishing is owner-only. A user with a share row into another user's
    scope is still not the owner, so the gate must fire before the skill
    folder and page side effects are created."""
    owner_key = await _register(client)
    sharee_key, sharee_id = await _register_user(client)

    mine = await client.get("/api/v1/users/me", headers=_auth(owner_key))
    owner_user_id = mine.json()["id"]
    owner_id = owner_user_id

    folder_id = await pool.fetchval(
        "INSERT INTO folders (name, owner_user_id, created_by) VALUES ('shared', $1, $2) "
        "RETURNING id",
        owner_user_id,
        owner_id,
    )
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) "
        "VALUES ($1, 'folder', $2, 'user', $3, 'write', $4)",
        owner_user_id,
        folder_id,
        sharee_id,
        owner_id,
    )

    resp = await client.post(
        "/api/v1/publish",
        json={
            "owner_user_id": owner_user_id,
            "title": "Sharee draft",
            "description": "This request must be rejected.",
            "content": "# should not persist",
        },
        headers=_auth(sharee_key),
    )

    assert resp.status_code == 403
    page_count = await pool.fetchval(
        "SELECT COUNT(*) FROM pages WHERE owner_user_id = $1", owner_user_id
    )
    assert page_count == 0


@pytest.mark.asyncio
async def test_publish_reuses_existing_skill_md(client: AsyncClient):
    """Publishing into a folder that already carries a SKILL.md must not try to
    mint a second one (which would collide); the existing manifest is the
    metadata source of truth."""
    key = await _register(client)

    folder = await client.post(
        "/api/v1/me/folders",
        json={"name": "Prewritten skill", "is_skill": True},
        headers=_auth(key),
    )
    assert folder.status_code == 201
    folder_id = folder.json()["id"]
    skill_md = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": "SKILL.md",
            "folder_id": folder_id,
            "content": "---\nname: Hand-written skill\ndescription: Authored by the user.\n---\n",
        },
        headers=_auth(key),
    )
    assert skill_md.status_code == 201

    resp = await client.post(
        "/api/v1/publish",
        json={
            "title": "Ignored title",
            "description": "Ignored description.",
            "content": "# body",
            "folder_id": folder_id,
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["folder_id"] == folder_id

    skill = await client.get(f"/api/v1/me/skills/{folder_id}/contents", headers=_auth(key))
    md_pages = [p for p in skill.json()["contents"]["pages"] if p["name"] == "SKILL.md"]
    assert len(md_pages) == 1
    assert "Authored by the user." in md_pages[0]["content_markdown"]
