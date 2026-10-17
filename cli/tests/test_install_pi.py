"""Tests for the Pi hook installer (`_install_pi`).

Pi's hooks are native executable files that each exec ``../_run.sh <handler>`` —
the ``on_*.py`` name ``_run.sh`` resolves (e.g. user_message -> on_prompt).
``_run.sh`` resolves its handler from its own dir via ``TARGET=$SCRIPT_DIR/$SCRIPT.py``.
So `_install_pi` copies the whole shipped ``scripts/`` tree onto ``~/.pi/``
byte-for-byte (never symlinking to the repo), so the install works even after the
checkout or tool venv moves, and the shipped-assets path never leaks into the
installed files.
"""

from __future__ import annotations

import inspect
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import (
    _HOOK_EVENTS,
    _INSTALLERS,
    _install_all_hooks,
    _install_pi,
    _plugin_installed,
    app,
)

# event name in the hook wrapper -> handler script it execs via _run.sh
HOOK_EVENTS = {
    "session_start": "on_session_start",
    "user_message": "on_prompt",
    "tool_use": "on_tool_use",
    "session_end": "on_session_end",
    "assistant_message": "on_stop",
}

REPO_ROOT = Path(__file__).resolve().parents[2]

# The two shipped pi script trees (source plugin + the packaged mirror that
# _install_pi copies). Both must satisfy the same wrapper->handler contract.
SHIPPED_SCRIPT_TREES = [
    REPO_ROOT / "plugins/pi-plugin/scripts",
    REPO_ROOT / "stashai/plugin/assets/pi/scripts",
]

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

runner = CliRunner()


