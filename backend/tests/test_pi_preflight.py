"""PI turn-start preflight: a dead local endpoint must fail loudly BEFORE pi
is launched — pi itself exits 0 on connection errors, so the only early
signal is a sprite-side curl probe of the endpoint.

The probe runs on the sprite (the backend never dials the user's URL):
curl --max-time 5 {base_url}/models; any HTTP response = reachable.
"""

import pytest

from backend.services import agent_auth, sprite_agent_service, sprite_service
from backend.services import harness as h

SPRITE = object()  # _turn_events passes the sprite straight through to helpers

ENDPOINT = "http://my-host:11434/v1"


def _pi_auth() -> agent_auth.RunAuth:
    return agent_auth.RunAuth(
        harness=h.PI,
        env={"PI_OFFLINE": "1"},
        files={"/home/sprite/.pi/agent/models.json": "{}"},
        endpoint=ENDPOINT,
        model="llama3.1:8b",
    )


async def _noop_write(sprite, path, contents):
    return None


def _fake_exec_collect(exit_code):
    calls: list[dict] = []

    async def fake_exec_collect(sprite, argv, *, env, cwd=None, timeout_s, stdout_only=False):
        calls.append({"argv": argv, "env": env, "timeout_s": timeout_s, "stdout_only": stdout_only})
        return "", exit_code

    return fake_exec_collect, calls


async def _fake_run_harness(harness, sprite, argv, state, provider_env):
    state.result_text = "ok"
    if False:
        yield


async def _native_id_none(session_id, harness_id):
    return None


@pytest.mark.asyncio
async def test_unreachable_endpoint_fails_loud_before_pi_launch(monkeypatch):
    monkeypatch.setattr(sprite_service, "write_file", _noop_write)
    fake_exec, calls = _fake_exec_collect(7)  # curl 7 = connection refused
    monkeypatch.setattr(sprite_service, "exec_collect", fake_exec)

    def argv_must_not_run(*_a, **_k):
        raise AssertionError("build_argv must not be called for an unreachable endpoint")

    monkeypatch.setattr(h, "build_argv", argv_must_not_run)

    events = [
        e
        async for e in sprite_agent_service._turn_events(
            _pi_auth(), SPRITE, [], "hi", "sess-preflight", "sys"
        )
    ]

    # Exactly one error, then end — the "one end/error event" contract.
    assert len(events) == 2
    assert events[0]["type"] == "error"
    assert ENDPOINT in events[0]["message"]
    assert "tunnel" in events[0]["message"]
    assert events[1] == {"type": "end", "_result_text": ""}

    # The probe is the sprite's curl, a 5s cap, and never the backend's: empty env.
    assert calls[0]["argv"] == [
        "curl",
        "-s",
        "-o",
        "/dev/null",
        "--max-time",
        "5",
        f"{ENDPOINT}/models",
    ]
    assert calls[0]["env"] == {}
    assert calls[0]["timeout_s"] == 20
    assert calls[0]["stdout_only"] is True


@pytest.mark.asyncio
async def test_reachable_endpoint_builds_pi_argv_with_model(monkeypatch):
    monkeypatch.setattr(sprite_service, "write_file", _noop_write)
    fake_exec, calls = _fake_exec_collect(0)  # any HTTP response = reachable
    monkeypatch.setattr(sprite_service, "exec_collect", fake_exec)

    argv_calls: list[dict] = []

    def fake_build_argv(harness, prompt, **kwargs):
        argv_calls.append({"harness": harness, "prompt": prompt, **kwargs})
        return ["pi", "--mode", "json"]

    monkeypatch.setattr(h, "build_argv", fake_build_argv)
    monkeypatch.setattr(h, "get_native_id", _native_id_none)
    monkeypatch.setattr(sprite_agent_service, "_run_harness", _fake_run_harness)

    events = [
        e
        async for e in sprite_agent_service._turn_events(
            _pi_auth(), SPRITE, [], "hi", "sess-preflight", "sys"
        )
    ]

    assert events == [{"type": "end", "_result_text": "ok"}]
    # The probe ran (exit 0) and the turn proceeded to pi with the local model.
    assert len(calls) == 1
    assert argv_calls[0]["harness"] is h.PI
    assert argv_calls[0]["model"] == "llama3.1:8b"
    assert argv_calls[0]["resume"] is False  # no native id yet → turn 1


@pytest.mark.asyncio
async def test_non_pi_harness_never_probes(monkeypatch):
    """Claude/Codex/OpenRouter turns must never probe a user endpoint."""
    monkeypatch.setattr(sprite_service, "write_file", _noop_write)

    def must_not_probe(*_a, **_k):
        raise AssertionError("exec_collect must not be called for a non-PI harness")

    monkeypatch.setattr(sprite_service, "exec_collect", must_not_probe)
    monkeypatch.setattr(h, "build_argv", lambda harness, prompt, **kw: ["claude", "-p", prompt])
    monkeypatch.setattr(h, "get_native_id", _native_id_none)
    monkeypatch.setattr(sprite_agent_service, "_run_harness", _fake_run_harness)

    auth = agent_auth.RunAuth(harness=h.CLAUDE, env={"ANTHROPIC_API_KEY": "sk-ant-x"})
    events = [
        e
        async for e in sprite_agent_service._turn_events(
            auth, SPRITE, [], "hi", "sess-preflight", "sys"
        )
    ]
    assert events == [{"type": "end", "_result_text": "ok"}]
