"""Tests for chat creation, messaging, retrieval, and personal rooms."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    name = name or unique_name()
    resp = await client.post("/api/v1/users/register", json={
        "name": name, "type": "human", "password": "securepassword1",
    })
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _create_workspace(client: AsyncClient, api_key: str, name: str = "ws") -> dict:
    resp = await client.post("/api/v1/workspaces", json={"name": name}, headers=_auth(api_key))
    assert resp.status_code == 201
    return resp.json()


# --- Workspace chats ---


@pytest.mark.asyncio
async def test_create_chat_in_workspace(client: AsyncClient):
    key, _ = await _register(client)
    ws = await _create_workspace(client, key)

    resp = await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats",
        json={"name": "general", "description": "main channel"},
        headers=_auth(key),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "general"
    assert body["workspace_id"] == ws["id"]


@pytest.mark.asyncio
async def test_list_chats(client: AsyncClient):
    key, _ = await _register(client)
    ws = await _create_workspace(client, key)
    h = _auth(key)

    await client.post(f"/api/v1/workspaces/{ws['id']}/chats", json={"name": "general"}, headers=h)
    await client.post(f"/api/v1/workspaces/{ws['id']}/chats", json={"name": "random"}, headers=h)

    resp = await client.get(f"/api/v1/workspaces/{ws['id']}/chats", headers=h)
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["chats"]}
    assert names == {"general", "random"}


@pytest.mark.asyncio
async def test_non_member_cannot_create_chat(client: AsyncClient):
    owner_key, _ = await _register(client)
    stranger_key, _ = await _register(client)
    ws = await _create_workspace(client, owner_key)

    resp = await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats",
        json={"name": "nope"},
        headers=_auth(stranger_key),
    )
    assert resp.status_code == 403


# --- Messaging ---


@pytest.mark.asyncio
async def test_send_and_retrieve_message(client: AsyncClient):
    key, user = await _register(client)
    ws = await _create_workspace(client, key)
    h = _auth(key)

    chat = (await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats", json={"name": "general"}, headers=h,
    )).json()

    msg_resp = await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats/{chat['id']}/messages",
        json={"content": "Hello, world!"},
        headers=h,
    )
    assert msg_resp.status_code == 200
    msg = msg_resp.json()
    assert msg["content"] == "Hello, world!"
    assert msg["sender_name"] == user["name"]

    history = await client.get(
        f"/api/v1/workspaces/{ws['id']}/chats/{chat['id']}/messages",
        headers=h,
    )
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello, world!"


@pytest.mark.asyncio
async def test_message_pagination(client: AsyncClient):
    key, _ = await _register(client)
    ws = await _create_workspace(client, key)
    h = _auth(key)

    chat = (await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats", json={"name": "busy"}, headers=h,
    )).json()

    for i in range(5):
        await client.post(
            f"/api/v1/workspaces/{ws['id']}/chats/{chat['id']}/messages",
            json={"content": f"msg-{i}"},
            headers=h,
        )

    resp = await client.get(
        f"/api/v1/workspaces/{ws['id']}/chats/{chat['id']}/messages?limit=3",
        headers=h,
    )
    body = resp.json()
    assert len(body["messages"]) == 3
    assert body["has_more"] is True


@pytest.mark.asyncio
async def test_non_member_cannot_send_message(client: AsyncClient):
    owner_key, _ = await _register(client)
    stranger_key, _ = await _register(client)
    ws = await _create_workspace(client, owner_key)
    h = _auth(owner_key)

    chat = (await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats", json={"name": "private"}, headers=h,
    )).json()

    resp = await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats/{chat['id']}/messages",
        json={"content": "sneaky"},
        headers=_auth(stranger_key),
    )
    assert resp.status_code == 403


# --- Delete chat ---


@pytest.mark.asyncio
async def test_owner_can_delete_chat(client: AsyncClient):
    key, _ = await _register(client)
    ws = await _create_workspace(client, key)
    h = _auth(key)

    chat = (await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats", json={"name": "temp"}, headers=h,
    )).json()

    resp = await client.delete(f"/api/v1/workspaces/{ws['id']}/chats/{chat['id']}", headers=h)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_member_cannot_delete_chat(client: AsyncClient):
    owner_key, _ = await _register(client)
    member_key, _ = await _register(client)
    ws = await _create_workspace(client, owner_key)

    await client.post(f"/api/v1/workspaces/join/{ws['invite_code']}", headers=_auth(member_key))

    chat = (await client.post(
        f"/api/v1/workspaces/{ws['id']}/chats", json={"name": "protected"}, headers=_auth(owner_key),
    )).json()

    resp = await client.delete(
        f"/api/v1/workspaces/{ws['id']}/chats/{chat['id']}", headers=_auth(member_key),
    )
    assert resp.status_code == 403


# --- Personal rooms ---


@pytest.mark.asyncio
async def test_personal_room_crud(client: AsyncClient):
    key, _ = await _register(client)
    h = _auth(key)

    create_resp = await client.post("/api/v1/rooms", json={"name": "my room"}, headers=h)
    assert create_resp.status_code == 201
    room = create_resp.json()
    assert room["workspace_id"] is None

    list_resp = await client.get("/api/v1/rooms", headers=h)
    assert list_resp.status_code == 200
    assert any(r["id"] == room["id"] for r in list_resp.json()["chats"])

    del_resp = await client.delete(f"/api/v1/rooms/{room['id']}", headers=h)
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_access_other_users_room(client: AsyncClient):
    owner_key, _ = await _register(client)
    other_key, _ = await _register(client)

    room = (await client.post("/api/v1/rooms", json={"name": "secret"}, headers=_auth(owner_key))).json()

    resp = await client.delete(f"/api/v1/rooms/{room['id']}", headers=_auth(other_key))
    assert resp.status_code == 404
