import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("agent_read"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _create_workspace(client: AsyncClient, api_key: str) -> dict:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": unique_name("agent_read_workspace")},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_page(
    client: AsyncClient,
    api_key: str,
    workspace_id: str,
    name: str,
    content: str,
) -> dict:
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/pages/new",
        json={"name": name, "content": content},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_public_stash_text_is_agent_homepage(client: AsyncClient):
    api_key, _ = await _register(client)
    workspace = await _create_workspace(client, api_key)
    page = await _create_page(client, api_key, workspace["id"], "Root cause", "# Finding")

    published = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/stashes/publish",
        json={
            "title": "Auth 401 spike",
            "description": "Clock skew investigation",
            "workspace_permission": "read",
            "public_permission": "read",
            "items": [{"object_type": "page", "object_id": page["id"]}],
        },
        headers=_auth(api_key),
    )
    assert published.status_code == 201
    slug = published.json()["stash"]["slug"]

    resp = await client.get(f"/api/v1/stashes/{slug}?format=text")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    text = resp.text
    assert "# Auth 401 spike" in text
    assert "This page is the Stash homepage" in text
    assert f"http://localhost:3457/stashes/{slug}.md" in text
    assert f"http://localhost:3457/stashes/{slug}.json" in text
    assert f"/stashes/{slug}/items/page/{page['id']}.md" in text
    assert "Clock skew investigation" in text


@pytest.mark.asyncio
async def test_public_stash_item_text_strips_html_page_content(client: AsyncClient):
    api_key, _ = await _register(client)
    workspace = await _create_workspace(client, api_key)

    published = await client.post(
        "/api/v1/publish",
        json={
            "workspace_id": workspace["id"],
            "title": "HTML strategy memo",
            "content_type": "html",
            "content": "<main><h1>Hello Agent</h1><p>Read this first.</p></main>",
            "workspace_permission": "read",
            "public_permission": "read",
        },
        headers=_auth(api_key),
    )
    assert published.status_code == 200
    body = published.json()

    resp = await client.get(
        f"/api/v1/stashes/{body['stash_slug']}/items/page/{body['page_id']}?format=text"
    )
    assert resp.status_code == 200
    assert "Hello Agent" in resp.text
    assert "Read this first." in resp.text
    assert "<h1>" not in resp.text

    json_resp = await client.get(
        f"/api/v1/stashes/{body['stash_slug']}/items/page/{body['page_id']}"
    )
    assert json_resp.status_code == 200
    assert json_resp.json()["item"]["inline"]["page"]["content_type"] == "html"


@pytest.mark.asyncio
async def test_llms_txt_documents_agent_stash_reads(client: AsyncClient):
    resp = await client.get("/llms.txt")
    assert resp.status_code == 200
    assert "Public Stash URLs are agent-readable" in resp.text
    assert "/stashes/example.md" in resp.text
