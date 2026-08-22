"""Tests for the self-contained Pi hook installer (`_install_pi`).

Pi's hooks are native executable files that each exec ``../_run.sh <event>``;
``_run.sh`` resolves its handler from its own dir via ``TARGET=$SCRIPT_DIR/$SCRIPT.py``.
So `_install_pi` copies the whole shipped ``scripts/`` tree onto ``~/.pi/``
byte-for-byte (never symlinking to the repo), so the install works even after the
checkout or pipx env moves, and the shipped-assets path never leaks into the
installed files.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from cli.main import _install_pi, _plugin_installed

# event name in the hook wrapper -> handler script it execs via _run.sh
HOOK_EVENTS = {
    "session_start": "on_session_start",
    "user_message": "on_prompt",
    "tool_use": "on_tool_use",
    "session_end": "on_session_end",
    "assistant_message": "on_stop",
}

RUNTIME_FILES = {
    "_run.sh",
    "config.py",
    "adapt.py",
    "on_session_start.py",
    "on_prompt.py",
    "on_tool_use.py",
    "on_session_end.py",
    "on_stop.py",
}


def _hook_wrapper(event: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        f'exec "$SCRIPT_DIR/../_run.sh" {event} "$@"\n'
    )


@pytest.fixture
def pi_home(monkeypatch, tmp_path: Path) -> Path:
    """Point Path.home() at a scratch dir and serve shipped assets from tmp."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _make_assets(root: Path) -> Path:
    """Materialize a shipping pi assets tree under root and return its assets dir."""
    assets = root / "assets" / "pi"
    scripts = assets / "scripts"
    hooks = scripts / "hooks"
    hooks.mkdir(parents=True)

    scripts.joinpath("_run.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'SCRIPT="$1"; shift\n'
        'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'TARGET="$SCRIPT_DIR/$SCRIPT.py"\n'
        'exec python3 "$TARGET" "$@"\n'
    )
    scripts.joinpath("_run.sh").chmod(0o755)
    for event in HOOK_EVENTS:
        hook = hooks / event
        hook.write_text(_hook_wrapper(event))
        hook.chmod(0o755)
    for name in (
        "config.py",
        "adapt.py",
        "on_session_start.py",
        "on_prompt.py",
        "on_tool_use.py",
        "on_session_end.py",
        "on_stop.py",
    ):
        scripts.joinpath(name).write_text(f"# {name}\n")
    assets.joinpath("AGENTS.md").write_text("# Stash\nstash CLI is on PATH.\n")
    return assets


def test_fresh_install_writes_hooks_and_runtime(pi_home: Path, monkeypatch) -> None:
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)

    status, _ = _install_pi(False)

    assert status == "installed"

    pi = pi_home / ".pi"
    hooks_dir = pi / "hooks"
    assert hooks_dir.is_dir()
    assert sorted(p.name for p in hooks_dir.iterdir()) == sorted(HOOK_EVENTS)

    for event in HOOK_EVENTS:
        hook = hooks_dir / event
        assert os.stat(hook).st_mode & stat.S_IXUSR, f"{event} must be executable"
        assert not hook.is_symlink(), f"{event} must be a real copy, not a symlink"
        body = hook.read_text()
        assert body.startswith("#!/usr/bin/env bash")
        assert f'exec "$SCRIPT_DIR/../_run.sh" {event} "$@"' in body

    run_sh = pi / "_run.sh"
    assert run_sh.is_file()
    assert os.stat(run_sh).st_mode & stat.S_IXUSR
    assert 'TARGET="$SCRIPT_DIR/$SCRIPT.py"' in run_sh.read_text()

    for name in RUNTIME_FILES:
        assert (pi / name).is_file(), f"expected {name} copied to ~/.pi/"

    agents_md = pi / "AGENTS.md"
    assert "stash-plugin:begin" in agents_md.read_text()
    assert "stash-plugin:end" in agents_md.read_text()

    # No absolute shipped-assets path may leak into any installed file.
    assets_path = str(assets)
    for f in list(hooks_dir.iterdir()) + [p for p in pi.iterdir() if p.is_file()]:
        assert assets_path not in f.read_text(errors="replace"), f"{f} leaks assets path"


def test_second_run_is_skipped(pi_home: Path, monkeypatch) -> None:
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)

    pi = pi_home / ".pi"
    _install_pi(False)
    first_bytes = [p.read_bytes() for p in sorted(pi.rglob("*")) if p.is_file()]

    status, _ = _install_pi(False)

    assert status == "skipped"
    second_bytes = [p.read_bytes() for p in sorted(pi.rglob("*")) if p.is_file()]
    assert second_bytes == first_bytes


def test_drifted_hook_rediscovered(pi_home: Path, monkeypatch) -> None:
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)

    pi = pi_home / ".pi"
    _install_pi(False)
    drifted = pi / "hooks" / "session_start"
    drifted.write_bytes(b"#!/usr/bin/env bash\necho I am different\n")

    status, _ = _install_pi(False)

    assert status == "installed"
    assert _hook_wrapper("session_start").encode() in drifted.read_bytes()


def test_force_rewrites_up_to_date(pi_home: Path, monkeypatch) -> None:
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)

    _install_pi(False)
    status, _ = _install_pi(True)

    assert status == "installed"


def test_upsert_agents_md_preserves_user_content(pi_home: Path, monkeypatch) -> None:
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)

    pi = pi_home / ".pi"
    pi.mkdir(parents=True)
    (pi / "AGENTS.md").write_text("my personal notes\n")

    _install_pi(False)
    body = (pi / "AGENTS.md").read_text()
    assert "my personal notes" in body
    assert "stash-plugin:begin" in body

    # Idempotent: a second install leaves a single stash block.
    _install_pi(False)
    body2 = (pi / "AGENTS.md").read_text()
    assert body2.count("stash-plugin:begin") == 1


def test_plugin_installed_true_after_install(pi_home: Path, monkeypatch) -> None:
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)

    assert _plugin_installed("pi") is False
    _install_pi(False)
    assert _plugin_installed("pi") is True


def test_plugin_installed_false_without_runtime(pi_home: Path) -> None:
    # ~/.pi/hooks exists but _run.sh is missing -> not installed.
    (pi_home / ".pi" / "hooks").mkdir(parents=True)
    assert _plugin_installed("pi") is False


def test_replaces_legacy_symlink_with_real_copy(pi_home: Path, monkeypatch) -> None:
    """A hook left behind by an older symlink installer (pointing at the repo)
    is replaced by a self-contained copy, leaving no repo-path dependency."""
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)

    hooks_dir = pi_home / ".pi" / "hooks"
    hooks_dir.mkdir(parents=True)
    virtual_repo = pi_home / "some/old/checkout/stashai/plugin/assets/pi/scripts/hooks"
    virtual_repo.mkdir(parents=True)
    (virtual_repo / "session_start").write_text(_hook_wrapper("session_start"))
    (hooks_dir / "session_start").symlink_to(virtual_repo / "session_start")

    _install_pi(False)

    restored = hooks_dir / "session_start"
    assert not restored.is_symlink()
    assert _hook_wrapper("session_start").encode() in restored.read_bytes()
    # None of the installed files may leak the old checkout/repo path.
    repo_blob = str(virtual_repo)
    assert all(repo_blob not in p.read_text(errors="replace") for p in hooks_dir.iterdir())
