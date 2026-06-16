"""Tests for short-lived, read-only dashboard tokens (the generative-UI backend)."""

import uuid

import pytest
from httpx import AsyncClient

from backend import auth
from backend.config import settings

_SECRET = "test-dashboard-secret-which-is-long-enough"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient) -> tuple[str, dict]:
    name = f"user_{uuid.uuid4().hex[:10]}"
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "display_name": name, "password": "password123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


async def _make_workspace(client: AsyncClient, api_key: str) -> dict:
    return (
        await client.post(
            "/api/v1/workspaces", json={"name": "Dash"}, headers=_auth(api_key)
        )
    ).json()


@pytest.fixture(autouse=True)
def _enable_dashboard_tokens(monkeypatch):
    monkeypatch.setattr(settings, "DASHBOARD_TOKEN_SECRET", _SECRET)


@pytest.mark.asyncio
async def test_minted_token_reads_owner_data(client: AsyncClient):
    api_key, _user = await _register(client)
    ws = await _make_workspace(client, api_key)

    minted = await client.post(
        "/api/v1/dashboard-tokens",
        json={"workspace_id": ws["id"]},
        headers=_auth(api_key),
    )
    assert minted.status_code == 201
    dt = minted.json()["token"]
    assert dt.startswith("dt_")

    # The dashboard token authenticates a read of the owner's workspace.
    listed = await client.get(
        f"/api/v1/workspaces/{ws['id']}/pages", headers=_auth(dt)
    )
    assert listed.status_code == 200


@pytest.mark.asyncio
async def test_mint_requires_membership(client: AsyncClient):
    _owner_key, _ = await _register(client)
    owner_ws = await _make_workspace(client, _owner_key)

    outsider_key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/dashboard-tokens",
        json={"workspace_id": owner_ws["id"]},
        headers=_auth(outsider_key),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_token_cannot_mint_tokens(client: AsyncClient):
    api_key, _ = await _register(client)
    ws = await _make_workspace(client, api_key)
    dt = (
        await client.post(
            "/api/v1/dashboard-tokens",
            json={"workspace_id": ws["id"]},
            headers=_auth(api_key),
        )
    ).json()["token"]

    resp = await client.post(
        "/api/v1/dashboard-tokens",
        json={"workspace_id": ws["id"]},
        headers=_auth(dt),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient):
    api_key, user = await _register(client)
    ws = await _make_workspace(client, api_key)

    expired, _exp = auth.mint_dashboard_token(user["id"], ws["id"], ttl_seconds=-10)
    resp = await client.get(
        f"/api/v1/workspaces/{ws['id']}/pages", headers=_auth(expired)
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tampered_token_rejected(client: AsyncClient):
    api_key, user = await _register(client)
    ws = await _make_workspace(client, api_key)

    token, _exp = auth.mint_dashboard_token(user["id"], ws["id"])
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    resp = await client.get(
        f"/api/v1/workspaces/{ws['id']}/pages", headers=_auth(tampered)
    )
    assert resp.status_code == 401
