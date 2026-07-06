"""Multi-turn agent chat: turns execute as Claude Code on the user's cloud
computer (mocked at the sprite_service seam) and persist as a stored session.

These tests encode the contract the frontend and Slack rely on: the SSE event
ordering, --session-id vs --resume across turns, the reseed-from-history rule
when the box has lost its transcript, and the one-turn-per-session lock.
"""

import json

import pytest
from httpx import AsyncClient

from backend.services import sprite_agent_service, sprite_service

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


def _events(sse_text: str) -> list[dict]:
    out = []
    for line in sse_text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


class FakeRedis:
    """Just enough of redis.asyncio for the per-session turn lock."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value.encode() if isinstance(value, str) else value
        return True

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)


def _stream_json_reply(text: str) -> list[str]:
    """A minimal well-formed claude stream-json transcript replying `text`."""
    return [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": text},
                },
            }
        ),
        json.dumps({"type": "result", "subtype": "success", "result": text}),
    ]


@pytest.fixture
def sprite_exec(monkeypatch):
    """Mock the substrate seam: capture exec argv, reply via a queue of canned
    transcripts (default: echo the prompt back)."""
    calls: list[list[str]] = []
    replies: list[tuple[list[str], int]] = []

    async def fake_acquire(user_id):
        return sprite_service.Sprite(name="test-sprite")

    async def fake_exec_stream(sprite, argv, *, env, cwd=None):
        assert env["ANTHROPIC_API_KEY"], "turns must carry the API key"
        calls.append(argv)
        if replies:
            lines, exit_code = replies.pop(0)
        else:
            lines, exit_code = _stream_json_reply("Reply to: " + argv[2]), 0
        for line in lines:
            yield {"stream": "stdout", "data": (line + "\n").encode()}
        yield {"exit_code": exit_code}

    monkeypatch.setattr(sprite_service, "acquire", fake_acquire)
    monkeypatch.setattr(sprite_service, "exec_stream", fake_exec_stream)
    fake_redis = FakeRedis()
    monkeypatch.setattr(sprite_agent_service, "_get_redis", lambda: fake_redis)

    from backend.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-key")

    class Seam:
        pass

    seam = Seam()
    seam.calls = calls
    seam.replies = replies
    seam.redis = fake_redis
    return seam


@pytest.mark.asyncio
async def test_agent_chat_persists_and_resumes(client: AsyncClient, sprite_exec):
    key, _ = await _register(client)

    # First turn — no session_id; server mints one and streams a session event.
    r1 = await client.post(
        "/api/v1/me/agent-chat",
        json={"message": "what did I do yesterday?"},
        headers=_auth(key),
    )
    assert r1.status_code == 200
    evts1 = _events(r1.text)
    types1 = [e["type"] for e in evts1]
    assert types1[0] == "session"
    assert types1[1] == "status"
    assert "text" in types1
    assert types1[-1] == "end"
    session_id = evts1[0]["session_id"]
    assert session_id.startswith("agent-")

    # First turn starts a fresh CLI session with the raw message as prompt.
    assert "--session-id" in sprite_exec.calls[0]
    assert sprite_exec.calls[0][2] == "what did I do yesterday?"

    # Second turn on the same session resumes the same on-box transcript.
    r2 = await client.post(
        "/api/v1/me/agent-chat",
        json={"message": "and the day before?", "session_id": session_id},
        headers=_auth(key),
    )
    assert r2.status_code == 200
    assert "--resume" in sprite_exec.calls[1]

    # The chat is a stored session: GET returns both turns' messages.
    got = await client.get(f"/api/v1/me/agent-chat/{session_id}", headers=_auth(key))
    assert got.status_code == 200
    roles = [m["role"] for m in got.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert got.json()["messages"][1]["content"] == "Reply to: what did I do yesterday?"


@pytest.mark.asyncio
async def test_lost_transcript_reseeds_from_history(client: AsyncClient, sprite_exec):
    key, _ = await _register(client)

    r1 = await client.post(
        "/api/v1/me/agent-chat", json={"message": "hello"}, headers=_auth(key)
    )
    session_id = _events(r1.text)[0]["session_id"]

    # The box lost the transcript: --resume fails, then the reseeded fresh
    # session succeeds. The reseed prompt must replay stored history.
    sprite_exec.replies.append(([], 1))  # stderr-free nonzero exit won't match…
    sprite_exec.replies[0] = (
        [json.dumps({"type": "result", "subtype": "error_during_execution",
                     "result": "No conversation found with session ID: xyz"})],
        1,
    )
    sprite_exec.replies.append((_stream_json_reply("recovered"), 0))

    r2 = await client.post(
        "/api/v1/me/agent-chat",
        json={"message": "still there?", "session_id": session_id},
        headers=_auth(key),
    )
    evts = _events(r2.text)
    assert not any(e["type"] == "error" for e in evts)
    assert "".join(e.get("delta", "") for e in evts if e["type"] == "text") == "recovered"

    resume_call, reseed_call = sprite_exec.calls[1], sprite_exec.calls[2]
    assert "--resume" in resume_call
    assert "--session-id" in reseed_call
    assert "hello" in reseed_call[2]  # stored history replayed
    assert reseed_call[2].endswith("still there?")


@pytest.mark.asyncio
async def test_concurrent_turn_on_same_session_errors(client: AsyncClient, sprite_exec):
    key, _ = await _register(client)
    r1 = await client.post(
        "/api/v1/me/agent-chat", json={"message": "hi"}, headers=_auth(key)
    )
    session_id = _events(r1.text)[0]["session_id"]

    # Simulate a turn already holding the lock.
    await sprite_exec.redis.set(f"agent-turn:{session_id}", "other-turn")
    r2 = await client.post(
        "/api/v1/me/agent-chat",
        json={"message": "again", "session_id": session_id},
        headers=_auth(key),
    )
    evts = _events(r2.text)
    assert any(e["type"] == "error" for e in evts)
    assert evts[-1]["type"] == "end"


@pytest.mark.asyncio
async def test_agent_failure_surfaces_error_event(client: AsyncClient, sprite_exec):
    key, _ = await _register(client)
    sprite_exec.replies.append(
        ([json.dumps({"type": "result", "subtype": "error_during_execution",
                      "result": "API overloaded"})], 1)
    )
    r = await client.post(
        "/api/v1/me/agent-chat", json={"message": "hi"}, headers=_auth(key)
    )
    evts = _events(r.text)
    errors = [e for e in evts if e["type"] == "error"]
    assert errors and "API overloaded" in errors[0]["message"]
    assert evts[-1]["type"] == "end"

    # A failed turn persists the user message but no assistant reply.
    session_id = evts[0]["session_id"]
    got = await client.get(f"/api/v1/me/agent-chat/{session_id}", headers=_auth(key))
    assert [m["role"] for m in got.json()["messages"]] == ["user"]
