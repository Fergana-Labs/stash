"""Central config + curate spawn gating tests.

The shared `state.py` helpers read `auto_curate`, `streaming_enabled`, and
`last_curate_at` from `~/.octopus/config.json` so every installed plugin
shares one toggle surface. These tests patch `CENTRAL_CONFIG_PATH` to a
tempdir and verify the read/write/gating logic.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(SHARED))


@pytest.fixture()
def central(tmp_path, monkeypatch):
    """Point CENTRAL_CONFIG_PATH at a tempfile for the duration of the test."""
    import state as state_mod

    path = tmp_path / "config.json"
    monkeypatch.setattr(state_mod, "CENTRAL_CONFIG_PATH", path)
    return state_mod, path


def test_auto_curate_defaults_true_when_unset(central):
    state_mod, _ = central
    assert state_mod.auto_curate_enabled() is True


def test_auto_curate_toggle_round_trip(central):
    state_mod, path = central
    state_mod.set_auto_curate(False)
    assert state_mod.auto_curate_enabled() is False
    assert '"auto_curate": false' in path.read_text()
    state_mod.set_auto_curate(True)
    assert state_mod.auto_curate_enabled() is True


def test_streaming_enabled_overlayed_into_load_state(central, tmp_path):
    state_mod, _ = central
    data_dir = tmp_path / "plugin-data"
    state_mod.save_state(data_dir, {"streaming_enabled": True, "session_id": "x"})

    state_mod.set_streaming_enabled(False)
    loaded = state_mod.load_state(data_dir)
    assert loaded["streaming_enabled"] is False
    assert loaded["session_id"] == "x"


def test_curate_cooldown_blocks_within_window(central):
    state_mod, _ = central
    assert state_mod.curate_cooldown_active() is False
    state_mod.record_curate_run()
    assert state_mod.curate_cooldown_active() is True


def test_curate_cooldown_expires(central, monkeypatch):
    state_mod, _ = central
    state_mod.record_curate_run()
    future = time.time() + state_mod.CURATE_COOLDOWN_SECONDS + 1
    monkeypatch.setattr(state_mod.time, "time", lambda: future)
    assert state_mod.curate_cooldown_active() is False


def _fake_popen_calls(monkeypatch):
    import curate_spawn

    calls = []

    class FakePopen:
        def __init__(self, argv, **kwargs):
            calls.append((argv, kwargs))
            self.argv = argv
            self.pid = 1234

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(curate_spawn.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(curate_spawn.shutil, "which", lambda name: f"/usr/bin/{name}")
    return curate_spawn, calls


def test_spawn_curation_fires_binary_with_sleep_prompt(central, monkeypatch):
    curate_spawn, calls = _fake_popen_calls(monkeypatch)
    monkeypatch.delenv("OCTOPUS_SKIP_AUTO_CURATE", raising=False)
    from sleep_prompt import SLEEP_PROMPT

    for binary, flags in [
        ("claude", ["-p"]),
        ("codex", ["exec"]),
        ("cursor-agent", ["-p"]),
        ("gemini", ["-p"]),
        ("opencode", ["run"]),
    ]:
        # Clear cooldown before each spawn.
        central[0].CENTRAL_CONFIG_PATH.unlink(missing_ok=True)
        assert curate_spawn.spawn_curation(binary, flags) is True

    assert [argv[0] for argv, _ in calls] == [
        "/usr/bin/claude",
        "/usr/bin/codex",
        "/usr/bin/cursor-agent",
        "/usr/bin/gemini",
        "/usr/bin/opencode",
    ]
    # Flags preserved in order, prompt appended last.
    for argv, _ in calls:
        assert argv[-1] == SLEEP_PROMPT


def test_spawn_curation_respects_recursion_guard(central, monkeypatch):
    curate_spawn, calls = _fake_popen_calls(monkeypatch)
    monkeypatch.setenv("OCTOPUS_SKIP_AUTO_CURATE", "1")
    assert curate_spawn.spawn_curation("claude", ["-p"]) is False
    assert calls == []


def test_spawn_curation_respects_cooldown(central, monkeypatch):
    curate_spawn, calls = _fake_popen_calls(monkeypatch)
    monkeypatch.delenv("OCTOPUS_SKIP_AUTO_CURATE", raising=False)
    central[0].record_curate_run()
    assert curate_spawn.spawn_curation("claude", ["-p"]) is False
    assert calls == []


def test_spawn_curation_respects_auto_curate_flag(central, monkeypatch):
    curate_spawn, calls = _fake_popen_calls(monkeypatch)
    monkeypatch.delenv("OCTOPUS_SKIP_AUTO_CURATE", raising=False)
    central[0].set_auto_curate(False)
    assert curate_spawn.spawn_curation("claude", ["-p"]) is False
    assert calls == []


def test_spawn_curation_sets_recursion_guard_env(central, monkeypatch):
    curate_spawn, calls = _fake_popen_calls(monkeypatch)
    monkeypatch.delenv("OCTOPUS_SKIP_AUTO_CURATE", raising=False)
    assert curate_spawn.spawn_curation("claude", ["-p"]) is True
    _, kwargs = calls[-1]
    assert kwargs["env"]["OCTOPUS_SKIP_AUTO_CURATE"] == "1"
