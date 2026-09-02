"""Skill-declared tool servers reach every harness and leave when the skill
does. Why it matters: this is the only path by which a hosted skill's tools
appear on a laptop, and it must never clobber MCP servers the user set up
by hand."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli import skill_mcp

SKILL = """---
name: stylewriter
description: Write in my voice.
mcp: stylewriter https://api.example.test/mcp/stylewriter
---
# body
"""

PLAIN = """---
name: brief
description: No tools here.
---
"""

THIRD_PARTY = """---
name: weather
description: Someone else's server.
mcp: weather https://weather.example/mcp
---
"""


@pytest.fixture
def home(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(skill_mcp, "USER_CONFIG_DIR", tmp_path / ".stash")
    monkeypatch.setattr(
        skill_mcp,
        "load_config",
        lambda: {"api_key": "mc_test_key", "base_url": "https://api.example.test"},
    )
    return tmp_path


def _skills_root(home: Path, *skills: tuple[str, str]) -> Path:
    root = home / ".claude" / "skills"
    for name, markdown in skills:
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / "SKILL.md").write_text(markdown)
    return root


def test_declarations_are_read_and_bad_ones_reported(home):
    root = _skills_root(
        home,
        ("stylewriter", SKILL),
        ("brief", PLAIN),
        ("broken", SKILL.replace("stylewriter https", "not a url")),
    )
    servers, notes = skill_mcp.declared_servers(root)
    assert servers == {"stylewriter": "https://api.example.test/mcp/stylewriter"}
    assert notes and "broken" in notes[0]


def test_every_harness_gets_the_server_with_the_users_key(home):
    root = _skills_root(home, ("stylewriter", SKILL))
    # Pre-existing user config that must survive untouched.
    (home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"mine": {"type": "stdio"}}, "theme": "dark"})
    )
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text('model = "o3"\n')

    notes = skill_mcp.sync(root, ["claude", "codex", "opencode", "gemini", "cursor"])
    assert any("stylewriter" in n for n in notes)

    claude = json.loads((home / ".claude.json").read_text())
    assert claude["theme"] == "dark" and "mine" in claude["mcpServers"]
    entry = claude["mcpServers"]["stylewriter"]
    assert entry["type"] == "http" and entry["headers"]["Authorization"] == "Bearer mc_test_key"

    codex = (home / ".codex" / "config.toml").read_text()
    assert codex.startswith('model = "o3"')
    assert "[mcp_servers.stylewriter]" in codex and "Bearer mc_test_key" in codex

    opencode = json.loads((home / ".config" / "opencode" / "opencode.json").read_text())
    assert opencode["mcp"]["stylewriter"]["type"] == "remote"
    gemini = json.loads((home / ".gemini" / "settings.json").read_text())
    assert gemini["mcpServers"]["stylewriter"]["httpUrl"].endswith("/mcp/stylewriter")
    cursor = json.loads((home / ".cursor" / "mcp.json").read_text())
    assert cursor["mcpServers"]["stylewriter"]["url"].endswith("/mcp/stylewriter")


def test_the_key_never_goes_to_another_host(home):
    root = _skills_root(home, ("stylewriter", SKILL), ("weather", THIRD_PARTY))
    skill_mcp.sync(root, ["claude", "codex"])
    claude = json.loads((home / ".claude.json").read_text())
    assert "headers" not in claude["mcpServers"]["weather"]
    assert claude["mcpServers"]["stylewriter"]["headers"]["Authorization"] == "Bearer mc_test_key"
    codex = (home / ".codex" / "config.toml").read_text()
    weather_block = codex.split("[mcp_servers.weather]", 1)[1].split("[mcp_servers", 1)[0]
    assert "mc_test_key" not in weather_block


def test_removing_the_skill_removes_only_our_entries(home):
    root = _skills_root(home, ("stylewriter", SKILL))
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"mine": {"type": "stdio"}}}))
    skill_mcp.sync(root, ["claude", "codex"])
    codex_before = (home / ".codex" / "config.toml").read_text()
    assert "[mcp_servers.stylewriter]" in codex_before

    # Same skill again: the codex block is replaced, not duplicated.
    skill_mcp.sync(root, ["claude", "codex"])
    assert (home / ".codex" / "config.toml").read_text().count("[mcp_servers.stylewriter]") == 1

    (root / "stylewriter" / "SKILL.md").unlink()
    (root / "stylewriter").rmdir()
    notes = skill_mcp.sync(root, ["claude", "codex"])
    assert any("removed" in n for n in notes)
    claude = json.loads((home / ".claude.json").read_text())
    assert claude["mcpServers"] == {"mine": {"type": "stdio"}}
    assert "mcp_servers.stylewriter" not in (home / ".codex" / "config.toml").read_text()


def test_nothing_declared_touches_nothing(home):
    root = _skills_root(home, ("brief", PLAIN))
    assert skill_mcp.sync(root, ["claude"]) == []
    assert not (home / ".claude.json").exists()


def test_signed_out_fails_loud(home, monkeypatch):
    root = _skills_root(home, ("stylewriter", SKILL))
    monkeypatch.setattr(
        skill_mcp, "load_config", lambda: {"api_key": "", "base_url": "https://api.example.test"}
    )
    with pytest.raises(RuntimeError, match="signin"):
        skill_mcp.sync(root, ["claude"])