def _hook_wrapper(event: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        f'exec "$SCRIPT_DIR/../_run.sh" {HOOK_EVENTS[event]} "$@"\n'
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
    assert sorted(p.name for p in hooks_dir.iterdir()) == sorted(HOOK_EVENTS)

    for event in HOOK_EVENTS:
        hook = hooks_dir / event
        assert os.stat(hook).st_mode & stat.S_IXUSR, f"{event} must be executable"
        assert not hook.is_symlink(), f"{event} must be a real copy, not a symlink"
        body = hook.read_text()
        assert body.startswith("#!/usr/bin/env bash")
        assert f'exec "$SCRIPT_DIR/../_run.sh" {HOOK_EVENTS[event]} "$@"' in body

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


@pytest.mark.parametrize(
    "scripts_dir", SHIPPED_SCRIPT_TREES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_shipped_wrappers_exec_handlers_that_resolve(scripts_dir: Path) -> None:
    """Read the REAL shipped payload and prove every hook wrapper execs
    ``_run.sh`` with a handler name whose ``.py`` actually ships beside
    ``_run.sh``.

    ``_run.sh`` resolves ``TARGET=$SCRIPT_DIR/$SCRIPT.py`` from its first
    argument, so a wrapper that passes the pi *event* name (``user_message``)
    instead of the handler (``on_prompt``) dies on every pi event with exit 2
    (``can't open file .../user_message.py: No such file or directory``) —
    a permanently dead install that the fixture-driven tests above cannot see.
    This guard reads both payload trees independently so a wrapper edit to the
    event name turns CI red instead of shipping it.
    """
    assert 'TARGET="$SCRIPT_DIR/$SCRIPT.py"' in (scripts_dir / "_run.sh").read_text()

    hooks_dir = scripts_dir / "hooks"
    assert sorted(p.name for p in hooks_dir.iterdir()) == sorted(HOOK_EVENTS)

    for event, handler in HOOK_EVENTS.items():
        body = (hooks_dir / event).read_text()
        assert f'exec "$SCRIPT_DIR/../_run.sh" {handler} "$@"' in body, (
            f"{scripts_dir.relative_to(REPO_ROOT)}/hooks/{event} must exec "
            f"_run.sh {handler} (the name _run.sh resolves), got: {body!r}"
        )
        assert (scripts_dir / f"{handler}.py").is_file(), (
            f"{handler}.py must ship next to _run.sh for {event}'s wrapper to resolve"
        )


def test_shipped_pi_runtime_carries_no_self_upgrade() -> None:
    """`spawn_self_upgrade()` in the session_start handler is the one background
    upgrade path, and pi reaches it like every other agent does. A second
    `uv tool install` from the shell runner would race it against the venv it is
    about to exec, so the runner and handlers must stay free of it.
    """
    for scripts_dir in SHIPPED_SCRIPT_TREES:
        for path in sorted(scripts_dir.rglob("*")):
            if path.is_file():
                assert "uv tool install" not in path.read_text(errors="replace"), (
                    f"{path.relative_to(REPO_ROOT)} runs its own upgrade; "
                    "stashai.plugin.session_upload.spawn_self_upgrade is the only one"
                )


def test_installed_tree_matches_shipped_assets_bytes(monkeypatch, tmp_path: Path) -> None:
    """Run the install path against the REAL shipped assets, not a fixture tree:
    every installed file must equal its shipped bytes and keep its shipped mode,
    because pi only executes files it finds on disk under ``~/.pi/`` and a lost
    exec bit there is a hook that never runs."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert _install_pi(False)[0] == "installed"

    root = REPO_ROOT / "stashai" / "plugin" / "assets" / "pi" / "scripts"
    shipped = {p.relative_to(root): p for p in root.rglob("*") if p.is_file()}
    assert shipped, "the shipped pi scripts tree must not be empty"

    installed_dir = home / ".pi"
    installed = {
        rel: path
        for rel, path in (
            (p.relative_to(installed_dir), p) for p in installed_dir.rglob("*") if p.is_file()
        )
        if rel.as_posix() != "AGENTS.md"
    }
    assert set(installed) == set(shipped)

    for rel, source in shipped.items():
        target = installed[rel]
        assert target.read_bytes() == source.read_bytes(), f"{rel} differs from shipped bytes"
        target_mode = os.stat(target).st_mode & 0o777
        source_mode = os.stat(source).st_mode & 0o777
        assert target_mode == source_mode, (
            f"{rel}: installed {target_mode:o} != shipped {source_mode:o}"
        )


def test_every_installer_accepts_the_call_site_positional_args() -> None:
    """The setup path calls ``_INSTALLERS[agent](False)`` with one positional arg
    (see ``_install_all_hooks``), and its ``except Exception`` swallows any
    mismatch into a "failed" status line instead of crashing. A signature drift
    would therefore leave the suite green while shipping an install that never
    lands. Bind the call site's arity against every registered installer.
    """
    for agent, installer in _INSTALLERS.items():
        inspect.signature(installer).bind(False)


def test_setup_path_installs_pi(pi_home: Path, monkeypatch, capsys) -> None:
    """Exercise the real setup call site (``_install_all_hooks``), not just
    ``_install_pi`` directly: the installer must land its runtime on disk when
    invoked the way the wizard invokes it. A TypeError swallowed inside that loop
    leaves ``~/.pi/`` empty and prints "failed", so this test fails on exactly the
    failure mode that would otherwise look like a green suite with a broken install.
    """
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)
    monkeypatch.setattr("cli.main._detected_agents", lambda: ["pi"])

    _install_all_hooks(["pi"])

    assert "✓ Pi hook installed" in capsys.readouterr().out
    pi = pi_home / ".pi"
    assert (pi / "_run.sh").is_file()
    assert sorted(p.name for p in (pi / "hooks").iterdir()) == sorted(HOOK_EVENTS)
    assert (pi / "on_prompt.py").is_file()
    assert (pi / "AGENTS.md").is_file()
    assert _plugin_installed("pi") is True


def test_a_dead_deployed_generation_upgrades_without_force(pi_home: Path, monkeypatch) -> None:
    """A ``~/.pi`` whose handler imports a name the installed package no longer
    exports dies at import time — and pi ignores a hook that fails, so nothing
    ever tells the user their telemetry stopped. The install path is the only
    thing allowed to replace a deployed generation, so installing must overwrite a
    dead handler, a stale wrapper, and a stale guidance block in one pass, with no
    ``--force`` and no fallback that keeps the old copy running.
    """
    assets = _make_assets(pi_home)
    monkeypatch.setattr("cli.main._assets_dir", lambda agent: assets)

    pi = pi_home / ".pi"
    (pi / "hooks").mkdir(parents=True)
    dead_handler = pi / "on_session_start.py"
    dead_handler.write_text("from stashai.plugin.hooks import session_start_legacy\n")
    stale_wrapper = pi / "hooks" / "session_start"
    stale_wrapper.write_text("#!/usr/bin/env bash\necho I am the old generation\n")
    (pi / "AGENTS.md").write_text(
        "# my own rules\n\n"
        "<!-- stash-plugin:begin -->\nOld frozen guidance.\n<!-- stash-plugin:end -->\n"
        "\nkeep me\n"
    )

    status, _ = _install_pi(False)

    assert status == "installed"
    assert dead_handler.read_text() == "# on_session_start.py\n"
    assert _hook_wrapper("session_start") in stale_wrapper.read_text()
    assert os.stat(stale_wrapper).st_mode & stat.S_IXUSR, "wrapper lost its exec bit"

    guidance = (pi / "AGENTS.md").read_text()
    assert "Old frozen guidance." not in guidance
    assert "stash CLI is on PATH." in guidance
    assert "# my own rules" in guidance and "keep me" in guidance
    assert guidance.count("stash-plugin:begin") == 1


def test_pi_keeps_its_own_generation_and_is_never_dispatched() -> None:
    """The canonical-shape decision, locked so the rejected alternative cannot be
    reintroduced by accident.

    CHOSEN: pi owns its own shipped generation — ``_install_pi`` returns before the
    dispatcher's table lookup and ``_copy_pi_runtime`` copies the whole tree into
    ``~/.pi/``, so pi's generation is replaced only by the installer, never by a
    shared code path.

    REJECTED: give pi a ``"pi"`` row in ``_HOOK_EVENTS`` and have the five native
    hook wrappers call ``stash hook run pi <event>``. Measured against it:

      1. It would delete the only copy of pi's generation a running hook can reach.
         Pi reads executables from ``~/.pi/hooks/``; routing through the CLI means a
         stale or broken installed CLI silently stops pi's telemetry with nothing
         left on disk to fall back to.
      2. It would move pi's runtime off the two files ``_plugin_installed("pi")``
         probes (``~/.pi/hooks/`` plus ``~/.pi/_run.sh``) — the only signal the CLI
         has that pi is installed at all — and nothing would replace them: no
         agent's hooks are compared event-by-event anywhere in the CLI, so a dead pi
         would still report itself healthy.
      3. It buys pi nothing the payload does not already have: ``_run.sh`` already
         resolves the interpreter whose venv can import ``stashai``, which is the
         only reason ``stash hook run`` exists for the other agents.

    So the dispatcher stays table-only and pi stays out of the table. If this test
    fails because someone added the row, the decision to revisit it belongs in a new
    task with the costs above answered, not in a one-line table edit.
    """
    assert "pi" not in _HOOK_EVENTS, (
        "`_HOOK_EVENTS` gained a pi row: pi's hooks are native ~/.pi/hooks/ executables "
        "and must keep their own shipped generation (see "
        "test_pi_keeps_its_own_generation_and_is_never_dispatched for the rejected "
        "alternative and its measured costs)"
    )

    result = runner.invoke(app, ["hook", "run", "pi", "on_stop"])
    assert result.exit_code == 1
    assert "Unknown hook agent: pi" in result.stderr

    installer_source = inspect.getsource(_install_pi)
    assert "_HOOK_EVENTS" not in installer_source, (
        "_install_pi must land pi's own shipped tree, not a generation derived from the "
        "dispatcher's event table — that table is dispatchable-agent-only"
    )
