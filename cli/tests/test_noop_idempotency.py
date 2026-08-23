"""Idempotent no-op exit-0 contract for mutating commands (STAS-081).

Re-running a mutating command on an already-done state must exit 0 and report
the no-op clearly: a human "already …" message on stderr, and in --json mode
exactly one stable document {"ok": true, "changed": false} on stdout. A
genuinely-changed run emits {"ok": true, "changed": true}. Genuine errors
(403/5xx) still fail loud with the AXI-classified exit code and never report
"ok": true.

Covers the five audited commands: `rm`, `restore`, `connect`, `disconnect`,
`skills follow` (plus the symmetric `skills unfollow` no-op path).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import main
from cli.client import StashError
from cli.config import MANIFEST_FILE

runner = CliRunner()

# The stable no-op/change document the audited commands emit in --json mode.
NOOP = {"ok": True, "changed": False}
CHANGED = {"ok": True, "changed": True}


@pytest.fixture(autouse=True)
def _reset_json_mode():
    # Each Typer invocation is a fresh CLI process in production, so the
    # module-level JSON-mode flag starts False. Reset it per test so in-process
    # CliRunner invocations do not leak state across tests.
    main._JSON_MODE = False
    yield
    main._JSON_MODE = False


class _MutationClient:
    """Fake client whose mutation methods raise the configured status per ref.

    `outcomes` maps "method:ref" to a status code to raise as StashError;
    anything not listed succeeds. Mirrors cli/tests/test_sharing_cli.py's
    monkeypatched-fake-client pattern."""

    def __init__(self, outcomes: dict[str, int] | None = None):
        self.outcomes = outcomes or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _mutate(self, method: str, ref: str) -> None:
        status = self.outcomes.get(f"{method}:{ref}")
        if status is not None:
            detail = "not found" if status == 404 else f"server error {status}"
            raise StashError(status, detail)

    def delete_page(self, i):
        self._mutate("delete_page", i)

    def purge_page(self, i):
        self._mutate("purge_page", i)

    def delete_file(self, i):
        self._mutate("delete_file", i)

    def purge_file(self, i):
        self._mutate("purge_file", i)

    def delete_session(self, i):
        self._mutate("delete_session", i)

    def purge_session(self, i):
        self._mutate("purge_session", i)

    def restore_page(self, i):
        self._mutate("restore_page", i)

    def restore_file(self, i):
        self._mutate("restore_file", i)

    def restore_session(self, i):
        self._mutate("restore_session", i)


def _setup_mutation(monkeypatch, client) -> None:
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: client)
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


def _setup_connect(monkeypatch, tmp_path: Path, streaming_calls: list) -> None:
    """Point connect/disconnect at `tmp_path` as a git-free folder (connect
    works outside a git repo) and record start/stop_streaming calls so tests
    can assert the streaming side-effect is unchanged."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "load_config", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: None)
    monkeypatch.setattr(main, "start_streaming", lambda: streaming_calls.append("start"))
    monkeypatch.setattr(main, "stop_streaming", lambda: streaming_calls.append("stop"))
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# stash rm — a 404 is the idempotent end state, not an error
# ---------------------------------------------------------------------------


