"""Tests for in-product Skill invite notifications.

Sharing a skill goes through the unified share endpoint (object_type='skill'),
which also creates the invite notification.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _share_skill(client, owner_key, skill_id, email, permission="read"):
    resp = await client.post(
        "/api/v1/share",
        json={
            "object_type": "skill",
            "object_id": skill_id,
            "email": email,
            "permission": permission,
        },
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200
    return resp.json()


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name or unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.mark.asyncio
async def test_skill_invite_grants_view_access_before_adding(client: AsyncClient, pool):
    owner_key, _owner = await _register(client, "skill_invite_owner")
    recipient_key, recipient = await _register(client, "skill_invite_recipient")

    source_workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Source workspace"},
            headers=_auth(owner_key),
        )
    ).json()
    target_workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Recipient workspace"},
            headers=_auth(recipient_key),
        )
    ).json()
    page = (
        await client.post(
            f"/api/v1/workspaces/{source_workspace['id']}/pages/new",
            json={"name": "Partner plan", "content": "private context"},
            headers=_auth(owner_key),
        )
    ).json()
    stash = (
        await client.post(
            f"/api/v1/workspaces/{source_workspace['id']}/skills",
            json={
                "title": "Partner Stash",
                "workspace_permission": "none",
                "public_permission": "none",
                "items": [{"object_type": "page", "object_id": page["id"]}],
            },
            headers=_auth(owner_key),
        )
    ).json()

    await pool.execute(
        "UPDATE users SET email = 'invite-recipient@example.com' WHERE id = $1",
        UUID(recipient["id"]),
    )
    await _share_skill(client, owner_key, stash["id"], "invite-recipient@example.com")

    invites = await client.get("/api/v1/skill-invites", headers=_auth(recipient_key))
    assert invites.status_code == 200
    [invite] = invites.json()["invites"]
    assert invite["skill_id"] == stash["id"]
    assert invite["skill_title"] == "Partner Stash"
    assert invite["source_workspace_id"] == source_workspace["id"]
    assert invite["permission"] == "read"

    viewed = await client.get(
        f"/api/v1/skills/{stash['slug']}",
        headers=_auth(recipient_key),
    )
    assert viewed.status_code == 200
    assert viewed.json()["skill"]["id"] == stash["id"]

    still_pending = await client.get("/api/v1/skill-invites", headers=_auth(recipient_key))
    assert len(still_pending.json()["invites"]) == 1

    added = await client.post(
        f"/api/v1/skills/{stash['slug']}/add-to-workspace",
        json={"workspace_id": target_workspace["id"]},
        headers=_auth(recipient_key),
    )
    assert added.status_code == 201
    fork = added.json()
    assert fork["is_external"] is True
    assert fork["workspace_id"] == target_workspace["id"]
    assert fork["forked_from_skill_id"] == stash["id"]

    remaining = await client.get("/api/v1/skill-invites", headers=_auth(recipient_key))
    assert remaining.json()["invites"] == []


@pytest.mark.asyncio
async def test_skill_invite_can_be_dismissed(client: AsyncClient, pool):
    owner_key, _owner = await _register(client, "stash_dismiss_owner")
    recipient_key, recipient = await _register(client, "stash_dismiss_recipient")

    workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Source workspace"},
            headers=_auth(owner_key),
        )
    ).json()
    page = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/pages/new",
            json={"name": "Draft", "content": "hello"},
            headers=_auth(owner_key),
        )
    ).json()
    stash = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/skills",
            json={
                "title": "Dismissable Stash",
                "workspace_permission": "none",
                "public_permission": "none",
                "items": [{"object_type": "page", "object_id": page["id"]}],
            },
            headers=_auth(owner_key),
        )
    ).json()
    await pool.execute(
        "UPDATE users SET email = 'dismiss-recipient@example.com' WHERE id = $1",
        UUID(recipient["id"]),
    )
    await _share_skill(client, owner_key, stash["id"], "dismiss-recipient@example.com")

    invites = (await client.get("/api/v1/skill-invites", headers=_auth(recipient_key))).json()
    invite_id = invites["invites"][0]["id"]

    dismissed = await client.post(
        f"/api/v1/skill-invites/{invite_id}/dismiss",
        headers=_auth(recipient_key),
    )
    assert dismissed.status_code == 204

    remaining = await client.get("/api/v1/skill-invites", headers=_auth(recipient_key))
    assert remaining.json()["invites"] == []

    viewed = await client.get(
        f"/api/v1/skills/{stash['slug']}",
        headers=_auth(recipient_key),
    )
    assert viewed.status_code == 200
