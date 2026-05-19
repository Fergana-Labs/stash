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
