"""opencode plugin config. Reads from ~/.stash/config.json (CLI config)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from stashai.plugin.scope import find_manifest
from stashai.plugin.stash_client import StashClient

DATA_DIR = Path(os.environ.get(
    "STASH_OPENCODE_DATA",
    Path.home() / ".stash/plugins/opencode",
))

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


def _cli_config() -> dict:
    user_path = Path.home() / ".stash" / "config.json"
    if user_path.exists():
        return _read_json(user_path)
    return {}


def get_config() -> dict:
    cli = _cli_config()
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
        "auto_curate": os.environ.get("STASH_AUTO_CURATE", "false"),
        "client": "opencode",
    }


def get_client() -> StashClient:
    cfg = get_config()
    return StashClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"], data_dir=DATA_DIR)


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["api_key"] and cfg["agent_name"])
