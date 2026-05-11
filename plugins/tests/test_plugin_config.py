from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATHS = [
    ROOT / "plugins/claude-plugin/scripts/config.py",
    ROOT / "plugins/codex-plugin/scripts/config.py",
    ROOT / "plugins/cursor-plugin/scripts/config.py",
    ROOT / "plugins/gemini-plugin/scripts/config.py",
    ROOT / "plugins/openclaw-plugin/scripts/config.py",
    ROOT / "plugins/opencode-plugin/scripts/config.py",
    ROOT / "stashai/plugin/assets/codex/scripts/config.py",
    ROOT / "stashai/plugin/assets/cursor/scripts/config.py",
    ROOT / "stashai/plugin/assets/opencode/scripts/config.py",
]


def _load_config(path: Path):
    spec = importlib.util.spec_from_file_location(
        f"config_{path.parent.parent.name}_{path.parent.name}", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clear_claude_env(monkeypatch):
    for key in (
        "CLAUDE_PLUGIN_USER_CONFIG_api_key",
        "CLAUDE_PLUGIN_USER_CONFIG_agent_name",
        "CLAUDE_PLUGIN_USER_CONFIG_api_endpoint",
        "CLAUDE_PLUGIN_USER_CONFIG_workspace_id",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("config_path", CONFIG_PATHS, ids=lambda p: str(p.relative_to(ROOT)))
def test_plugin_config_uses_dot_stash_manifest_base_url(config_path, tmp_path, monkeypatch):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    home_config = home / ".stash" / "config.json"
    home_config.parent.mkdir(parents=True)
    home_config.write_text(
        json.dumps(
            {
                "base_url": "https://user.example",
                "api_key": "user-key",
                "username": "alice-agent",
            }
        )
    )
    repo.mkdir()
    (repo / ".stash").write_text(
        json.dumps(
            {
                "workspace_id": "ws-manifest",
                "base_url": "https://repo.example",
            }
        )
    )

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(repo)

    cfg = _load_config(config_path).get_config()

    assert cfg["api_endpoint"] == "https://repo.example"
    assert cfg["api_key"] == ""
    assert cfg["agent_name"] == "alice-agent"
    assert cfg["workspace_id"] == "ws-manifest"


@pytest.mark.parametrize("config_path", CONFIG_PATHS, ids=lambda p: str(p.relative_to(ROOT)))
def test_plugin_config_ignores_project_dot_stash_config_json(config_path, tmp_path, monkeypatch):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    home_config = home / ".stash" / "config.json"
    home_config.parent.mkdir(parents=True)
    home_config.write_text(
        json.dumps(
            {
                "base_url": "https://user.example",
                "api_key": "user-key",
                "username": "alice-agent",
            }
        )
    )
    project_config = repo / ".stash" / "config.json"
    project_config.parent.mkdir(parents=True)
    project_config.write_text(
        json.dumps(
            {
                "workspace_id": "ws-wrong",
                "base_url": "https://wrong.example",
                "api_key": "wrong-key",
                "username": "wrong-agent",
            }
        )
    )

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(repo)

    cfg = _load_config(config_path).get_config()

    assert cfg["api_endpoint"] == "https://user.example"
    assert cfg["api_key"] == "user-key"
    assert cfg["agent_name"] == "alice-agent"
    assert cfg["workspace_id"] == ""
