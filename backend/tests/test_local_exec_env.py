"""Local exec env isolation.

Local mode runs the harness on the developer's own machine, inheriting the
backend process's environment. Two classes of vars must never cross that
boundary: the backend's own secrets (its ANTHROPIC_API_KEY would override
the developer's local Claude login) and pi's session plumbing (the backend
itself can run inside a pi-hosted agent — an inherited PI_PACKAGE_DIR points
the child pi at the host's staging dir and it crashes on startup).
"""

import pytest

from backend.config import settings
from backend.services import sprite_service

BLOCKED = [
    "ANTHROPIC_API_KEY",
    "PI_PACKAGE_DIR",
    "PI_SESSION_ID",
    "PI_SESSION_FILE",
    "PI_PROVIDER",
    "PI_MODEL",
    "PI_REASONING_LEVEL",
]


def test_local_inherited_env_blocks_session_plumbing(monkeypatch):
    monkeypatch.setattr(
        "os.environ",
        {
            "PATH": "/usr/bin",
            "ANTHROPIC_API_KEY": "sk-ant-backend",
            "PI_PACKAGE_DIR": "/tmp/fn-pkg-host",
            "PI_SESSION_ID": "host-session",
            "PI_SESSION_FILE": "/tmp/host-session.jsonl",
            "PI_PROVIDER": "host-provider",
            "PI_MODEL": "host-model",
            "PI_REASONING_LEVEL": "off",
            "STASH_LOCAL_KEY": "pass-through",
        },
    )
    env = sprite_service._local_inherited_env()
    for name in BLOCKED:
        assert name not in env, name
    # Only the blocked set is filtered; the rest passes through untouched.
    assert env["PATH"] == "/usr/bin"
    assert env["STASH_LOCAL_KEY"] == "pass-through"


@pytest.mark.asyncio
async def test_local_exec_child_never_sees_blocked_vars(monkeypatch):
    """The filter is only real if the spawned child's env actually drops
    the vars — verify against a real `env` subprocess, not the helper."""
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "local")
    monkeypatch.setenv("PI_PACKAGE_DIR", "/tmp/fn-pkg-host")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-backend")

    out = b""
    async for event in sprite_service.exec_stream(
        sprite_service.Sprite(name="local"),
        ["env"],
        env={"STAS098_PROBE": "explicit-wins"},
        cwd=sprite_service.SPRITE_WORKDIR,
    ):
        if "data" in event:
            out += event["data"]

    lines = out.decode().splitlines()
    for name in BLOCKED:
        assert not any(line.startswith(f"{name}=") for line in lines), name
    # Explicit env still reaches the child and wins over inheritance.
    assert "STAS098_PROBE=explicit-wins" in lines
