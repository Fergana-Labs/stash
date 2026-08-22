from pathlib import Path

import pytest

from cli import main
from cli.main import _agent_present


def test_codex_detects_existing_session_history_without_binary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    (tmp_path / ".codex" / "sessions").mkdir(parents=True)

    assert _agent_present("codex")


def test_codex_detects_existing_config_without_binary_or_session_history(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("[features]\n")

    assert _agent_present("codex")


def test_codex_detects_macos_desktop_app_without_binary_or_session_history(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(main.sys, "platform", "darwin")

    (tmp_path / "Library" / "Application Support" / "Codex").mkdir(parents=True)

    assert _agent_present("codex")


# --- Claude Code: detection must not hinge on PATH ---
#
# Claude Code is the flagship agent, and `shutil.which("claude")` misses real
# installs — the local/migrate install hides the binary behind a shell alias,
# and ~/.local/bin reaches PATH only via a shell rc. When detection missed it
# the user lost *both* live recording and their history import (the import is
# scoped to the detected agents), which is exactly what happened on a customer
# call: the picker offered Cursor — detected from a stray ~/.cursor — while the
# agent they actually used went unseen.


def test_claude_detected_from_its_folder_without_binary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    (tmp_path / ".claude" / "projects").mkdir(parents=True)

    assert _agent_present("claude")


def test_claude_detected_from_alias_style_local_install(monkeypatch, tmp_path: Path) -> None:
    # ~/.claude/local/claude + a shell alias: never on PATH, still a real install.
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    local = tmp_path / ".claude" / "local"
    local.mkdir(parents=True)
    binary = local / "claude"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)

    assert main._claude_binary() == str(binary)
    assert _agent_present("claude")


def test_claude_absent_when_nothing_on_the_machine(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert not _agent_present("claude")


def test_undetected_claude_would_strand_its_history_import(monkeypatch, tmp_path: Path) -> None:
    """The import is scoped to detected agents, so missing Claude silently
    strands every transcript on disk — the failure that cost a customer their
    whole first impression."""
    from cli import import_history

    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # The discoverer freezes this path at import time, so patching home alone
    # would read the developer's own transcripts.
    monkeypatch.setattr(import_history, "CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects")

    proj = tmp_path / ".claude" / "projects" / "-Users-someone-repo"
    proj.mkdir(parents=True)
    proj.joinpath("s1.jsonl").write_text(
        '{"type":"summary","summary":"work"}\n'
        '{"type":"user","timestamp":"2026-08-07T12:00:00Z","cwd":"/Users/someone/repo",'
        '"sessionId":"s1","message":{"role":"user","content":"hi"}}\n'
    )

    detected = main._detected_agents()
    assert detected == ["claude"]
    found = import_history.discover_conversations(detected)
    assert [(c.agent, c.session_id) for c in found] == [("claude", "s1")]


def test_finder_cancel_is_told_apart_from_a_real_failure(monkeypatch, tmp_path: Path) -> None:
    """osascript echoes the offending path into stderr, so matching "-128"
    anywhere in the message turns a genuine failure under a folder like
    ~/work/PROJ-128 into a fake Cancel — and a fake Cancel aborts setup with no
    message and no recorded_paths written. Only the trailing code means Cancel."""
    import subprocess

    def run_with(returncode: int, stderr: str):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(a[0], returncode, "", stderr),
        )
        return main._choose_folder_finder(tmp_path)

    assert run_with(1, "execution error: User canceled. (-128)") is None

    with pytest.raises(RuntimeError):
        run_with(1, 'execution error: Can\'t make file "HD:work:PROJ-128" into type file. (-1700)')

    # Exit 0 with no folder is an anomaly, not a silent "never mind".
    with pytest.raises(RuntimeError):
        run_with(0, "")


def test_claude_plugin_freshen_uses_the_resolved_binary(monkeypatch, tmp_path: Path) -> None:
    """The whole point of resolving the binary is the install that parks claude
    outside PATH; a bare "claude" in any one call fails for exactly that user."""
    import subprocess

    binary = str(tmp_path / ".claude" / "local" / "claude")
    monkeypatch.setattr(main, "_claude_binary", lambda: binary)
    monkeypatch.setattr(main, "_enable_marketplace_autoupdate", lambda _p: True)

    argv0: list[str] = []

    def fake_run(cmd, *a, **k):
        argv0.append(cmd[0])
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    main._install_claude_plugin()

    assert argv0, "expected the installer to shell out"
    assert set(argv0) == {binary}, f"a call still used a bare binary name: {argv0}"


def test_agent_folder_candidates_never_offer_a_relative_path(monkeypatch, tmp_path: Path) -> None:
    """Cursor reports an encoded slug, not a path. A relative entry written into
    recorded_paths resolves against each session's own cwd, matches nothing, and
    the scope gate then reads that as "record nothing" — recording silently off."""
    from cli import import_history

    real = tmp_path / "repo"
    real.mkdir()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Users-someone-projects-stash").mkdir()

    class Conv:
        def __init__(self, cwd):
            self.cwd = cwd

    monkeypatch.setattr(
        main,
        "_agent_folder_candidates",
        main._agent_folder_candidates,
    )
    monkeypatch.setattr(
        import_history,
        "discover_conversations",
        lambda *a, **k: [Conv("Users-someone-projects-stash")] * 5 + [Conv(str(real))],
    )

    candidates = main._agent_folder_candidates()

    assert [str(p) for p, _ in candidates] == [str(real)]
    assert all(p.is_absolute() for p, _ in candidates)


# --- Pi: binary on PATH or the ~/.pi config dir ---


def test_pi_detects_config_dir_without_binary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    (tmp_path / ".pi").mkdir(parents=True)

    assert _agent_present("pi")


def test_pi_not_detected_without_binary_or_config_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert not _agent_present("pi")


def test_pi_detected_via_binary_without_config_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: _cmd == "pi")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert _agent_present("pi")


def test_pi_not_detected_when_other_binary_present(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: _cmd == "claude")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert not _agent_present("pi")
