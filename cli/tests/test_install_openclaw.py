"""Tests for `_install_openclaw` — extension install via the openclaw CLI.

The installer shells out to `openclaw plugins install --force <assets>`, so
these tests stub subprocess.run and assert the skip/installed/failed
contract around it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cli.main import _assets_dir, _install_openclaw


def _patch_home(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path / ".openclaw" / "extensions" / "stash"


def test_install_runs_openclaw_cli(monkeypatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    status, detail = _install_openclaw(False)

    assert status == "installed"
    assert "openclaw gateway restart" in detail
    assert calls == [
        [
            "openclaw",
            "plugins",
            "install",
            "--force",
            "--dangerously-force-unsafe-install",
            str(_assets_dir("openclaw")),
        ]
    ]


def test_up_to_date_extension_is_skipped_without_running_cli(monkeypatch, tmp_path: Path) -> None:
    ext_dir = _patch_home(monkeypatch, tmp_path)
    shutil.copytree(
        _assets_dir("openclaw"),
        ext_dir,
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    def fail_run(cmd, **kwargs):
        raise AssertionError("openclaw CLI must not run when extension is current")

    monkeypatch.setattr(subprocess, "run", fail_run)

    status, _ = _install_openclaw(False)

    assert status == "skipped"


def test_stale_extension_is_reinstalled(monkeypatch, tmp_path: Path) -> None:
    ext_dir = _patch_home(monkeypatch, tmp_path)
    shutil.copytree(
        _assets_dir("openclaw"),
        ext_dir,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (ext_dir / "index.ts").write_text("// old version")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    status, _ = _install_openclaw(False)

    assert status == "installed"
    assert len(calls) == 1


def test_failed_cli_surfaces_error_tail(monkeypatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="boom\nplugin rejected by gateway"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    status, detail = _install_openclaw(False)

    assert status == "failed"
    assert detail == "plugin rejected by gateway"
