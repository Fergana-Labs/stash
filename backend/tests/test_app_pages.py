"""Tests for the 'app' (dashboard) page-kind: scripts kept, downloads non-executable."""

import uuid

import pytest
from httpx import AsyncClient

SCRIPT_HTML = (
    "<!DOCTYPE html><html><head></head><body><h1>Dash</h1>"
    '<script>window.stash.rest("Sales").then(r=>r.json())</script></body></html>'
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient) -> str:
    name = f"user_{uuid.uuid4().hex[:10]}"
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "display_name": name, "password": "password123"},
    )
    return resp.json()["api_key"]


async def _workspace(client: AsyncClient, api_key: str) -> str:
    return (
        await client.post("/api/v1/workspaces", json={"name": "App"}, headers=_auth(api_key))
    ).json()["id"]


async def _make_page(client: AsyncClient, api_key: str, ws: str, layout: str) -> dict:
    return (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={
                "name": "Dashboard",
                "content_html": SCRIPT_HTML,
                "content_type": "html",
                "html_layout": layout,
            },
            headers=_auth(api_key),
        )
    ).json()


@pytest.mark.asyncio
async def test_app_page_keeps_scripts(client: AsyncClient):
    api_key = await _register(client)
    ws = await _workspace(client, api_key)
    page = await _make_page(client, api_key, ws, "app")
    assert "<script>" in page["content_html"]
    assert "window.stash" in page["content_html"]


@pytest.mark.asyncio
async def test_non_app_html_still_strips_scripts(client: AsyncClient):
    api_key = await _register(client)
    ws = await _workspace(client, api_key)
    page = await _make_page(client, api_key, ws, "full-width")
    assert "<script" not in page["content_html"]


@pytest.mark.asyncio
async def test_html_download_is_attachment(client: AsyncClient):
    # An app page's HTML must never execute on this origin, so /download forces a
    # save (attachment) with nosniff rather than rendering inline.
    api_key = await _register(client)
    ws = await _workspace(client, api_key)
    page = await _make_page(client, api_key, ws, "app")
    resp = await client.get(
        f"/api/v1/workspaces/{ws}/pages/{page['id']}/download", headers=_auth(api_key)
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.headers["x-content-type-options"] == "nosniff"
