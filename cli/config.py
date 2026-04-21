"""Auth credential and config storage for the stash CLI.

Config lives in two scopes:
- user:    ~/.stash/config.json  (applies everywhere)
- project: <repo>/.stash/config.json  (overrides user-level when present)

Project lookup walks up from cwd. Project values override user values.
Auth (api_key, username) and base_url are always stored at user scope —
they're per-machine, not per-repo. This ensures `stash history` works
from any directory.
"""

import json
import os
from pathlib import Path
from typing import Literal, TypedDict

USER_CONFIG_DIR = Path.home() / ".stash"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

PROJECT_DIRNAME = ".stash"
PROJECT_FILENAME = "config.json"
MANIFEST_FILENAME = "stash.json"

Scope = Literal["user", "project"]


class Manifest(TypedDict, total=False):
    version: int
    workspace_id: str
    workspace_name: str
    invite_code: str
    base_url: str
    streaming_default: bool
    require_approval: bool

DEFAULT_CONFIG = {
    "base_url": "http://localhost:3456",
    "api_key": "",
    "username": "",
    "default_workspace": "",
    "default_chat": "",
    "output_format": "human",
    "notify_rooms": [],
}

# Keys that are always user-scoped regardless of requested scope.
# base_url lives here so `stash history` works from any directory.
USER_SCOPED_KEYS = {"api_key", "username", "base_url"}


def find_project_config(start: Path | None = None) -> Path | None:
    """Walk up from cwd looking for .stash/config.json. Return path or None."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / PROJECT_DIRNAME / PROJECT_FILENAME
        if candidate.exists():
            return candidate
    return None


def find_project_manifest(start: Path | None = None) -> Path | None:
    """Walk up from cwd looking for .stash/stash.json (the committed team manifest)."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / PROJECT_DIRNAME / MANIFEST_FILENAME
        if candidate.exists():
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
    """Load config. Project-level overrides user-level. Env vars override both."""
    cfg = dict(DEFAULT_CONFIG)

    if USER_CONFIG_FILE.exists():
        cfg.update(_read_json(USER_CONFIG_FILE))

    project_path = find_project_config()
    if project_path:
        cfg.update(_read_json(project_path))

    if url := os.environ.get("STASH_URL"):
        cfg["base_url"] = url
    if key := os.environ.get("STASH_API_KEY"):
        cfg["api_key"] = key
    return cfg


def _path_for_scope(scope: Scope) -> Path:
    if scope == "user":
        return USER_CONFIG_FILE
    existing = find_project_config()
    if existing:
        return existing
    # No project config yet. If a manifest exists, colocate the per-user
    # config next to it so hook lookups (which walk up from cwd) find it
    # even when `stash connect` was run from a subdirectory.
    manifest = find_project_manifest()
    if manifest:
        return manifest.parent / PROJECT_FILENAME
    return Path.cwd() / PROJECT_DIRNAME / PROJECT_FILENAME


def _write_to(path: Path, updates: dict) -> None:
    existing = _read_json(path) if path.exists() else {}
    for key, val in updates.items():
        if val is not None:
            existing[key] = val
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n")


def save_config(
    *,
    scope: Scope = "user",
    base_url: str | None = None,
    api_key: str | None = None,
    username: str | None = None,
    default_workspace: str | None = None,
    default_chat: str | None = None,
    output_format: str | None = None,
    notify_rooms: list[str] | None = None,
) -> None:
    """Save config to the chosen scope.

    base_url, api_key, and username are always written to user scope so
    `stash history` works from any directory.
    """
    all_updates = {
        "base_url": base_url,
        "api_key": api_key,
        "username": username,
        "default_workspace": default_workspace,
        "default_chat": default_chat,
        "output_format": output_format,
        "notify_rooms": notify_rooms,
    }

    auth_updates = {k: v for k, v in all_updates.items() if k in USER_SCOPED_KEYS}
    other_updates = {k: v for k, v in all_updates.items() if k not in USER_SCOPED_KEYS}

    if any(v is not None for v in auth_updates.values()):
        _write_to(USER_CONFIG_FILE, auth_updates)

    if any(v is not None for v in other_updates.values()):
        _write_to(_path_for_scope(scope), other_updates)


def detect_previous_scope() -> Scope | None:
    """Return the scope the user previously picked, or None if no prior config.

    A project-level config with any non-auth data means scope was `project`.
    Otherwise, a user-level config with any non-auth data means scope was `user`.
    Auth-only files don't count because api_key/username always live at user
    scope regardless of the requested scope.
    """
    project_path = find_project_config()
    if project_path:
        data = _read_json(project_path)
        if any(k not in USER_SCOPED_KEYS and v for k, v in data.items()):
            return "project"
    if USER_CONFIG_FILE.exists():
        data = _read_json(USER_CONFIG_FILE)
        if any(k not in USER_SCOPED_KEYS and v for k, v in data.items()):
            return "user"
    return None


def stored_base_url() -> str | None:
    """Return the base_url the user has written to disk in either scope, or None.

    Project scope wins over user scope, matching `load_config` precedence.
    """
    project_path = find_project_config()
    if project_path:
        url = _read_json(project_path).get("base_url")
        if url:
            return url
    if USER_CONFIG_FILE.exists():
        url = _read_json(USER_CONFIG_FILE).get("base_url")
        if url:
            return url
    return None


def clear_config(scope: Scope = "user") -> None:
    """Remove stored config for the given scope."""
    if scope == "user":
        if USER_CONFIG_FILE.exists():
            USER_CONFIG_FILE.unlink()
        return
    project_path = find_project_config()
    if project_path and project_path.exists():
        project_path.unlink()


def get_notify_rooms() -> list[str]:
    return load_config().get("notify_rooms", [])


def add_notify_room(room_id: str) -> None:
    rooms = get_notify_rooms()
    if room_id in rooms:
        return
    rooms.append(room_id)
    save_config(notify_rooms=rooms)


def remove_notify_room(room_id: str) -> None:
    rooms = get_notify_rooms()
    if room_id not in rooms:
        return
    rooms.remove(room_id)
    save_config(notify_rooms=rooms)
