"""Auth credential and config storage for the stash CLI.

Config lives at user scope: ~/.stash/config.json (applies everywhere).
Per-repo settings live in .stash (a single file at the repo root, committed).
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
    # The session folder this repo's agent sessions are pushed into. Omitted →
    # they land in the user's Default folder.
    session_folder_id: str
    base_url: str


DEFAULT_CONFIG = {
    "base_url": PRODUCTION_BASE_URL,
    "api_key": "",
    "username": "",
}


def find_project_manifest(start: Path | None = None) -> Path | None:
    """Walk up from cwd looking for a .stash file at a repo root."""
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


def write_manifest(updates: Manifest, start: Path | None = None) -> Manifest:
    path = find_project_manifest(start)
    if not path:
        raise FileNotFoundError(MANIFEST_FILE)
    data = load_manifest(start) or {}
    for key, value in updates.items():
        if value:
            data[key] = value
        elif key in data:
            del data[key]
    path.write_text(json.dumps(data, indent=2) + "\n")
    return data


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
        _migrate_legacy_scope(cfg)

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


def _migrate_legacy_scope(cfg: dict) -> None:
    """One-shot migration: pre-2026-07 CLIs stored a mode string ("repo") under
    `scope`; today the key is a workspace scope_user_id UUID sent as
    X-Stash-Scope, and the backend hard-400s non-UUIDs — which would break
    every request on machines carrying the old value. Non-UUID values are
    deleted from the file once; after that there is only the UUID format."""
    from uuid import UUID

    raw = cfg.get("scope")
    if not raw:
        return
    try:
        UUID(str(raw))
    except ValueError:
        cfg.pop("scope", None)
        data = _read_json(USER_CONFIG_FILE)
        if data.pop("scope", None) is not None:
            USER_CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")


def save_scope(scope: str | None) -> None:
    """Set the active workspace scope, or clear it (None) for personal.

    Read by both the CLI client and the plugin's StashClient, so every write —
    live events, transcripts, artifacts — lands in the same scope."""
    existing = _read_json(USER_CONFIG_FILE) if USER_CONFIG_FILE.exists() else {}
    if scope:
        existing["scope"] = scope
    else:
        existing.pop("scope", None)
    USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_FILE.write_text(json.dumps(existing, indent=2) + "\n")


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
#
# Streaming is global to the user's scope: a single boolean the plugin reads as
# `not stopped_streaming` (stashai/plugin/scope.py). There is no per-repo scope.


def streaming_stopped() -> bool:
    if USER_CONFIG_FILE.exists():
        return bool(_read_json(USER_CONFIG_FILE).get("stopped_streaming"))
    return False


def start_streaming() -> None:
    _write_to(USER_CONFIG_FILE, {"stopped_streaming": False})


def stop_streaming() -> None:
    _write_to(USER_CONFIG_FILE, {"stopped_streaming": True})


# --- Session-link toggle ---
#
# When on, the Claude plugin instructs the agent to append the session record
# link to every response. Independent of upload streaming, and off unless the
# user turns it on.


def session_link_enabled() -> bool:
    if USER_CONFIG_FILE.exists():
        return bool(_read_json(USER_CONFIG_FILE).get("session_link"))
    return False


def set_session_link(enabled: bool) -> None:
    _write_to(USER_CONFIG_FILE, {"session_link": enabled})
