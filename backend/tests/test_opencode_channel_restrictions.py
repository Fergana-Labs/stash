"""Channel tool restrictions on the OPENCODE harness.

A Slack/Telegram turn on an OpenRouter sprite must be unable to mutate the
box: the channel turn rides a per-turn env var (OPENCODE_CONFIG_CONTENT
carrying a permission-deny config) that strips bash/edit/write from the
model's tools and refuses forced calls at execution (verified on the pinned
1.17.18). The argv is unchanged on every turn — scheduled/web turns get
exactly the pre-STAS-121 argv and env.

Hermetic — no DB, no network, no redis, no real sprites (fake seams modeled
on test_pi_channel_restrictions.py).
"""

import json
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


def _opencode_auth() -> agent_auth.RunAuth:
    return agent_auth.RunAuth(
        harness=h.OPENCODE,
        env={"OPENROUTER_API_KEY": "sk-or-mock"},
        files={"/home/sprite/.config/opencode/opencode.json": agent_auth._OPENCODE_PRIVACY_CONFIG},
    )


def _channel_env() -> dict[str, str]:
    return dict(h.OPENCODE.channel_env)


def _channel_env_permissions() -> dict[str, str]:
    """The deny map the channel env actually carries."""
    return json.loads(_channel_env()["OPENCODE_CONFIG_CONTENT"])["permission"]


async def _noop(*_a, **_k):
    return None


async def _empty_dict(*_a, **_k):
    return {}


async def _empty_history(*_a, **_k):
    return []


async def _sprite(_user_id):
    return SPRITE


async def _channel_agent(_user_id, _channel):
    return {"model_provider": "openrouter", "system_prompt": None, "name": "Test Agent"}


async def _resolve(_user_id, _model_provider):
    return _opencode_auth()


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


def test_channel_disallowed_matches_channel_env_permissions():
    """The denylist names exactly the tools the channel env denies — the
    tuple is the source of truth; a drift between the two would strand a
    mutation tool (or over-deny) silently."""
    assert _channel_env_permissions() == {t: "deny" for t in h.OPENCODE.channel_disallowed}
    assert set(h.OPENCODE.channel_disallowed) == {"bash", "edit", "write"}


def test_scheduled_argv_and_env_are_byte_identical():
    """No channel → the pre-STAS-121 argv, byte for byte, and no channel env."""
    argv = h.build_argv(
        h.OPENCODE,
        "hi",
        session_key=None,
        resume=False,
        system_prompt="sys",
    )
    assert argv == [
        "opencode",
        "run",
        "sys\n\nhi",
        "-m",
        f"{h.OPENCODE.provider.id}/{h.OPENCODE.default_model}",
        "--format",
        "json",
        "--dangerously-skip-permissions",
    ]
    # The opencode restriction rides on env, not argv: the channel turn's
    # argv must be identical too.
    argv_channel = h.build_argv(
        h.OPENCODE,
        "hi",
        session_key=None,
        resume=False,
        system_prompt="sys",
        disallowed_tools=h.OPENCODE.channel_disallowed,
    )
    assert argv_channel == argv


@pytest.mark.asyncio
async def test_opencode_channel_env_survives_reseed(monkeypatch):
    """The reseed path rebuilds the argv — the channel env must ride along."""
    argvs, envs = [], []
    monkeypatch.setattr(sprite_service, "write_file", _noop)
    monkeypatch.setattr(h, "get_native_id", _native_id_none)
    monkeypatch.setattr(
        svc, "_run_harness", _capturing_run_harness(argvs, envs, resume_missing_on_first=True)
    )

    events = [
        e
        async for e in svc._turn_events(
            _opencode_auth(),
            SPRITE,
            [{"role": "user", "content": "earlier"}],
            "hi",
            "sess-reseed",
            "sys",
            disallowed_tools=h.OPENCODE.channel_disallowed,
            channel_env=_channel_env(),
        )
    ]

    assert len(argvs) == 2  # initial pass + reseed pass
    assert len(envs) == 2
    for env in envs:
        assert env["OPENCODE_CONFIG_CONTENT"] == _channel_env()["OPENCODE_CONFIG_CONTENT"]
        # The provider credential rides alongside — the merge is additive.
        assert env["OPENROUTER_API_KEY"] == "sk-or-mock"
    # The argv mechanism is identical across both passes — only the prompt
    # differs (the reseed prompt carries the history), exactly like PI.
    assert argvs[0][:2] + argvs[0][3:] == argvs[1][:2] + argvs[1][3:]
    assert events[-1] == {"type": "end", "_result_text": "ok"}


@pytest.mark.asyncio
async def test_slack_channel_opencode_turn_carries_env(monkeypatch):
    """run_chat(channel="slack") → the exec env carries the deny config."""
    argvs, envs = [], []
    _patch_run_chat_seams(monkeypatch, argvs, envs)

    final = await svc.run_chat(
        uuid.uuid4(), "Owner", uuid.uuid4(), "sess-slack", "hi", channel="slack"
    )

    assert final == "ok"
    assert len(envs) == 1
    assert envs[0]["OPENCODE_CONFIG_CONTENT"] == _channel_env()["OPENCODE_CONFIG_CONTENT"]
    assert envs[0]["OPENROUTER_API_KEY"] == "sk-or-mock"
    # The argv is untouched by the channel mechanism (no reseed, no -s):
    # opencode run <prompt> -m openrouter/<model> --format json <skip flag>.
    assert argvs[0][:2] == ["opencode", "run"]
    assert argvs[0][-5:] == [
        "-m",
        f"{h.OPENCODE.provider.id}/{h.OPENCODE.default_model}",
        "--format",
        "json",
        "--dangerously-skip-permissions",
    ]
    assert "-s" not in argvs[0]


@pytest.mark.asyncio
async def test_scheduled_opencode_turn_has_no_channel_env(monkeypatch):
    """No channel → the exec env is the provider env, nothing more."""
    argvs, envs = [], []
    _patch_run_chat_seams(monkeypatch, argvs, envs)

    final = await svc.run_chat(
        uuid.uuid4(),
        "Owner",
        uuid.uuid4(),
        "sess-sched",
        "hi",
        model_provider="openrouter",
    )

    assert final == "ok"
    assert len(envs) == 1
    assert "OPENCODE_CONFIG_CONTENT" not in envs[0]
    assert envs[0] == {"OPENROUTER_API_KEY": "sk-or-mock"}
