"""Scope gate — manifest presence is the only opt-in signal.

The gate checks for a flat `.stash` file walking up from cwd:
- Repo-level `.stash` in cwd or ancestor → in scope.
- Nothing → out of scope.

Regression test: out-of-scope sessions must short-circuit before any event
reaches the transport.
"""

from __future__ import annotations

from pathlib import Path

from stashai.plugin import scope as scope_mod
from stashai.plugin.event import HookEvent




def test_manifest_in_cwd_is_in_scope(tmp_path):
    (tmp_path / ".stash").write_text('{"workspace_id": "test"}')
    assert scope_mod.cwd_in_scope(str(tmp_path))


def test_manifest_in_ancestor_is_in_scope(tmp_path):
    (tmp_path / ".stash").write_text('{"workspace_id": "test"}')
    sub = tmp_path / "packages" / "foo"
    sub.mkdir(parents=True)
    assert scope_mod.cwd_in_scope(str(sub))


def test_no_manifest_rejected(tmp_path):
    assert not scope_mod.cwd_in_scope(str(tmp_path))


def test_empty_cwd_rejected():
    assert not scope_mod.cwd_in_scope("")
    assert not scope_mod.cwd_in_scope(None)


def test_repo_manifest_wins_over_shallower_one(tmp_path):
    (tmp_path / ".stash").write_text('{"workspace_id": "A"}')

    repo = tmp_path / "projects" / "repo"
    repo.mkdir(parents=True)
    (repo / ".stash").write_text('{"workspace_id": "B"}')

    assert scope_mod.cwd_in_scope(str(repo))
    assert scope_mod.cwd_in_scope(str(tmp_path))


def test_worktree_resolves_to_main_repo_manifest(tmp_path, monkeypatch):
    """A git worktree without its own manifest should find the main repo's manifest."""
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".stash").write_text('{"workspace_id": "W"}')

    worktree = tmp_path / "worktree-checkout"
    worktree.mkdir()

    monkeypatch.setattr(
        scope_mod, "_git_repo_info", lambda cwd: (worktree, main_repo)
    )

    manifest = scope_mod.find_manifest(str(worktree))
    assert manifest is not None
    assert manifest["workspace_id"] == "W"


def test_worktree_manifest_beats_global(tmp_path, monkeypatch):
    """Main repo manifest takes precedence over an ancestor's .stash file."""
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".stash").write_text('{"workspace_id": "company"}')

    (tmp_path / ".stash").write_text('{"workspace_id": "personal"}')

    worktree = tmp_path / "worktrees" / "feature"
    worktree.mkdir(parents=True)

    monkeypatch.setattr(
        scope_mod, "_git_repo_info", lambda cwd: (worktree, main_repo)
    )

    manifest = scope_mod.find_manifest(str(worktree))
    assert manifest is not None
    assert manifest["workspace_id"] == "company"


def test_main_repo_manifest_beats_worktree_local(tmp_path, monkeypatch):
    """Main repo manifest wins even if the worktree has its own."""
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".stash").write_text('{"workspace_id": "main"}')

    worktree = tmp_path / "worktree-checkout"
    worktree.mkdir()
    (worktree / ".stash").write_text('{"workspace_id": "local"}')

    monkeypatch.setattr(
        scope_mod, "_git_repo_info", lambda cwd: (worktree, main_repo)
    )

    manifest = scope_mod.find_manifest(str(worktree))
    assert manifest is not None
    assert manifest["workspace_id"] == "main"



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
    stream_user_message(c, {"workspace_id": "ws1", "tag_name": "a"}, {"session_id": "s"},
                        "hello", HookEvent(kind="prompt", cwd="/other"))
    assert c.calls == []


def test_in_scope_allows_live_events(monkeypatch):
    from stashai.plugin.hooks import stream_user_message
    # Autouse fixture in conftest already patches cwd_in_scope → True.
    c = _RecordingClient()
    stream_user_message(c, {"workspace_id": "ws1", "tag_name": "a"}, {"session_id": "s"},
                        "hello", HookEvent(kind="prompt", cwd="/anywhere"))
    assert len(c.calls) == 1