def test_rm_already_trashed_is_noop_exit_zero_json(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"delete_page:page-1": 404}))
    result = runner.invoke(main.app, ["rm", "page:page-1", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "already in trash" in result.stderr


def test_rm_already_trashed_noop_default_mode_reports_stderr(monkeypatch):
    """Without --json the no-op is still reported, on stderr, with clean stdout."""
    _setup_mutation(monkeypatch, _MutationClient({"delete_page:page-1": 404}))
    result = runner.invoke(main.app, ["rm", "page:page-1"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "already in trash" in result.stderr


def test_rm_global_json_position_noop(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"delete_page:page-1": 404}))
    result = runner.invoke(main.app, ["--json", "rm", "page:page-1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "already in trash" in result.stderr


def test_rm_changed_first_run_reports_changed_true(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient())
    result = runner.invoke(main.app, ["rm", "page:page-1", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    assert "item(s) moved to trash" in result.stderr


def test_rm_mixed_batch_reports_changed_true(monkeypatch):
    """One already-done item + one real change: still exit 0, changed:true."""
    client = _MutationClient({"delete_page:gone": 404})
    _setup_mutation(monkeypatch, client)
    result = runner.invoke(main.app, ["rm", "page:gone", "file:file-1", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    assert "already in trash" in result.stderr
    assert "item(s) moved to trash" in result.stderr


def test_rm_permanent_404_is_noop(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"delete_page:page-1": 404}))
    result = runner.invoke(main.app, ["rm", "page:page-1", "--permanent", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "already permanently deleted" in result.stderr


def test_rm_permanent_purge_404_is_noop(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"purge_page:page-1": 404}))
    result = runner.invoke(main.app, ["rm", "page:page-1", "--permanent", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP


def test_rm_403_fails_loud_and_never_reports_ok(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"delete_page:page-1": 403}))
    result = runner.invoke(main.app, ["rm", "page:page-1", "--json"])
    assert result.exit_code == 1
    assert "ok" not in result.stdout
    assert "Error [403]" in result.stderr


def test_rm_500_exits_internal_error(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"delete_page:page-1": 500}))
    result = runner.invoke(main.app, ["rm", "page:page-1", "--json"])
    assert result.exit_code == 2
    assert "ok" not in result.stdout
    assert "Error [500]" in result.stderr


def test_rm_without_refs_is_user_error_not_noop(monkeypatch):
    """A missing argument is still a usage error — never a no-op success."""
    _setup_mutation(monkeypatch, _MutationClient())
    result = runner.invoke(main.app, ["rm"])
    assert result.exit_code != 0
    assert "ok" not in result.stdout


# ---------------------------------------------------------------------------
# stash restore — a 404 means already restored: the idempotent end state
# ---------------------------------------------------------------------------


def test_restore_already_restored_is_noop_exit_zero_json(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"restore_page:page-1": 404}))
    result = runner.invoke(main.app, ["restore", "page:page-1", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "already restored" in result.stderr


def test_restore_already_restored_noop_default_mode_reports_stderr(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"restore_page:page-1": 404}))
    result = runner.invoke(main.app, ["restore", "page:page-1"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "already restored" in result.stderr


def test_restore_global_json_position_noop(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"restore_page:page-1": 404}))
    result = runner.invoke(main.app, ["--json", "restore", "page:page-1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "already restored" in result.stderr


def test_restore_changed_first_run_reports_changed_true(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient())
    result = runner.invoke(main.app, ["restore", "page:page-1", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    assert "item(s) restored" in result.stderr


def test_restore_mixed_batch_reports_changed_true(monkeypatch):
    client = _MutationClient({"restore_page:done": 404})
    _setup_mutation(monkeypatch, client)
    result = runner.invoke(main.app, ["restore", "page:done", "file:file-1", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    assert "already restored" in result.stderr


def test_restore_403_fails_loud_and_never_reports_ok(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"restore_page:page-1": 403}))
    result = runner.invoke(main.app, ["restore", "page:page-1", "--json"])
    assert result.exit_code == 1
    assert "ok" not in result.stdout
    assert "Error [403]" in result.stderr


def test_restore_500_exits_internal_error(monkeypatch):
    _setup_mutation(monkeypatch, _MutationClient({"restore_page:page-1": 500}))
    result = runner.invoke(main.app, ["restore", "page:page-1", "--json"])
    assert result.exit_code == 2
    assert "ok" not in result.stdout
    assert "Error [500]" in result.stderr


# ---------------------------------------------------------------------------
# stash connect / disconnect — manifest already present/absent is a no-op
# ---------------------------------------------------------------------------


def test_connect_already_connected_is_noop_exit_zero_json(monkeypatch, tmp_path):
    streaming: list = []
    _setup_connect(monkeypatch, tmp_path, streaming)
    (tmp_path / MANIFEST_FILE).write_text('{"sentinel": true}\n')
    before = (tmp_path / MANIFEST_FILE).read_text()

    result = runner.invoke(main.app, ["connect", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "Already connected" in result.stderr
    # The no-op must not re-write the manifest, and streaming still starts
    # (connect's streaming side-effect is unchanged by the no-op contract).
    assert (tmp_path / MANIFEST_FILE).read_text() == before
    assert "start" in streaming


def test_connect_already_connected_noop_default_mode_reports_stderr(monkeypatch, tmp_path):
    streaming: list = []
    _setup_connect(monkeypatch, tmp_path, streaming)
    (tmp_path / MANIFEST_FILE).write_text("{}\n")

    result = runner.invoke(main.app, ["connect"])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert "Already connected" in result.stderr
    assert "start" in streaming


def test_connect_global_json_position_noop(monkeypatch, tmp_path):
    _setup_connect(monkeypatch, tmp_path, [])
    (tmp_path / MANIFEST_FILE).write_text("{}\n")

    result = runner.invoke(main.app, ["--json", "connect"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "Already connected" in result.stderr


def test_connect_first_run_reports_changed_true_and_writes_files(monkeypatch, tmp_path):
    streaming: list = []
    _setup_connect(monkeypatch, tmp_path, streaming)
    assert not (tmp_path / MANIFEST_FILE).exists()

    result = runner.invoke(main.app, ["connect", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    assert (tmp_path / MANIFEST_FILE).is_file()
    assert (tmp_path / "CLAUDE.md").is_file()
    assert "start" in streaming


def test_disconnect_not_connected_is_noop_exit_zero_json(monkeypatch, tmp_path):
    _setup_connect(monkeypatch, tmp_path, [])
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: tmp_path)
    assert not (tmp_path / MANIFEST_FILE).exists()

    result = runner.invoke(main.app, ["disconnect", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "Not connected" in result.stderr


def test_disconnect_not_connected_noop_default_mode_reports_stderr(monkeypatch, tmp_path):
    _setup_connect(monkeypatch, tmp_path, [])
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: tmp_path)

    result = runner.invoke(main.app, ["disconnect"])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert "Not connected" in result.stderr


def test_disconnect_global_json_position_noop(monkeypatch, tmp_path):
    _setup_connect(monkeypatch, tmp_path, [])
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: tmp_path)

    result = runner.invoke(main.app, ["--json", "disconnect"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "Not connected" in result.stderr


def test_disconnect_with_manifest_reports_changed_true_and_removes_it(monkeypatch, tmp_path):
    _setup_connect(monkeypatch, tmp_path, [])
    monkeypatch.setattr(main, "_git_toplevel", lambda *a: tmp_path)
    (tmp_path / MANIFEST_FILE).write_text("{}\n")

    result = runner.invoke(main.app, ["disconnect", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    assert not (tmp_path / MANIFEST_FILE).exists()


def test_disconnect_outside_git_repo_is_user_error_not_noop(monkeypatch, tmp_path):
    _setup_connect(monkeypatch, tmp_path, [])  # _git_toplevel already returns None

    result = runner.invoke(main.app, ["disconnect"])

    assert result.exit_code == 1
    assert "ok" not in result.stdout
    assert "Not inside a git repo" in result.stderr


# ---------------------------------------------------------------------------
# stash skills follow / unfollow — the stored follow flag is the truth
# ---------------------------------------------------------------------------


def _seed_installed_manifest(monkeypatch, tmp_path: Path, root: Path, follow: bool | None):
    """Point the installed-manifest at `tmp_path` and seed `root`'s entry.

    follow=None leaves the root absent from the manifest entirely."""
    man_path = tmp_path / "installed_skills.json"
    manifest = {}
    if follow is not None:
        manifest[str(root.resolve())] = {"skills": {}, "follow_shared": follow}
    man_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(main, "_installed_manifest_path", lambda: man_path)
    return man_path


def test_skills_follow_already_following_is_noop_exit_zero_json(monkeypatch, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    man_path = _seed_installed_manifest(monkeypatch, tmp_path, root, follow=True)
    before = man_path.read_text()

    result = runner.invoke(main.app, ["skills", "follow", "--dir", str(root), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "Already following" in result.stderr
    # No-op must not re-write the manifest (bytes unchanged).
    assert man_path.read_text() == before


def test_skills_follow_already_following_noop_default_mode_reports_stderr(monkeypatch, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    _seed_installed_manifest(monkeypatch, tmp_path, root, follow=True)

    result = runner.invoke(main.app, ["skills", "follow", "--dir", str(root)])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert "Already following" in result.stderr


def test_skills_follow_global_json_position_noop(monkeypatch, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    _seed_installed_manifest(monkeypatch, tmp_path, root, follow=True)

    result = runner.invoke(main.app, ["--json", "skills", "follow", "--dir", str(root)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "Already following" in result.stderr


def test_skills_follow_first_run_reports_changed_true_and_sets_flag(monkeypatch, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    man_path = _seed_installed_manifest(monkeypatch, tmp_path, root, follow=False)

    result = runner.invoke(main.app, ["skills", "follow", "--dir", str(root), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    assert "Following" in result.stderr
    manifest = json.loads(man_path.read_text())
    assert manifest[str(root.resolve())]["follow_shared"] is True


def test_skills_follow_missing_entry_reports_changed_true(monkeypatch, tmp_path):
    """A root with no installed-manifest entry has never followed: first run
    is a real change, not a no-op."""
    root = tmp_path / "skills"
    root.mkdir()
    man_path = _seed_installed_manifest(monkeypatch, tmp_path, root, follow=None)

    result = runner.invoke(main.app, ["skills", "follow", "--dir", str(root), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    manifest = json.loads(man_path.read_text())
    assert manifest[str(root.resolve())]["follow_shared"] is True


def test_skills_unfollow_already_not_following_is_noop(monkeypatch, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    man_path = _seed_installed_manifest(monkeypatch, tmp_path, root, follow=False)
    before = man_path.read_text()

    result = runner.invoke(main.app, ["skills", "unfollow", "--dir", str(root), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == NOOP
    assert "Not following" in result.stderr
    assert man_path.read_text() == before


def test_skills_unfollow_following_reports_changed_true_and_clears_flag(monkeypatch, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    man_path = _seed_installed_manifest(monkeypatch, tmp_path, root, follow=True)

    result = runner.invoke(main.app, ["skills", "unfollow", "--dir", str(root), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == CHANGED
    manifest = json.loads(man_path.read_text())
    assert manifest[str(root.resolve())]["follow_shared"] is False
