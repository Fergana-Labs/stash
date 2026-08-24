"""Channel tool restrictions on the PI harness.

A Slack/Telegram turn on a local-model sprite must run read-only: pi's
verified headless denylist (--exclude-tools write,edit,bash). Scheduled/web
turns keep the full toolset. The restriction rides on harness.channel_disallowed
and must survive the PI reseed pass (which rebuilds the argv).

Hermetic — no DB, no network, no redis, no real sprites (fake seams modeled
on test_pi_preflight.py).
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
ENDPOINT = "http://my-host:11434/v1"


def _pi_auth() -> agent_auth.RunAuth:
    return agent_auth.RunAuth(
        harness=h.PI,
        env={"PI_OFFLINE": "1"},
        files={"/home/sprite/.pi/agent/models.json": "{}"},
        endpoint=ENDPOINT,
        model="mock-1",
    )


async def _noop(*_a, **_k):
    return None


async def _true(*_a, **_k):
    return True


async def _empty_dict(*_a, **_k):
    return {}


async def _empty_history(*_a, **_k):
    return []


async def _sprite(_user_id):
    return SPRITE


async def _channel_agent(_user_id, _channel):
    return {"model_provider": "local", "system_prompt": None, "name": "Test Agent"}


async def _resolve(_user_id, _model_provider):
    return _pi_auth()


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


def _capturing_run_harness(argvs, resume_missing_on_first=False):
    calls = 0

    async def fake(_harness, _sprite_, argv, state, _provider_env):
        nonlocal calls
        calls += 1
        argvs.append(list(argv))
        if resume_missing_on_first and calls == 1:
            state.resume_missing = True
        else:
            state.result_text = "ok"
        if False:
            yield

    return fake


def _patch_run_chat_seams(monkeypatch, argvs):
    monkeypatch.setattr(agent_service, "channel_agent", _channel_agent)
    monkeypatch.setattr(agent_auth, "resolve", _resolve)
    monkeypatch.setattr(sprite_service, "local_agent_env", _empty_dict)
    monkeypatch.setattr(sprite_service, "write_file", _noop)
    monkeypatch.setattr(sprite_service, "acquire", _sprite)
    monkeypatch.setattr(sprite_service, "touch", _noop)
    monkeypatch.setattr(mcp_server_service, "sync_sprite_config", _noop)
    monkeypatch.setattr(memory_service, "push_event", _noop)
    monkeypatch.setattr(svc, "_load_history", _empty_history)
    monkeypatch.setattr(svc, "_endpoint_reachable", _true)
    monkeypatch.setattr(svc, "_TurnLock", _NoopLock)
    monkeypatch.setattr(svc, "_stoppable", _passthrough)
    monkeypatch.setattr(svc, "_run_harness", _capturing_run_harness(argvs))
    monkeypatch.setattr(h, "get_native_id", _native_id_none)


@pytest.mark.asyncio
async def test_pi_channel_restriction_survives_reseed(monkeypatch):
    """The reseed path rebuilds the argv — the denylist must ride along."""
    argvs = []
    monkeypatch.setattr(sprite_service, "write_file", _noop)
    monkeypatch.setattr(svc, "_endpoint_reachable", _true)
    monkeypatch.setattr(h, "get_native_id", _native_id_none)
    monkeypatch.setattr(
        svc, "_run_harness", _capturing_run_harness(argvs, resume_missing_on_first=True)
    )

    events = [
        e
        async for e in svc._turn_events(
            _pi_auth(),
            SPRITE,
            [{"role": "user", "content": "earlier"}],
            "hi",
            "sess-reseed",
            "sys",
            disallowed_tools=_pi_auth().harness.channel_disallowed,
        )
    ]

    assert len(argvs) == 2  # initial pass + reseed pass
    for argv in argvs:
        assert argv[-2:] == ["--exclude-tools", ",".join(h.PI.channel_disallowed)]
    assert events[-1] == {"type": "end", "_result_text": "ok"}


@pytest.mark.asyncio
async def test_slack_channel_pi_turn_carries_restrictions(monkeypatch):
    """run_chat(channel="slack") → the pi argv ends with the denylist pair."""
    argvs = []
    _patch_run_chat_seams(monkeypatch, argvs)

    final = await svc.run_chat(
        uuid.uuid4(), "Owner", uuid.uuid4(), "sess-slack", "hi", channel="slack"
    )

    assert final == "ok"
    assert len(argvs) == 1
    assert argvs[0][-2:] == ["--exclude-tools", ",".join(h.PI.channel_disallowed)]


@pytest.mark.asyncio
async def test_scheduled_pi_turn_keeps_full_toolset(monkeypatch):
    """No channel → no restriction: the scheduled toolset stays intact."""
    argvs = []
    _patch_run_chat_seams(monkeypatch, argvs)

    final = await svc.run_chat(
        uuid.uuid4(),
        "Owner",
        uuid.uuid4(),
        "sess-sched",
        "hi",
        model_provider="local",
    )

    assert final == "ok"
    assert len(argvs) == 1
    assert "--exclude-tools" not in argvs[0]
