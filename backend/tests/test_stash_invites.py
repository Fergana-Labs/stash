"""Tests for in-product Stash invite notifications."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


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
async def test_stash_invite_grants_view_access_before_adding(client: AsyncClient):
    owner_key, _owner = await _register(client, "stash_invite_owner")
    recipient_key, recipient = await _register(client, "stash_invite_recipient")

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
            f"/api/v1/workspaces/{source_workspace['id']}/stashes",
            json={
                "title": "Partner Stash",
                "access": "private",
                "items": [{"object_type": "page", "object_id": page["id"]}],
            },
            headers=_auth(owner_key),
        )
    ).json()

    added_member = await client.post(
        f"/api/v1/stashes/{stash['id']}/members",
        json={"user_id": recipient["id"], "permission": "read"},
        headers=_auth(owner_key),
    )
    assert added_member.status_code == 201

    invites = await client.get("/api/v1/stash-invites", headers=_auth(recipient_key))
    assert invites.status_code == 200
    [invite] = invites.json()["invites"]
    assert invite["stash_id"] == stash["id"]
    assert invite["stash_title"] == "Partner Stash"
    assert invite["source_workspace_id"] == source_workspace["id"]
    assert invite["permission"] == "read"

    viewed = await client.get(
        f"/api/v1/stashes/{stash['slug']}",
        headers=_auth(recipient_key),
    )
    assert viewed.status_code == 200
    assert viewed.json()["stash"]["id"] == stash["id"]

    still_pending = await client.get("/api/v1/stash-invites", headers=_auth(recipient_key))
    assert len(still_pending.json()["invites"]) == 1

    added = await client.post(
        f"/api/v1/stashes/{stash['slug']}/add-to-workspace",
        json={"workspace_id": target_workspace["id"]},
        headers=_auth(recipient_key),
    )
    assert added.status_code == 201
    fork = added.json()
    assert fork["is_external"] is True
    assert fork["workspace_id"] == target_workspace["id"]
    assert fork["forked_from_stash_id"] == stash["id"]

    remaining = await client.get("/api/v1/stash-invites", headers=_auth(recipient_key))
    assert remaining.json()["invites"] == []


@pytest.mark.asyncio
async def test_stash_invite_can_be_dismissed(client: AsyncClient):
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
            f"/api/v1/workspaces/{workspace['id']}/stashes",
            json={
                "title": "Dismissable Stash",
                "access": "private",
                "items": [{"object_type": "page", "object_id": page["id"]}],
            },
            headers=_auth(owner_key),
        )
    ).json()
    await client.post(
        f"/api/v1/stashes/{stash['id']}/members",
        json={"user_id": recipient["id"], "permission": "read"},
        headers=_auth(owner_key),
    )

    invites = (await client.get("/api/v1/stash-invites", headers=_auth(recipient_key))).json()
    invite_id = invites["invites"][0]["id"]

    dismissed = await client.post(
        f"/api/v1/stash-invites/{invite_id}/dismiss",
        headers=_auth(recipient_key),
    )
    assert dismissed.status_code == 204

    remaining = await client.get("/api/v1/stash-invites", headers=_auth(recipient_key))
    assert remaining.json()["invites"] == []

    viewed = await client.get(
        f"/api/v1/stashes/{stash['slug']}",
        headers=_auth(recipient_key),
    )
    assert viewed.status_code == 200


@pytest.mark.asyncio
async def test_stash_share_api_grants_and_revokes_stash_level_access(client: AsyncClient):
    owner_key, owner = await _register(client, unique_name("stash_share_owner"))
    recipient_key, recipient = await _register(client, unique_name("stash_share_recipient"))

    workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Share API workspace"},
            headers=_auth(owner_key),
        )
    ).json()
    page = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/pages/new",
            json={"name": "Private brief", "content": "stash-only context"},
            headers=_auth(owner_key),
        )
    ).json()
    stash = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/stashes",
            json={
                "title": "Share API Stash",
                "access": "private",
                "items": [{"object_type": "page", "object_id": page["id"]}],
            },
            headers=_auth(owner_key),
        )
    ).json()

    shared = await client.patch(
        f"/api/v1/stashes/{stash['id']}/share",
        json={
            "people": [{"username": recipient["name"], "permission": "read"}],
        },
        headers=_auth(owner_key),
    )
    assert shared.status_code == 200
    body = shared.json()
    assert body["stash"]["id"] == stash["id"]
    assert body["url"].endswith(f"/stashes/{stash['slug']}")
    assert body["owner"]["user_id"] == owner["id"]
    assert body["members"][0]["user_id"] == recipient["id"]
    assert body["members"][0]["permission"] == "read"

    workspace_members = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/members",
        headers=_auth(owner_key),
    )
    assert recipient["id"] not in [member["user_id"] for member in workspace_members.json()]

    viewed = await client.get(
        f"/api/v1/stashes/{stash['slug']}",
        headers=_auth(recipient_key),
    )
    assert viewed.status_code == 200

    invites = await client.get("/api/v1/stash-invites", headers=_auth(recipient_key))
    assert len(invites.json()["invites"]) == 1

    removed = await client.patch(
        f"/api/v1/stashes/{stash['id']}/share",
        json={"remove_user_ids": [recipient["id"]]},
        headers=_auth(owner_key),
    )
    assert removed.status_code == 200
    assert removed.json()["members"] == []

    no_longer_viewable = await client.get(
        f"/api/v1/stashes/{stash['slug']}",
        headers=_auth(recipient_key),
    )
    assert no_longer_viewable.status_code == 404

    remaining = await client.get("/api/v1/stash-invites", headers=_auth(recipient_key))
    assert remaining.json()["invites"] == []
