"""Tests for `stash tools install`'s .mcp.json merge.

The merge must be idempotent and must never touch user-added servers: stash
ownership is tracked by name in the stashManagedServers marker list, so a
user entry that shares a name is a conflict, never a clobber.
"""

from __future__ import annotations

import json
from pathlib import Path

from cli.main import STASH_MANAGED_MCP_KEY, _mcp_json_entry, _merge_mcp_server

STDIO_ENTRY = {"type": "stdio", "command": "npx", "args": ["-y", "linear-mcp"]}
HTTP_ENTRY = {"type": "http", "url": "https://mcp.notion.com/mcp"}


def test_install_creates_mcp_json_when_missing(tmp_path: Path) -> None:
    dest = tmp_path / ".mcp.json"

    status = _merge_mcp_server(dest, "linear", STDIO_ENTRY)

    assert status == "installed"
    config = json.loads(dest.read_text())
    assert config["mcpServers"]["linear"] == STDIO_ENTRY
    assert config[STASH_MANAGED_MCP_KEY] == ["linear"]


def test_install_preserves_user_entries(tmp_path: Path) -> None:
    dest = tmp_path / ".mcp.json"
    user_entry = {"command": "my-own-server"}
    dest.write_text(json.dumps({"mcpServers": {"mine": user_entry}}))

    status = _merge_mcp_server(dest, "notion", HTTP_ENTRY)

    assert status == "installed"
    config = json.loads(dest.read_text())
    assert config["mcpServers"]["mine"] == user_entry
    assert config["mcpServers"]["notion"] == HTTP_ENTRY
    assert config[STASH_MANAGED_MCP_KEY] == ["notion"]


def test_install_refuses_to_clobber_a_user_entry_with_the_same_name(tmp_path: Path) -> None:
    dest = tmp_path / ".mcp.json"
    user_entry = {"command": "user-owned-linear"}
    dest.write_text(json.dumps({"mcpServers": {"linear": user_entry}}))

    status = _merge_mcp_server(dest, "linear", STDIO_ENTRY)

    assert status == "conflict"
    assert json.loads(dest.read_text())["mcpServers"]["linear"] == user_entry


def test_install_is_idempotent(tmp_path: Path) -> None:
    dest = tmp_path / ".mcp.json"

    assert _merge_mcp_server(dest, "linear", STDIO_ENTRY) == "installed"
    before = dest.read_text()
    assert _merge_mcp_server(dest, "linear", STDIO_ENTRY) == "skipped"
    assert dest.read_text() == before


def test_install_replaces_a_stash_managed_entry_whose_config_changed(tmp_path: Path) -> None:
    dest = tmp_path / ".mcp.json"
    _merge_mcp_server(dest, "linear", STDIO_ENTRY)

    updated = {"type": "stdio", "command": "npx", "args": ["-y", "linear-mcp@2"]}
    status = _merge_mcp_server(dest, "linear", updated)

    assert status == "installed"
    config = json.loads(dest.read_text())
    assert config["mcpServers"]["linear"] == updated
    assert config[STASH_MANAGED_MCP_KEY] == ["linear"]


def test_install_fails_on_invalid_json(tmp_path: Path) -> None:
    dest = tmp_path / ".mcp.json"
    dest.write_text("{not json")

    assert _merge_mcp_server(dest, "linear", STDIO_ENTRY) == "failed"


def test_entry_builder_splits_stdio_commands_and_carries_secrets() -> None:
    stdio = _mcp_json_entry(
        {
            "transport": "stdio",
            "command": "npx -y linear-mcp",
            "env": {"LINEAR_API_KEY": "lin_x"},
        }
    )
    assert stdio == {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "linear-mcp"],
        "env": {"LINEAR_API_KEY": "lin_x"},
    }

    http = _mcp_json_entry(
        {
            "transport": "http",
            "url": "https://mcp.notion.com/mcp",
            "headers": {"Authorization": "Bearer tok"},
        }
    )
    assert http == {
        "type": "http",
        "url": "https://mcp.notion.com/mcp",
        "headers": {"Authorization": "Bearer tok"},
    }
