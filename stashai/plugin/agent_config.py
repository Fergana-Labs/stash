"""Shared config helpers for per-agent Stash plugins.

Every CLI-style agent plugin (codex, cursor, gemini, opencode, openclaw)
piggybacks on the user-scoped CLI config in `~/.stash/config.json`. The
per-agent `config.py` modules used to be near-identical copies of this
logic; they now delegate here and only supply the three things that
actually differ between agents: the data-dir env var, the data-dir
default path, and the `client` label sent with each event.

Claude's plugin has its own env-var fast path, so it stays separate.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .scope import find_manifest
from .stash_client import StashClient

PRODUCTION_BASE_URL = "https://api.joinstash.ai"


def data_dir_from_env(env_var: str, default_subpath: str) -> Path:
    return Path(os.environ.get(env_var, Path.home() / default_subpath))


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
    """User-scoped CLI config only. Repo config lives in the `.stash` manifest."""
    user_path = Path.home() / ".stash" / "config.json"
    if user_path.exists():
        return _read_json(user_path)
    return {}


def get_config(client: str) -> dict:
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
        "client": client,
    }


def get_client(client: str, data_dir: Path) -> StashClient:
    cfg = get_config(client)
    return StashClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"], data_dir=data_dir)


def is_configured(client: str) -> bool:
    cfg = get_config(client)
    return bool(cfg["api_key"] and cfg["agent_name"])
