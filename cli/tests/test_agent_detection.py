from pathlib import Path

from cli.main import _agent_present


def test_codex_detects_existing_session_history_without_binary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    (tmp_path / ".codex" / "sessions").mkdir(parents=True)

    assert _agent_present("codex")
