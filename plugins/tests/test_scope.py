"""Scope gate — the shape that actually matters: worktree match, sibling
reject, scope=all bypass. Plus the regression test: scope=repo must block
live events when cwd is out of scope (and scope=all must preserve old
behavior if a user opts out)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(SHARED))

import scope as scope_mod  # noqa: E402
from event import HookEvent  # noqa: E402


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


@pytest.fixture(autouse=True)
def _clear_cache():
    scope_mod._common_dir.cache_clear()


def test_worktree_shares_install_scope(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    _init_repo(main)
    (main / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(main), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(main), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "init"],
        check=True, capture_output=True,
    )
    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", "--detach", str(wt)],
        check=True, capture_output=True,
    )
    install = scope_mod._common_dir(str(main))
    assert scope_mod.cwd_in_scope(str(wt), {"scope": "repo", "install_repo_common_dir": install})


def test_sibling_repo_rejected(tmp_path):
    main = tmp_path / "main"
    sib = tmp_path / "sib"
    main.mkdir(); sib.mkdir()
    _init_repo(main); _init_repo(sib)
    install = scope_mod._common_dir(str(main))
    assert not scope_mod.cwd_in_scope(str(sib), {"scope": "repo", "install_repo_common_dir": install})


def test_scope_all_bypasses_check(tmp_path):
    outside = tmp_path / "notrepo"
    outside.mkdir()
    assert scope_mod.cwd_in_scope(str(outside), {"scope": "all", "install_repo_common_dir": ""})


# --- Regression: the gate must short-circuit live events -------------------

class _RecordingClient:
    def __init__(self):
        self.calls = []

    def push_event(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


def test_scope_repo_blocks_live_events_out_of_scope(monkeypatch):
    from hooks import stream_user_message
    import hooks, scope as s
    monkeypatch.setattr(s, "cwd_in_scope", lambda cwd, cfg: False)
    monkeypatch.setattr(hooks, "cwd_in_scope", lambda cwd, cfg: False)

    c = _RecordingClient()
    stream_user_message(c, {"workspace_id": "ws1", "agent_name": "a"}, {"session_id": "s"},
                        "hello", HookEvent(kind="prompt", cwd="/other"))
    assert c.calls == []


def test_scope_all_preserves_old_behavior(monkeypatch):
    from hooks import stream_user_message
    c = _RecordingClient()
    # Autouse fixture in conftest already patches cwd_in_scope → True.
    stream_user_message(c, {"workspace_id": "ws1", "agent_name": "a"}, {"session_id": "s"},
                        "hello", HookEvent(kind="prompt", cwd="/anywhere"))
    assert len(c.calls) == 1
