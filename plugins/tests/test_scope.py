"""Scope gate — manifest presence is the only opt-in signal.

The gate checks for `.stash/stash.json` walking up from cwd:
- Repo-level manifest in cwd or ancestor → in scope.
- Global manifest at `~/.stash/stash.json` → in scope (implicitly covered
  by the walk-up if `$HOME` is above cwd; the mechanism is the same).
- Nothing → out of scope.

Regression test: out-of-scope sessions must short-circuit before any event
reaches the transport.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stashai.plugin import scope as scope_mod
from stashai.plugin.event import HookEvent


@pytest.fixture(autouse=True)
def _clear_cache():
    scope_mod.cwd_in_scope.cache_clear()
    scope_mod.repo_stash_disabled.cache_clear()


def test_manifest_in_cwd_is_in_scope(tmp_path):
    (tmp_path / ".stash").mkdir()
    (tmp_path / ".stash" / "stash.json").write_text('{"version": 1}')
    assert scope_mod.cwd_in_scope(str(tmp_path))


def test_manifest_in_ancestor_is_in_scope(tmp_path):
    (tmp_path / ".stash").mkdir()
    (tmp_path / ".stash" / "stash.json").write_text('{"version": 1}')
    sub = tmp_path / "packages" / "foo"
    sub.mkdir(parents=True)
    assert scope_mod.cwd_in_scope(str(sub))


def test_no_manifest_rejected(tmp_path):
    assert not scope_mod.cwd_in_scope(str(tmp_path))


def test_empty_cwd_rejected():
    assert not scope_mod.cwd_in_scope("")
    assert not scope_mod.cwd_in_scope(None)


def test_repo_manifest_wins_over_shallower_one(tmp_path):
    # A repo-level manifest under an ancestor with its own manifest should
    # still be in scope — the walk-up finds the nearest first.
    (tmp_path / ".stash").mkdir()
    (tmp_path / ".stash" / "stash.json").write_text('{"version": 1, "workspace_id": "A"}')

    repo = tmp_path / "projects" / "repo"
    (repo / ".stash").mkdir(parents=True)
    (repo / ".stash" / "stash.json").write_text('{"version": 1, "workspace_id": "B"}')

    # Both cwds resolve to in-scope; routing (which workspace) is read by the
    # plugin separately via get_config(), not the scope gate.
    assert scope_mod.cwd_in_scope(str(repo))
    assert scope_mod.cwd_in_scope(str(tmp_path))


def test_repo_stash_disabled_marker(tmp_path):
    (tmp_path / ".stash").mkdir()
    (tmp_path / ".stash" / "config.json").write_text('{"stash_disabled_here": true}')
    assert scope_mod.repo_stash_disabled(str(tmp_path))


def test_repo_stash_disabled_missing_file(tmp_path):
    assert not scope_mod.repo_stash_disabled(str(tmp_path))


# --- Regression: the gate must short-circuit live events -------------------

class _RecordingClient:
    def __init__(self):
        self.calls = []

    def push_event(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


def test_out_of_scope_blocks_live_events(monkeypatch):
    from stashai.plugin import hooks, scope as s
    from stashai.plugin.hooks import stream_user_message
    monkeypatch.setattr(s, "cwd_in_scope", lambda cwd: False)
    monkeypatch.setattr(hooks, "cwd_in_scope", lambda cwd: False)

    c = _RecordingClient()
    stream_user_message(c, {"workspace_id": "ws1", "agent_name": "a"}, {"session_id": "s"},
                        "hello", HookEvent(kind="prompt", cwd="/other"))
    assert c.calls == []


def test_in_scope_allows_live_events(monkeypatch):
    from stashai.plugin.hooks import stream_user_message
    # Autouse fixture in conftest already patches cwd_in_scope → True.
    c = _RecordingClient()
    stream_user_message(c, {"workspace_id": "ws1", "agent_name": "a"}, {"session_id": "s"},
                        "hello", HookEvent(kind="prompt", cwd="/anywhere"))
    assert len(c.calls) == 1
