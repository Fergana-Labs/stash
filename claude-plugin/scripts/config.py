"""Plugin configuration, state, and cache management."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PLUGIN_DATA = Path(os.environ.get("CLAUDE_PLUGIN_DATA", Path.home() / ".claude/plugins/data/boozle"))
STATE_FILE = PLUGIN_DATA / "state.json"
CACHE_FILE = PLUGIN_DATA / "context_cache.json"
CACHE_TTL = 300  # 5 minutes


def get_stdin_data() -> dict:
    """Read JSON from stdin (Claude Code hook protocol)."""
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def get_config() -> dict:
    """Read plugin userConfig from environment variables."""
    return {
        "api_endpoint": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_api_endpoint", "https://moltchat.onrender.com"),
        "api_key": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_api_key", ""),
        "agent_name": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_agent_name", ""),
        "workspace_id": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_workspace_id", ""),
        "history_store_id": os.environ.get("CLAUDE_PLUGIN_USER_CONFIG_history_store_id", ""),
    }


def get_client():
    """Build a BoozleClient from plugin config."""
    # Import here to keep this module lightweight for scripts that don't need the client
    from boozle_client import BoozleClient
    cfg = get_config()
    return BoozleClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"])


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
    return {"streaming_enabled": True, "persona": "", "session_id": "", "last_sync": None}


def save_state(state: dict):
    PLUGIN_DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# --- Cache (local context to avoid blocking API calls) ---

def load_cache() -> dict | None:
    """Load cached context. Returns None if stale or missing."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
    except Exception:
        return None
    if time.time() - data.get("_timestamp", 0) > CACHE_TTL:
        return None
    return data


def save_cache(profile: dict, recent_events: list):
    """Save context to local cache with timestamp."""
    PLUGIN_DATA.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({
        "_timestamp": time.time(),
        "profile": profile,
        "recent_events": recent_events,
    }, indent=2))
