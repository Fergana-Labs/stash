"""Gemini CLI plugin config. Reads from ~/.stash/config.json (CLI config)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parent.parent.parent / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from stash_client import StashClient  # noqa: E402

DATA_DIR = Path(os.environ.get(
    "STASH_GEMINI_DATA",
    Path.home() / ".stash/plugins/gemini",
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
    try:
        cur = Path.cwd().resolve()
    except Exception:
        return None
    for parent in [cur, *cur.parents]:
        candidate = parent / ".stash" / "config.json"
        if candidate.exists():
            return candidate
    return None


# base_url + api_key are user-only to prevent a .stash/config.json in any
# writable ancestor dir from hijacking the transport endpoint.
_USER_ONLY_KEYS = {"base_url", "api_key"}


def _cli_config() -> dict:
    """User config (~/.stash/config.json) overlaid with project config.

    Project config may not override base_url / api_key.
    """
    merged: dict = {}
    user_path = Path.home() / ".stash" / "config.json"
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
    cli = _cli_config()
    return {
        "api_endpoint": cli.get("base_url", "https://stash.ac"),
        "api_key": cli.get("api_key", ""),
        "agent_name": cli.get("username", ""),
        "workspace_id": cli.get("default_workspace", ""),
        "auto_curate": os.environ.get("STASH_AUTO_CURATE", "false"),
        "client": "gemini_cli",
    }


def get_client() -> StashClient:
    cfg = get_config()
    return StashClient(base_url=cfg["api_endpoint"], api_key=cfg["api_key"], data_dir=DATA_DIR)


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["api_key"] and cfg["agent_name"])
