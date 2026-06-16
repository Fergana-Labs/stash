"""Tests for the grounded AI endpoints (/ai/v1) and the AI SDK stream mapping."""

import uuid

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.services import ai_sdk, tool_loop


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient) -> str:
    name = f"user_{uuid.uuid4().hex[:10]}"
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "display_name": name, "password": "password123"},
    )
    return resp.json()["api_key"]


async def _workspace(client: AsyncClient, api_key: str) -> dict:
    return (await client.post("/api/v1/workspaces", json={"name": "AI"}, headers=_auth(api_key))).json()


@pytest.mark.asyncio
async def test_data_stream_mapping():
    async def events():
        yield {"type": "text", "delta": "Hello "}
        yield {"type": "tool", "id": "t1", "name": "search", "args": {"q": "x"}}
        yield {"type": "tool_result", "id": "t1", "name": "search", "ok": True}
        yield {"type": "end"}

    lines = [line async for line in ai_sdk.to_data_stream(events())]
    assert lines[0] == '0:"Hello "\n'
    assert lines[1] == '9:{"toolCallId":"t1","toolName":"search","args":{"q":"x"}}\n'
    assert lines[2] == 'a:{"toolCallId":"t1","result":{"ok":true}}\n'
    assert lines[3] == 'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'


@pytest.mark.asyncio
async def test_search_returns_results_shape(client: AsyncClient):
    api_key = await _register(client)
    ws = await _workspace(client, api_key)
    resp = await client.post(
        f"/ai/v1/{ws['id']}/search", json={"query": "anything"}, headers=_auth(api_key)
    )
    assert resp.status_code == 200
    assert "results" in resp.json()


@pytest.mark.asyncio
async def test_chat_streams_ai_sdk_protocol(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")

    async def fake_loop(**kwargs):
        yield {"type": "text", "delta": "Hi"}
        yield {"type": "end"}

    monkeypatch.setattr(tool_loop, "stream_tool_loop", fake_loop)

    api_key = await _register(client)
    ws = await _workspace(client, api_key)
    resp = await client.post(
        f"/ai/v1/{ws['id']}/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.headers["x-vercel-ai-data-stream"] == "v1"
    assert '0:"Hi"' in resp.text
    assert '"finishReason":"stop"' in resp.text


@pytest.mark.asyncio
async def test_publishable_key_cannot_use_ai(client: AsyncClient):
    # An anon pk_ token is not a user token, so AI rejects it.
    resp = await client.post(
        f"/ai/v1/{uuid.uuid4()}/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=_auth("pk_madeup"),
    )
    assert resp.status_code == 401
