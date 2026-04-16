"""Minimal backend coverage: upload + fetch round-trip, 413 oversize,
non-member 403. storage_service is stubbed in-memory."""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient

from backend.services import storage_service

from .conftest import unique_name

BODY = b'{"type":"user"}\n{"type":"assistant"}\n'


async def _register(client):
    r = await client.post("/api/v1/users/register",
                          json={"name": unique_name(), "password": "securepassword1"})
    assert r.status_code == 201
    return r.json()["api_key"]


async def _workspace(client, key):
    r = await client.post("/api/v1/workspaces",
                          json={"name": "ws-" + unique_name()},
                          headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 201
    return r.json()["id"]


@pytest_asyncio.fixture
async def stub_storage(monkeypatch):
    blobs: dict[str, bytes] = {}

    async def _upload(ws, name, content, ct):
        k = f"{ws}/{name}-{len(blobs)}"
        blobs[k] = content
        return k

    async def _url(k, expires_in=3600):
        return f"http://test/blobs/{k}"

    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)


@pytest.mark.asyncio
async def test_upload_and_fetch_roundtrip(client: AsyncClient, stub_storage):
    key = await _register(client)
    ws = await _workspace(client, key)

    up = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-1", "agent_name": "claude"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert up.status_code == 201, up.text
    assert up.json()["size_bytes"] == len(BODY)

    got = await client.get(
        f"/api/v1/workspaces/{ws}/transcripts/sess-1",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert got.status_code == 200
    assert got.json()["download_url"].startswith("http://test/blobs/")


@pytest.mark.asyncio
async def test_oversize_rejected(client: AsyncClient, stub_storage):
    key = await _register(client)
    ws = await _workspace(client, key)
    big = b"x" * (50 * 1024 * 1024 + 1)
    r = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(big), "application/jsonl")},
        data={"session_id": "sess-big", "agent_name": "claude"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_non_member_forbidden(client: AsyncClient, stub_storage):
    owner = await _register(client)
    other = await _register(client)
    ws = await _workspace(client, owner)
    r = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess", "agent_name": "claude"},
        headers={"Authorization": f"Bearer {other}"},
    )
    assert r.status_code == 403
