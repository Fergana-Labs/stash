"""Claude-plugin-specific config: reads CLAUDE_PLUGIN_USER_CONFIG_* env vars.

Everything agent-agnostic lives in `stashai.plugin`. This module only handles
the Claude-specific env surface + paths, then hands off.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from stashai.plugin.scope import find_manifest
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
    """User-scoped CLI config only. Repo config lives in the `.stash` manifest."""
    user_path = Path.home() / ".stash" / "config.json"
    if user_path.exists():
        return _read_json(user_path)
    return {}


def get_config() -> dict:
    api_key = os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_api_key", "")
    agent_name = os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_agent_name", "")

    if not api_key:
        cli = _load_cli_config()
        manifest = find_manifest(os.getcwd())
        manifest_base = (manifest or {}).get("base_url")
        user_base = cli.get("base_url", PRODUCTION_BASE_URL)
        api_endpoint = manifest_base or user_base
        api_key = cli.get("api_key", "") if api_endpoint == user_base else ""
        return {
            "api_endpoint": api_endpoint,
            "api_key": api_key,
            "agent_name": cli.get("username", ""),
            "workspace_id": (manifest or {}).get("workspace_id", ""),
            "client": "claude_code",
        }

    return {
        "api_endpoint": os.environ.get(
            "CLAUDE_PLUGIN_USER_CONFIG_api_endpoint", PRODUCTION_BASE_URL
        ),
        "api_key": api_key,
        "agent_name": agent_name,
        "workspace_id": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_workspace_id", ""),
        "client": "claude_code",
    }


def get_client() -> StashClient:
    cfg = get_config()
    return StashClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"], data_dir=DATA_DIR)


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["api_key"] and cfg["agent_name"])
