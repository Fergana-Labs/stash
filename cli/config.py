"""Auth credential and config storage for the stash CLI.

Config lives at user scope: ~/.stash/config.json (applies everywhere).
Per-repo workspace info lives in .stash (a single file at the repo root, committed).
"""

import json
import os
from pathlib import Path
from typing import TypedDict

USER_CONFIG_DIR = Path.home() / ".stash"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

MANIFEST_FILE = ".stash"

PRODUCTION_BASE_URL = "https://api.joinstash.ai"


class Manifest(TypedDict, total=False):
    workspace_id: str
    base_url: str


DEFAULT_CONFIG = {
    "base_url": PRODUCTION_BASE_URL,
    "api_key": "",
    "username": "",
}


def find_project_manifest(start: Path | None = None) -> Path | None:
    """Walk up from cwd looking for a .stash file (not directory) at a repo root."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / MANIFEST_FILE
        if candidate.is_file():
            return candidate
    return None


def load_manifest(start: Path | None = None) -> Manifest | None:
    path = find_project_manifest(start)
    if not path:
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def load_config() -> dict:
    """Load config from ~/.stash/config.json. Env vars override."""
    cfg = dict(DEFAULT_CONFIG)

    if USER_CONFIG_FILE.exists():
        cfg.update(_read_json(USER_CONFIG_FILE))

    if url := os.environ.get("STASH_URL"):
        cfg["base_url"] = url
    if key := os.environ.get("STASH_API_KEY"):
        cfg["api_key"] = key
    return cfg


def _write_to(path: Path, updates: dict) -> None:
    existing = _read_json(path) if path.exists() else {}
    for key, val in updates.items():
        if val is not None:
            existing[key] = val
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n")


def save_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    username: str | None = None,
) -> None:
    """Save config to ~/.stash/config.json."""
    updates = {
        "base_url": base_url,
        "api_key": api_key,
        "username": username,
    }
    if any(v is not None for v in updates.values()):
        _write_to(USER_CONFIG_FILE, updates)


def stored_base_url() -> str | None:
    """Return the base_url written to ~/.stash/config.json, or None."""
    if USER_CONFIG_FILE.exists():
        url = _read_json(USER_CONFIG_FILE).get("base_url")
        if url:
            return url
    return None


def load_enabled_agents() -> list[str] | None:
    """Return the enabled_agents list from config, or None if unset (all enabled)."""
    if USER_CONFIG_FILE.exists():
        data = _read_json(USER_CONFIG_FILE)
        agents = data.get("enabled_agents")
        if isinstance(agents, list):
            return agents
    return None


def save_enabled_agents(agents: list[str]) -> None:
    """Persist the enabled agents list to ~/.stash/config.json."""
    _write_to(USER_CONFIG_FILE, {"enabled_agents": agents})


def clear_config() -> None:
    """Remove stored config."""
    if USER_CONFIG_FILE.exists():
        USER_CONFIG_FILE.unlink()


# --- Streaming toggle ---


def _streaming_set() -> set[str]:
    if USER_CONFIG_FILE.exists():
        val = _read_json(USER_CONFIG_FILE).get("streaming")
        if isinstance(val, list):
            return set(val)
    return set()


def is_streaming(workspace_id: str) -> bool:
    return workspace_id in _streaming_set()


def set_streaming(workspace_id: str) -> None:
    ids = _streaming_set()
    ids.add(workspace_id)
    _write_to(USER_CONFIG_FILE, {"streaming": sorted(ids)})


def clear_streaming(workspace_id: str) -> None:
    ids = _streaming_set()
    ids.discard(workspace_id)
    _write_to(USER_CONFIG_FILE, {"streaming": sorted(ids)})


def _hints_shown_set() -> set[str]:
    if USER_CONFIG_FILE.exists():
        val = _read_json(USER_CONFIG_FILE).get("hints_shown")
        if isinstance(val, list):
            return set(val)
    return set()


def is_hint_shown(workspace_id: str) -> bool:
    return workspace_id in _hints_shown_set()


def mark_hint_shown(workspace_id: str) -> None:
    ids = _hints_shown_set()
    ids.add(workspace_id)
    _write_to(USER_CONFIG_FILE, {"hints_shown": sorted(ids)})
