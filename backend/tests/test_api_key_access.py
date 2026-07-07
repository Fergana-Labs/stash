"""Tests for API key access levels.

A 'read' key is what a customer drops into a production agent's sandbox: it can
read/search everything in the owner's stash and push session transcripts/events,
but any other mutation must fail. If these guarantees break, a prompt-injected
agent could delete or rewrite the owner's knowledge base.
"""

import io
import json

import pytest
from httpx import AsyncClient

from backend.auth import _READ_KEY_WRITE_ALLOWLIST
from backend.main import app

from .conftest import unique_name

TRANSCRIPT = (
    json.dumps({"type": "user", "message": {"content": "hi"}, "timestamp": "2026-05-10T20:00:00Z"})
    + "\n"
).encode()


async def _register(client) -> str:
    r = await client.post(
        "/api/v1/users/register", json={"name": unique_name(), "password": "securepassword1"}
    )
    assert r.status_code == 201
    return r.json()["api_key"]


async def _mint_key(client, owner_key: str, access: str) -> str:
    r = await client.post(
        "/api/v1/users/me/keys",
        json={"name": f"{access}-key", "access": access},
        headers=_auth(owner_key),
    )
    assert r.status_code == 201
    assert r.json()["access"] == access
    return r.json()["api_key"]


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


@pytest.mark.asyncio
async def test_read_key_can_read(client: AsyncClient):
    owner_key = await _register(client)
    read_key = await _mint_key(client, owner_key, "read")

    me = await client.get("/api/v1/users/me", headers=_auth(read_key))
    assert me.status_code == 200

    owner_me = await client.get("/api/v1/users/me", headers=_auth(owner_key))
    assert me.json()["id"] == owner_me.json()["id"]

    sessions = await client.get(
        "/api/v1/me/sessions",
        params={"owner_user_id": me.json()["id"]},
        headers=_auth(read_key),
    )
    assert sessions.status_code == 200


@pytest.mark.asyncio
async def test_read_key_can_push_transcripts_and_events(client: AsyncClient):
    owner_key = await _register(client)
    read_key = await _mint_key(client, owner_key, "read")

    up = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(TRANSCRIPT), "application/jsonl")},
        data={"session_id": "sandbox-run-1", "agent_name": "heavi-parts-agent"},
        headers=_auth(read_key),
    )
    assert up.status_code == 201, up.text

    event = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "session_id": "sandbox-run-2",
            "agent_name": "heavi-parts-agent",
            "event_type": "user_prompt",
            "content": "find brake part",
        },
        headers=_auth(read_key),
    )
    assert event.status_code == 201, event.text


@pytest.mark.asyncio
async def test_read_key_mutations_forbidden(client: AsyncClient):
    owner_key = await _register(client)
    read_key = await _mint_key(client, owner_key, "read")

    upload = await client.post(
        "/api/v1/me/files",
        files={"file": ("note.md", io.BytesIO(b"# hi"), "text/markdown")},
        headers=_auth(read_key),
    )
    assert upload.status_code == 403
    assert "read-only" in upload.json()["detail"]

    delete = await client.delete(
        "/api/v1/me/files/00000000-0000-0000-0000-000000000000",
        headers=_auth(read_key),
    )
    assert delete.status_code == 403

    # A read key must not be able to mint itself a full-access key.
    escalate = await client.post(
        "/api/v1/users/me/keys",
        json={"name": "escalated", "access": "full"},
        headers=_auth(read_key),
    )
    assert escalate.status_code == 403


@pytest.mark.asyncio
async def test_full_key_can_write(client: AsyncClient):
    owner_key = await _register(client)
    full_key = await _mint_key(client, owner_key, "full")

    upload = await client.post(
        "/api/v1/me/files",
        files={"file": ("note.md", io.BytesIO(b"# hi"), "text/markdown")},
        headers=_auth(full_key),
    )
    assert upload.status_code == 201, upload.text


@pytest.mark.asyncio
async def test_revoked_read_key_is_rejected(client: AsyncClient):
    owner_key = await _register(client)

    r = await client.post(
        "/api/v1/users/me/keys",
        json={"name": "read-key", "access": "read"},
        headers=_auth(owner_key),
    )
    key_id, read_key = r.json()["id"], r.json()["api_key"]

    revoke = await client.delete(f"/api/v1/users/me/keys/{key_id}", headers=_auth(owner_key))
    assert revoke.status_code == 204

    me = await client.get("/api/v1/users/me", headers=_auth(read_key))
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_keys_list_returns_access(client: AsyncClient):
    owner_key = await _register(client)
    await _mint_key(client, owner_key, "read")

    keys = await client.get("/api/v1/users/me/keys", headers=_auth(owner_key))
    assert keys.status_code == 200
    by_name = {k["name"]: k["access"] for k in keys.json()}
    assert by_name["read-key"] == "read"


def test_allowlist_matches_registered_routes():
    """A route rename must fail this test loudly, not silently 403 production
    agents that rely on the allowlist."""
    registered = {
        (method, route.path) for route in app.routes for method in getattr(route, "methods", ())
    }
    missing = _READ_KEY_WRITE_ALLOWLIST - registered
    assert not missing, f"allowlisted routes not registered: {missing}"
