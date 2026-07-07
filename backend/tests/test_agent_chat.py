"""Multi-turn agent chat: turns execute as Claude Code on the user's cloud
computer (mocked at the sprite_service seam) and persist as a stored session.

These tests encode the contract the frontend and Slack rely on: the SSE event
ordering, --session-id vs --resume across turns, the reseed-from-history rule
when the box has lost its transcript, and the one-turn-per-session lock.
"""

import json

import pytest
from httpx import AsyncClient

from .conftest import stream_json_reply, unique_name


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

    r1 = await client.post("/api/v1/me/agent-chat", json={"message": "hello"}, headers=_auth(key))
    session_id = _events(r1.text)[0]["session_id"]

    # The box lost the transcript: --resume fails, then the reseeded fresh
    # session succeeds. The reseed prompt must replay stored history.
    sprite_exec.replies.append(([], 1))  # stderr-free nonzero exit won't match…
    sprite_exec.replies[0] = (
        [
            json.dumps(
                {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "result": "No conversation found with session ID: xyz",
                }
            )
        ],
        1,
    )
    sprite_exec.replies.append((stream_json_reply("recovered"), 0))

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
    r1 = await client.post("/api/v1/me/agent-chat", json={"message": "hi"}, headers=_auth(key))
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
        (
            [
                json.dumps(
                    {
                        "type": "result",
                        "subtype": "error_during_execution",
                        "result": "API overloaded",
                    }
                )
            ],
            1,
        )
    )
    r = await client.post("/api/v1/me/agent-chat", json={"message": "hi"}, headers=_auth(key))
    evts = _events(r.text)
    errors = [e for e in evts if e["type"] == "error"]
    assert errors and "API overloaded" in errors[0]["message"]
    assert evts[-1]["type"] == "end"

    # A failed turn records the failure as the reply — a prompt with no
    # answer would be indistinguishable from a run that never happened.
    session_id = evts[0]["session_id"]
    got = await client.get(f"/api/v1/me/agent-chat/{session_id}", headers=_auth(key))
    messages = got.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert "API overloaded" in messages[1]["content"]


@pytest.mark.asyncio
async def test_tool_calls_persist_as_history_events(client: AsyncClient, sprite_exec, _db_pool):
    """Cloud runs have no plugin hooks, so the backend itself must record the
    harness's tool calls — otherwise the stored session is prompt + answer
    only and a run's behavior can't be audited after the fact."""
    key, _ = await _register(client)

    sprite_exec.replies.append(
        (
            [
                json.dumps({"type": "system", "subtype": "init"}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "tu1",
                                    "name": "Bash",
                                    "input": {"command": "stash changes --json"},
                                }
                            ]
                        },
                    }
                ),
                json.dumps({"type": "result", "subtype": "success", "result": "done"}),
            ],
            0,
        )
    )
    r = await client.post("/api/v1/me/agent-chat", json={"message": "curate"}, headers=_auth(key))
    evts = _events(r.text)
    assert any(e["type"] == "tool" for e in evts)  # still streamed live
    session_id = evts[0]["session_id"]

    row = await _db_pool.fetchrow(
        "SELECT content, tool_name FROM history_events "
        "WHERE session_id = $1 AND event_type = 'tool_use'",
        session_id,
    )
    assert row is not None
    assert row["tool_name"] == "Bash"
    assert row["content"] == "Ran: stash changes --json"
