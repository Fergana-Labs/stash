"""Plugin configuration and persistent state."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PLUGIN_DATA = Path(os.environ.get("CLAUDE_PLUGIN_DATA", Path.home() / ".claude/plugins/data/octopus"))
STATE_FILE = PLUGIN_DATA / "state.json"


def get_stdin_data() -> dict:
    """Read JSON from stdin (Claude Code hook protocol)."""
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _find_project_config() -> Path | None:
    """Walk up from cwd looking for .octopus/config.json."""
    try:
        cur = Path.cwd().resolve()
    except Exception:
        return None
    for parent in [cur, *cur.parents]:
        candidate = parent / ".octopus" / "config.json"
        if candidate.exists():
            return candidate
    return None


def _load_cli_config() -> dict:
    """Load CLI config. Project-level (.octopus/config.json walking up from cwd)
    overrides user-level (~/.octopus/config.json)."""
    merged: dict = {}
    user_path = Path.home() / ".octopus" / "config.json"
    if user_path.exists():
        merged.update(_read_json(user_path))
    project_path = _find_project_config()
    if project_path:
        merged.update(_read_json(project_path))
    return merged


def get_config() -> dict:
    """Read plugin userConfig from environment variables, falling back to CLI config."""
    api_key = os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_api_key", "")
    agent_name = os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_agent_name", "")

    # If env vars aren't set, fall back to CLI config (~/.octopus/config.json)
    if not api_key:
        cli = _load_cli_config()
        return {
            "api_endpoint": cli.get("base_url", "https://getoctopus.com"),
            "api_key": cli.get("api_key", ""),
            "agent_name": cli.get("username", ""),
            "workspace_id": cli.get("default_workspace", ""),
            "auto_curate": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_auto_curate", "true"),
        }

    return {
        "api_endpoint": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_api_endpoint", "https://getoctopus.com"),
        "api_key": api_key,
        "agent_name": agent_name,
        "workspace_id": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_workspace_id", ""),
        "auto_curate": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_auto_curate", "true"),
    }


def get_client():
    """Build a OctopusClient from plugin config."""
    # Import here to keep this module lightweight for scripts that don't need the client
    from octopus_client import OctopusClient
    cfg = get_config()
    return OctopusClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"])


def is_configured() -> bool:
    """Check if the minimum config is set (api_key + agent_name)."""
    cfg = get_config()
    return bool(cfg["api_key"] and cfg["agent_name"])


# --- State (persistent across sessions) ---

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"streaming_enabled": True, "session_id": ""}


def save_state(state: dict):
    PLUGIN_DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
