from pathlib import Path

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
