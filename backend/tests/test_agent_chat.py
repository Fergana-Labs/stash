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
async def test_cli_death_reports_its_output_not_just_exit_code(client: AsyncClient, sprite_exec):
    # A CLI that dies without emitting stream-json (missing binary, auth
    # failure) must surface its plain-text output in the error event — a bare
    # "exited with code 1" cost us a production outage to diagnose.
    key, _ = await _register(client)
    sprite_exec.replies.append((["bash: opencode: command not found"], 127))

    r = await client.post("/api/v1/me/agent-chat", json={"message": "hi"}, headers=_auth(key))
    errors = [e for e in _events(r.text) if e["type"] == "error"]
    assert errors and "command not found" in errors[0]["message"]
    assert "exited with code 127" in errors[0]["message"]


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

    # Restoring the tab returns the tool call in order, so the client can
    # rebuild the citations strip the live stream showed.
    got = await client.get(f"/api/v1/me/agent-chat/{session_id}", headers=_auth(key))
    tool_rows = [m for m in got.json()["messages"] if m["role"] == "tool"]
    assert len(tool_rows) == 1
    assert tool_rows[0]["tool_name"] == "Bash"
    assert tool_rows[0]["metadata"]["command"] == "stash changes --json"


@pytest.mark.asyncio
async def test_stop_kills_a_running_turn(client: AsyncClient, sprite_exec, monkeypatch):
    """A stop must end the run itself (the harness exec), not just the SSE
    stream — otherwise a runaway cloud turn burns the user's box and tokens
    with no off switch. The stored session must close with the stop note so
    the chat isn't a dangling prompt."""
    import asyncio

    from backend.services import sprite_agent_service, sprite_service

    key, _ = await _register(client)

    started = asyncio.Event()

    async def hanging_exec(sprite, argv, *, env, cwd=None):
        started.set()
        await asyncio.sleep(60)
        yield {"exit_code": 0}

    monkeypatch.setattr(sprite_service, "exec_stream", hanging_exec)
    monkeypatch.setattr(sprite_agent_service, "_STOP_POLL_SECONDS", 0.05)

    session_id = "agent-stoptest"
    turn = asyncio.create_task(
        client.post(
            "/api/v1/me/agent-chat",
            json={"message": "run forever", "session_id": session_id},
            headers=_auth(key),
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5)

    st = await client.get(f"/api/v1/me/agent-chat/{session_id}/status", headers=_auth(key))
    assert st.status_code == 200
    assert st.json()["running"] is True

    stop = await client.post(f"/api/v1/me/agent-chat/{session_id}/stop", headers=_auth(key))
    assert stop.status_code == 200
    assert stop.json() == {"stopping": True}

    r = await asyncio.wait_for(turn, timeout=10)
    evts = _events(r.text)
    assert evts[-1]["type"] == "end"
    stop_note = sprite_agent_service.STOPPED_NOTE
    assert any(e["type"] == "text" and e["delta"] == stop_note for e in evts)

    got = await client.get(f"/api/v1/me/agent-chat/{session_id}", headers=_auth(key))
    assert got.json()["messages"][-1] == {"role": "assistant", "content": stop_note}

    st2 = await client.get(f"/api/v1/me/agent-chat/{session_id}/status", headers=_auth(key))
    assert st2.json()["running"] is False


@pytest.mark.asyncio
async def test_disconnect_does_not_kill_the_turn(client: AsyncClient, sprite_exec, monkeypatch):
    """The sandbox isolates the turn from the chat UI: a dropped SSE stream
    (closed tab, in-app navigation) must not cancel the run. The reply still
    records into the session and the turn lock still releases — without this,
    every disconnect bricked the chat with 'a turn is already running' for
    the full lock TTL and lost the reply."""
    import asyncio

    from backend.services import sprite_service
    from backend.tests.conftest import stream_json_reply

    key, _ = await _register(client)

    started = asyncio.Event()

    async def slow_exec(sprite, argv, *, env, cwd=None):
        started.set()
        await asyncio.sleep(0.3)
        for line in stream_json_reply("finished after you left"):
            yield {"stream": "stdout", "data": (line + "\n").encode()}
        yield {"exit_code": 0}

    monkeypatch.setattr(sprite_service, "exec_stream", slow_exec)

    session_id = "agent-disconnecttest"
    # Open the stream and abandon it as soon as the turn is underway.
    async with client.stream(
        "POST",
        "/api/v1/me/agent-chat",
        json={"message": "keep going without me", "session_id": session_id},
        headers=_auth(key),
    ) as response:
        assert response.status_code == 200
        await asyncio.wait_for(started.wait(), timeout=5)

    # The detached turn finishes: reply recorded, lock released.
    async def _settled() -> bool:
        st = await client.get(f"/api/v1/me/agent-chat/{session_id}/status", headers=_auth(key))
        return st.json()["running"] is False

    async with asyncio.timeout(10):
        while not await _settled():
            await asyncio.sleep(0.05)

    got = await client.get(f"/api/v1/me/agent-chat/{session_id}", headers=_auth(key))
    assert got.json()["messages"] == [
        {"role": "user", "content": "keep going without me"},
        {"role": "assistant", "content": "finished after you left"},
    ]


@pytest.mark.asyncio
async def test_stop_and_status_require_an_owned_session(client: AsyncClient, sprite_exec):
    """Stop is a real action on another process's run — a caller must not be
    able to stop (or probe) a session that isn't theirs or doesn't exist."""
    key, _ = await _register(client)

    r = await client.get("/api/v1/me/agent-chat/agent-nope/status", headers=_auth(key))
    assert r.status_code == 404
    r = await client.post("/api/v1/me/agent-chat/agent-nope/stop", headers=_auth(key))
    assert r.status_code == 404

    # Another user's session reads as nonexistent, not as forbidden.
    r1 = await client.post("/api/v1/me/agent-chat", json={"message": "hi"}, headers=_auth(key))
    session_id = _events(r1.text)[0]["session_id"]
    other_key, _ = await _register(client)
    r = await client.post(f"/api/v1/me/agent-chat/{session_id}/stop", headers=_auth(other_key))
    assert r.status_code == 404

    # Own session with no turn running: stop is a 409, not a silent no-op.
    r = await client.post(f"/api/v1/me/agent-chat/{session_id}/stop", headers=_auth(key))
    assert r.status_code == 409
