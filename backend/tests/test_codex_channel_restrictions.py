"""Channel tool restrictions on the CODEX harness.

A Slack/Telegram turn on an OpenAI-key sprite must be unable to mutate the
box: the channel argv swaps --dangerously-bypass-approvals-and-sandbox for
the verified --sandbox read-only tail (the read-only sandbox blocks
exec_command's filesystem writes at execution time). Scheduled/web turns
keep the bypass flag — their argv must stay byte-identical.

Hermetic — no DB, no network, no redis, no real sprites (fake seams modeled
on test_pi_channel_restrictions.py).
"""

import uuid

import pytest

from backend.services import (
    agent_auth,
    agent_service,
    mcp_server_service,
    memory_service,
    sprite_service,
)
from backend.services import harness as h
from backend.services import sprite_agent_service as svc

SPRITE = object()  # passed straight through to the faked _run_harness

BYPASS = "--dangerously-bypass-approvals-and-sandbox"


def _codex_auth() -> agent_auth.RunAuth:
    return agent_auth.RunAuth(
        harness=h.CODEX,
        env={"OPENAI_API_KEY": "sk-mock"},
        files={},
    )


async def _noop(*_a, **_k):
    return None


async def _empty_dict(*_a, **_k):
    return {}


async def _empty_history(*_a, **_k):
    return []


async def _sprite(_user_id):
    return SPRITE


async def _channel_agent(_user_id, _channel):
    return {"model_provider": "openai", "system_prompt": None, "name": "Test Agent"}


async def _resolve(_user_id, _model_provider):
    return _codex_auth()


async def _native_id_none(_session_id, _harness_id):
    return None


class _NoopLock:
    def __init__(self, _session_id):
        pass

    async def __aenter__(self):
        return None

    async def __aexit__(self, *_exc):
        return False


async def _passthrough(events, _session_id):
    async for event in events:
        yield event


def _capturing_run_harness(argvs, envs, resume_missing_on_first=False):
    calls = 0

    async def fake(_harness, _sprite_, argv, state, provider_env):
        nonlocal calls
        calls += 1
        argvs.append(list(argv))
        envs.append(dict(provider_env))
        if resume_missing_on_first and calls == 1:
            state.resume_missing = True
        else:
            state.result_text = "ok"
        if False:
            yield

    return fake


def _patch_run_chat_seams(monkeypatch, argvs, envs):
    monkeypatch.setattr(agent_service, "channel_agent", _channel_agent)
    monkeypatch.setattr(agent_auth, "resolve", _resolve)
    monkeypatch.setattr(sprite_service, "local_agent_env", _empty_dict)
    monkeypatch.setattr(sprite_service, "write_file", _noop)
    monkeypatch.setattr(sprite_service, "acquire", _sprite)
    monkeypatch.setattr(sprite_service, "touch", _noop)
    monkeypatch.setattr(mcp_server_service, "sync_sprite_config", _noop)
    monkeypatch.setattr(memory_service, "push_event", _noop)
    monkeypatch.setattr(svc, "_load_history", _empty_history)
    monkeypatch.setattr(svc, "_TurnLock", _NoopLock)
    monkeypatch.setattr(svc, "_stoppable", _passthrough)
    monkeypatch.setattr(svc, "_run_harness", _capturing_run_harness(argvs, envs))
    monkeypatch.setattr(h, "get_native_id", _native_id_none)


def _channel_argv() -> list[str]:
    """The channel-turn argv the CODEX branch must produce."""
    argv = h.build_argv(
        h.CODEX,
        "hi",
        session_key=None,
        resume=False,
        system_prompt="sys",
        disallowed_tools=h.CODEX.channel_disallowed,
    )
    assert "--sandbox" in argv
    assert "read-only" in argv
    assert BYPASS not in argv
    return argv


def test_codex_channel_argv_is_sandbox_read_only():
    """Channel turn: the bypass flag is replaced by --sandbox read-only."""
    argv = _channel_argv()
    # The tail replaces the bypass flag in place — the rest of the argv is
    # unchanged (prompt, --json, --skip-git-repo-check).
    assert argv[:-2] == [
        "codex",
        "exec",
        "sys\n\nhi",
        "--json",
        "--skip-git-repo-check",
    ]
    assert argv[-2:] == ["--sandbox", "read-only"]


def test_codex_scheduled_argv_is_byte_identical():
    """No channel → the pre-STAS-121 argv, byte for byte."""
    argv = h.build_argv(
        h.CODEX,
        "hi",
        session_key=None,
        resume=False,
        system_prompt="sys",
    )
    assert argv == [
        "codex",
        "exec",
        "sys\n\nhi",
        "--json",
        "--skip-git-repo-check",
        BYPASS,
    ]
    assert "--sandbox" not in argv


@pytest.mark.asyncio
async def test_codex_channel_restriction_survives_reseed(monkeypatch):
    """The reseed path rebuilds the argv — the sandbox tail must ride along."""
    argvs, envs = [], []
    monkeypatch.setattr(sprite_service, "write_file", _noop)
    monkeypatch.setattr(h, "get_native_id", _native_id_none)
    monkeypatch.setattr(
        svc, "_run_harness", _capturing_run_harness(argvs, envs, resume_missing_on_first=True)
    )

    events = [
        e
        async for e in svc._turn_events(
            _codex_auth(),
            SPRITE,
            [{"role": "user", "content": "earlier"}],
            "hi",
            "sess-reseed",
            "sys",
            disallowed_tools=h.CODEX.channel_disallowed,
        )
    ]

    assert len(argvs) == 2  # initial pass + reseed pass
    for argv in argvs:
        assert argv[-2:] == ["--sandbox", "read-only"]
        assert BYPASS not in argv
    assert events[-1] == {"type": "end", "_result_text": "ok"}


@pytest.mark.asyncio
async def test_slack_channel_codex_turn_carries_sandbox(monkeypatch):
    """run_chat(channel="slack") → the codex argv ends with the sandbox tail."""
    argvs, envs = [], []
    _patch_run_chat_seams(monkeypatch, argvs, envs)

    final = await svc.run_chat(
        uuid.uuid4(), "Owner", uuid.uuid4(), "sess-slack", "hi", channel="slack"
    )

    assert final == "ok"
    assert len(argvs) == 1
    assert argvs[0][-2:] == ["--sandbox", "read-only"]
    assert BYPASS not in argvs[0]
    # The codex restriction rides on argv, not env — the channel turn adds
    # no env of its own.
    assert envs[0] == {"OPENAI_API_KEY": "sk-mock"}


@pytest.mark.asyncio
async def test_scheduled_codex_turn_keeps_bypass(monkeypatch):
    """No channel → the scheduled argv keeps the bypass flag, byte-identical."""
    argvs, envs = [], []
    _patch_run_chat_seams(monkeypatch, argvs, envs)

    final = await svc.run_chat(
        uuid.uuid4(),
        "Owner",
        uuid.uuid4(),
        "sess-sched",
        "hi",
        model_provider="openai",
    )

    assert final == "ok"
    assert len(argvs) == 1
    assert argvs[0][-1] == BYPASS
    assert "--sandbox" not in argvs[0]
