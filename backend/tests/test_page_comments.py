import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _setup_page(client: AsyncClient, headers: dict) -> tuple[str, str]:
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Comments"}, headers=headers)
    ).json()
    page = (
        await client.post(
            f"/api/v1/workspaces/{ws['id']}/pages/new",
            json={"name": "Doc", "content": "Hello world, this is a sample page."},
            headers=headers,
        )
    ).json()
    return ws["id"], page["id"]


async def _register_with_email(client: AsyncClient, email: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1", "email": email},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


@pytest.mark.asyncio
async def test_read_share_cannot_comment_but_comment_share_can(client: AsyncClient) -> None:
    """The comment tier: a read-only share can view threads but not post; a
    'comment' share can post. Exercised across the trust boundary (a sharee who
    is NOT a workspace member)."""
    owner_key = await _register(client)
    owner = _auth(owner_key)
    friend_email = f"{unique_name()}@example.com"
    friend_key = await _register_with_email(client, friend_email)
    friend = _auth(friend_key)
    ws_id, page_id = await _setup_page(client, owner)

    comment_body = {"quoted_text": "Hello", "prefix": "", "suffix": "", "body": "hi"}

    # Read-only share: friend can read threads, but commenting 404s.
    await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": friend_email,
            "permission": "read",
        },
        headers=owner,
    )
    list_resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads", headers=friend
    )
    assert list_resp.status_code == 200
    denied = await client.post(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
        json=comment_body,
        headers=friend,
    )
    assert denied.status_code == 404

    # Upgrade to a comment share: now the post succeeds.
    await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": friend_email,
            "permission": "comment",
        },
        headers=owner,
    )
    allowed = await client.post(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
        json=comment_body,
        headers=friend,
    )
    assert allowed.status_code == 201


@pytest.mark.asyncio
async def test_create_thread_with_first_message(client: AsyncClient) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    ws_id, page_id = await _setup_page(client, headers)

    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
        json={
            "quoted_text": "Hello world",
            "prefix": "",
            "suffix": ", this",
            "body": "What did you mean here?",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    thread = resp.json()
    assert thread["quoted_text"] == "Hello world"
    assert thread["resolved_at"] is None
    assert thread["orphaned"] is False
    assert len(thread["messages"]) == 1
    assert thread["messages"][0]["body"] == "What did you mean here?"


@pytest.mark.asyncio
async def test_reply_resolve_and_reopen(client: AsyncClient) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    ws_id, page_id = await _setup_page(client, headers)

    created = (
        await client.post(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            json={"quoted_text": "Hello", "prefix": "", "suffix": "", "body": "first"},
            headers=headers,
        )
    ).json()
    thread_id = created["id"]

    reply = await client.post(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads/{thread_id}/messages",
        json={"body": "second"},
        headers=headers,
    )
    assert reply.status_code == 201
    assert [m["body"] for m in reply.json()["messages"]] == ["first", "second"]

    resolved = await client.patch(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads/{thread_id}",
        json={"resolved": True},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None

    reopened = await client.patch(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads/{thread_id}",
        json={"resolved": False},
        headers=headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None


@pytest.mark.asyncio
async def test_delete_thread_removes_it_for_creator(client: AsyncClient) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    ws_id, page_id = await _setup_page(client, headers)

    created = (
        await client.post(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            json={"quoted_text": "x", "prefix": "", "suffix": "", "body": "msg"},
            headers=headers,
        )
    ).json()

    deleted = await client.delete(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads/{created['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204

    listing = (
        await client.get(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            headers=headers,
        )
    ).json()["threads"]
    assert listing == []


@pytest.mark.asyncio
async def test_delete_thread_forbidden_for_other_user(client: AsyncClient) -> None:
    owner_key = await _register(client)
    owner_headers = _auth(owner_key)
    ws_id, page_id = await _setup_page(client, owner_headers)
    created = (
        await client.post(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            json={"quoted_text": "x", "prefix": "", "suffix": "", "body": "msg"},
            headers=owner_headers,
        )
    ).json()

    # Join the workspace as a second user via the invite code.
    workspace = (await client.get(f"/api/v1/workspaces/{ws_id}", headers=owner_headers)).json()
    other_key = await _register(client)
    other_headers = _auth(other_key)
    await client.post(
        f"/api/v1/workspaces/join/{workspace['invite_code']}",
        headers=other_headers,
    )

    forbidden = await client.delete(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads/{created['id']}",
        headers=other_headers,
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_delete_message_auto_deletes_empty_thread(client: AsyncClient) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    ws_id, page_id = await _setup_page(client, headers)
    created = (
        await client.post(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            json={"quoted_text": "x", "prefix": "", "suffix": "", "body": "only"},
            headers=headers,
        )
    ).json()
    msg_id = created["messages"][0]["id"]

    resp = await client.delete(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/messages/{msg_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["thread_deleted"] is True
    assert body["thread"] is None

    listing = (
        await client.get(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            headers=headers,
        )
    ).json()["threads"]
    assert listing == []


@pytest.mark.asyncio
async def test_delete_one_message_keeps_thread_alive(client: AsyncClient) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    ws_id, page_id = await _setup_page(client, headers)
    created = (
        await client.post(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            json={"quoted_text": "x", "prefix": "", "suffix": "", "body": "first"},
            headers=headers,
        )
    ).json()
    second = (
        await client.post(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads/{created['id']}/messages",
            json={"body": "second"},
            headers=headers,
        )
    ).json()

    first_msg_id = created["messages"][0]["id"]
    resp = await client.delete(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/messages/{first_msg_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["thread_deleted"] is False
    assert [m["body"] for m in body["thread"]["messages"]] == ["second"]
    # Lookup by id for sanity.
    assert body["thread"]["id"] == second["id"]


@pytest.mark.asyncio
async def test_reconcile_flags_missing_threads_as_orphaned(client: AsyncClient) -> None:
    api_key = await _register(client)
    headers = _auth(api_key)
    ws_id, page_id = await _setup_page(client, headers)

    alive = (
        await client.post(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            json={"quoted_text": "alive", "prefix": "", "suffix": "", "body": "still"},
            headers=headers,
        )
    ).json()
    gone = (
        await client.post(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            json={"quoted_text": "gone", "prefix": "", "suffix": "", "body": "deleted"},
            headers=headers,
        )
    ).json()

    rec = await client.post(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/reconcile",
        json={"present_ids": [alive["id"]]},
        headers=headers,
    )
    assert rec.status_code == 204

    listing = (
        await client.get(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            headers=headers,
        )
    ).json()["threads"]
    by_id = {t["id"]: t for t in listing}
    assert by_id[alive["id"]]["orphaned"] is False
    assert by_id[gone["id"]]["orphaned"] is True

    # Resolved threads should NOT flip to orphaned even if absent.
    await client.patch(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads/{alive['id']}",
        json={"resolved": True},
        headers=headers,
    )
    await client.post(
        f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/reconcile",
        json={"present_ids": []},
        headers=headers,
    )
    listing2 = (
        await client.get(
            f"/api/v1/workspaces/{ws_id}/pages/{page_id}/comments/threads",
            headers=headers,
        )
    ).json()["threads"]
    by_id2 = {t["id"]: t for t in listing2}
    assert by_id2[alive["id"]]["orphaned"] is False
    assert by_id2[alive["id"]]["resolved_at"] is not None
