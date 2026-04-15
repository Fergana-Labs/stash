"""Claude-plugin-specific config: reads CLAUDE_PLUGIN_USER_CONFIG_* env vars.

Everything agent-agnostic lives in plugins/shared/. This module only handles
the Claude-specific env surface + paths, then hands off.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add shared/ to sys.path so on_*.py scripts can import it
SHARED = Path(__file__).resolve().parent.parent.parent / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from octopus_client import OctopusClient  # noqa: E402

DATA_DIR = Path(os.environ.get(
    "CLAUDE_PLUGIN_DATA",
    Path.home() / ".claude/plugins/data/octopus",
))


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


def _project_config() -> Path | None:
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


# Keys that ONLY the user-scoped ~/.octopus/config.json is allowed to set.
# A project-scoped .octopus/config.json (walked up from cwd) must not be able
# to override these — otherwise any writable ancestor dir becomes an exfil
# vector (attacker points base_url at their own server, captures every
# prompt + tool output).
_USER_ONLY_KEYS = {"base_url", "api_key"}


def _load_cli_config() -> dict:
    """User config (~/.octopus/config.json) overlaid with project config.

    Project config may override workspace/username scoping, but NOT the
    transport credentials (base_url, api_key).
    """
    merged: dict = {}
    user_path = Path.home() / ".octopus" / "config.json"
    if user_path.exists():
        merged.update(_read_json(user_path))
    project_path = _project_config()
    if project_path:
        project = _read_json(project_path)
        for key in _USER_ONLY_KEYS:
            project.pop(key, None)
        merged.update(project)
    return merged


def get_config() -> dict:
    api_key = os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_api_key", "")
    agent_name = os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_agent_name", "")

    if not api_key:
        cli = _load_cli_config()
        return {
            "api_endpoint": cli.get("base_url", "https://getoctopus.com"),
            "api_key": cli.get("api_key", ""),
            "agent_name": cli.get("username", ""),
            "workspace_id": cli.get("default_workspace", ""),
            "auto_curate": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_auto_curate", "true"),
            "client": "claude_code",
        }

    return {
        "api_endpoint": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_api_endpoint", "https://getoctopus.com"),
        "api_key": api_key,
        "agent_name": agent_name,
        "workspace_id": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_workspace_id", ""),
        "auto_curate": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_auto_curate", "true"),
        "client": "claude_code",
    }


def get_client() -> OctopusClient:
    cfg = get_config()
    return OctopusClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"], data_dir=DATA_DIR)


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["api_key"] and cfg["agent_name"])
