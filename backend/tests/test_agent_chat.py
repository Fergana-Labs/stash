"""Multi-turn agent chat: turns persist as a stored session and the whole
conversation is replayed to the model on each message."""

import json

import pytest
from httpx import AsyncClient

from backend.services import tool_loop

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("chat"), "password": "securepassword1"},
    )
    assert r.status_code == 201
    return r.json()["api_key"], r.json()["id"]


def _auth(k: str) -> dict:
    return {"Authorization": f"Bearer {k}"}


async def _ws(client: AsyncClient, key: str) -> str:
    r = await client.post(
        "/api/v1/workspaces", json={"name": unique_name("ws")}, headers=_auth(key)
    )
    return r.json()["id"]


def _events(sse_text: str) -> list[dict]:
    out = []
    for line in sse_text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


@pytest.mark.asyncio
async def test_agent_chat_persists_and_replays_history(client: AsyncClient, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    # Capture the history the loop is given, and emit a canned reply — no
    # Anthropic call.
    seen_histories: list[list[dict]] = []

    async def fake_loop(*, history=None, prompt=None, **kwargs):
        seen_histories.append([dict(m) for m in (history or [])])
        reply = "Reply to: " + (history[-1]["content"] if history else (prompt or ""))
        yield {"type": "text", "delta": reply}
        yield {"type": "end"}

    monkeypatch.setattr(tool_loop, "stream_tool_loop", fake_loop)

    key, _ = await _register(client)
    ws = await _ws(client, key)

    # First turn — no session_id; server mints one and streams a session event.
    r1 = await client.post(
        f"/api/v1/workspaces/{ws}/agent-chat",
        json={"message": "what did I do yesterday?"},
        headers=_auth(key),
    )
    assert r1.status_code == 200
    evts1 = _events(r1.text)
    session_evt = next(e for e in evts1 if e["type"] == "session")
    session_id = session_evt["session_id"]
    assert session_id.startswith("agent-")
    assert any(e["type"] == "text" for e in evts1)
    assert evts1[-1]["type"] == "end"

    # The first turn's history given to the model is just the user message.
    assert seen_histories[0] == [{"role": "user", "content": "what did I do yesterday?"}]

    # Second turn on the same session — the model now sees the full conversation.
    r2 = await client.post(
        f"/api/v1/workspaces/{ws}/agent-chat",
        json={"message": "and the day before?", "session_id": session_id},
        headers=_auth(key),
    )
    assert r2.status_code == 200
    assert [m["role"] for m in seen_histories[1]] == ["user", "assistant", "user"]
    assert seen_histories[1][-1]["content"] == "and the day before?"

    # The chat is a stored session: GET returns both turns' messages.
    got = await client.get(f"/api/v1/workspaces/{ws}/agent-chat/{session_id}", headers=_auth(key))
    assert got.status_code == 200
    roles = [m["role"] for m in got.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]


@pytest.mark.asyncio
async def test_agent_chat_requires_membership(client: AsyncClient, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    owner_key, _ = await _register(client)
    ws = await _ws(client, owner_key)
    other_key, _ = await _register(client)
    r = await client.post(
        f"/api/v1/workspaces/{ws}/agent-chat",
        json={"message": "hi"},
        headers=_auth(other_key),
    )
    assert r.status_code == 403
