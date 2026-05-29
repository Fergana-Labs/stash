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
