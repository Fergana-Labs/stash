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

from stashai.plugin import scope as scope_mod
from stashai.plugin.event import HookEvent




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


def test_worktree_resolves_to_main_repo_manifest(tmp_path, monkeypatch):
    """A git worktree without its own manifest should find the main repo's manifest."""
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".stash").mkdir()
    (main_repo / ".stash" / "stash.json").write_text('{"version": 1, "workspace_id": "W"}')

    worktree = tmp_path / "worktree-checkout"
    worktree.mkdir()

    monkeypatch.setattr(
        scope_mod, "_git_repo_info", lambda cwd: (worktree, main_repo)
    )

    manifest = scope_mod.find_manifest(str(worktree))
    assert manifest is not None
    assert manifest["workspace_id"] == "W"


def test_worktree_manifest_beats_global(tmp_path, monkeypatch):
    """Main repo manifest takes precedence over a global ~/.stash/ manifest."""
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".stash").mkdir()
    (main_repo / ".stash" / "stash.json").write_text('{"version": 1, "workspace_id": "company"}')

    # Simulate a global manifest in an ancestor of the worktree
    global_stash = tmp_path / ".stash"
    global_stash.mkdir()
    (global_stash / "stash.json").write_text('{"version": 1, "workspace_id": "personal"}')

    worktree = tmp_path / "worktrees" / "feature"
    worktree.mkdir(parents=True)

    monkeypatch.setattr(
        scope_mod, "_git_repo_info", lambda cwd: (worktree, main_repo)
    )

    manifest = scope_mod.find_manifest(str(worktree))
    assert manifest is not None
    assert manifest["workspace_id"] == "company"


def test_worktree_local_manifest_beats_main_repo(tmp_path, monkeypatch):
    """A manifest inside the worktree itself is more specific than the main repo's."""
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".stash").mkdir()
    (main_repo / ".stash" / "stash.json").write_text('{"version": 1, "workspace_id": "main"}')

    worktree = tmp_path / "worktree-checkout"
    worktree.mkdir()
    (worktree / ".stash").mkdir()
    (worktree / ".stash" / "stash.json").write_text('{"version": 1, "workspace_id": "local"}')

    monkeypatch.setattr(
        scope_mod, "_git_repo_info", lambda cwd: (worktree, main_repo)
    )

    manifest = scope_mod.find_manifest(str(worktree))
    assert manifest is not None
    assert manifest["workspace_id"] == "local"


def test_worktree_disabled_checks_main_repo(tmp_path, monkeypatch):
    """repo_stash_disabled should check the main worktree root."""
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".stash").mkdir()
    (main_repo / ".stash" / "config.json").write_text('{"stash_disabled_here": true}')

    worktree = tmp_path / "worktree-checkout"
    worktree.mkdir()

    monkeypatch.setattr(
        scope_mod, "_git_repo_info", lambda cwd: (worktree, main_repo)
    )

    assert scope_mod.repo_stash_disabled(str(worktree))


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
