"""Claude-plugin-specific config: reads CLAUDE_PLUGIN_USER_CONFIG_* env vars.

Everything agent-agnostic lives in `stashai.plugin`. This module only handles
the Claude-specific env surface + paths, then hands off.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from stashai.plugin.stash_client import StashClient

DATA_DIR = Path(
    os.environ.get(
        "CLAUDE_PLUGIN_DATA",
        Path.home() / ".claude/plugins/data/stash",
    )
)

PRODUCTION_BASE_URL = "https://api.joinstash.ai"


def get_stdin_data() -> dict:
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _load_cli_config() -> dict:
    """User-scoped CLI config (`~/.stash/config.json`)."""
    user_path = Path.home() / ".stash" / "config.json"
    if user_path.exists():
        return _read_json(user_path)
    return {}


def get_config() -> dict:
    api_key = os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_api_key", "")
    agent_name = os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_agent_name", "")

    if not api_key:
        cli = _load_cli_config()
        return {
            "api_endpoint": cli.get("base_url", PRODUCTION_BASE_URL),
            "api_key": cli.get("api_key", ""),
            "agent_name": cli.get("username", ""),
            "session_folder_id": cli.get("session_folder_id", ""),
            "stopped_streaming": bool(cli.get("stopped_streaming")),
            "session_link": bool(cli.get("session_link")),
            "client": "claude_code",
        }

    return {
        "api_endpoint": os.environ.get(
            "CLAUDE_PLUGIN_USER_CONFIG_api_endpoint", PRODUCTION_BASE_URL
        ),
        "api_key": api_key,
        "agent_name": agent_name,
        "session_folder_id": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_session_folder_id", ""),
        "stopped_streaming": bool(os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_stopped_streaming")),
        "session_link": bool(os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_session_link")),
        "client": "claude_code",
    }


def get_client() -> StashClient:
    cfg = get_config()
    return StashClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"], data_dir=DATA_DIR)


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["api_key"] and cfg["agent_name"])
