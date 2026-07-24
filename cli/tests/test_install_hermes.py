"""Tests for `_install_hermes` — marked hooks block in ~/.hermes/config.yaml.

Hermes has no dedicated hooks file: shell hooks live in the shared config.yaml.
The installer owns a marker-comment block so re-runs refresh it in place, and
it must never text-merge into a user-owned top-level `hooks:` key (duplicate
YAML keys are last-one-wins, which silently drops hooks) — that case fails.
"""

from __future__ import annotations

from pathlib import Path

from cli.main import _install_hermes

_HOOK_EVENTS = (
    "on_session_start:",
    "pre_llm_call:",
    "post_tool_call:",
    "post_llm_call:",
    "on_session_end:",
)


def _run_install(monkeypatch, tmp_path: Path) -> tuple[str, str]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return _install_hermes(False)


def test_fresh_install_writes_marked_hooks_block(monkeypatch, tmp_path: Path) -> None:
    status, detail = _run_install(monkeypatch, tmp_path)

    assert status == "installed"
    text = (tmp_path / ".hermes" / "config.yaml").read_text()
    assert "# stash-plugin:begin" in text
    assert "# stash-plugin:end" in text
    for event in _HOOK_EVENTS:
        assert event in text
    # Machine-independent commands: the CLI runs its own shipped scripts, so
    # no absolute install path may leak into the user's config.yaml.
    assert "stash hook run hermes" in text
    assert "stashai/plugin/assets/hermes" not in text
    assert "${PLUGIN_ROOT}" not in text
    # Hooks need one-time user approval inside Hermes — the installer must say so.
    assert "hermes hooks list" in detail


def test_install_preserves_existing_user_config(monkeypatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / ".hermes" / "config.yaml"
    cfg_path.parent.mkdir(parents=True)
    user_config = "model:\n  provider: nous\n  name: Hermes-4-405B\n"
    cfg_path.write_text(user_config)

    status, _ = _run_install(monkeypatch, tmp_path)

    assert status == "installed"
    text = cfg_path.read_text()
    assert text.startswith(user_config)
    assert "# stash-plugin:begin" in text


def test_second_run_is_noop(monkeypatch, tmp_path: Path) -> None:
    _run_install(monkeypatch, tmp_path)
    cfg_path = tmp_path / ".hermes" / "config.yaml"
    before = cfg_path.read_text()

    status, _ = _install_hermes(False)

    assert status == "skipped"
    assert cfg_path.read_text() == before


def test_user_owned_hooks_block_fails_loud(monkeypatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / ".hermes" / "config.yaml"
    cfg_path.parent.mkdir(parents=True)
    user_config = "hooks:\n  pre_tool_call:\n    - command: echo mine\n"
    cfg_path.write_text(user_config)

    status, detail = _run_install(monkeypatch, tmp_path)

    assert status == "failed"
    assert "by hand" in detail
    assert cfg_path.read_text() == user_config
