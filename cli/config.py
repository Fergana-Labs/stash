"""Auth credential and config storage for the octopus CLI.

Config lives in two scopes:
- user:    ~/.octopus/config.json  (applies everywhere)
- project: <repo>/.octopus/config.json  (overrides user-level when present)

Project lookup walks up from cwd. Project values override user values.
Auth (api_key, username) is always stored at user scope — it's per-machine,
not per-repo.
"""

import json
import os
from pathlib import Path
from typing import Literal

USER_CONFIG_DIR = Path.home() / ".octopus"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

PROJECT_DIRNAME = ".octopus"
PROJECT_FILENAME = "config.json"

Scope = Literal["user", "project"]

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
AUTH_KEYS = {"api_key", "username"}


def find_project_config(start: Path | None = None) -> Path | None:
    """Walk up from cwd looking for .octopus/config.json. Return path or None."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / PROJECT_DIRNAME / PROJECT_FILENAME
        if candidate.exists():
            return candidate
    return None


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

    if url := os.environ.get("OCTOPUS_URL"):
        cfg["base_url"] = url
    if key := os.environ.get("OCTOPUS_API_KEY"):
        cfg["api_key"] = key
    return cfg


def _path_for_scope(scope: Scope) -> Path:
    if scope == "user":
        return USER_CONFIG_FILE
    existing = find_project_config()
    if existing:
        return existing
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

    Auth keys (api_key, username) are always written to the user scope even if
    scope='project' — auth is per-machine, not per-repo.
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

    auth_updates = {k: v for k, v in all_updates.items() if k in AUTH_KEYS}
    other_updates = {k: v for k, v in all_updates.items() if k not in AUTH_KEYS}

    if any(v is not None for v in auth_updates.values()):
        _write_to(USER_CONFIG_FILE, auth_updates)

    if any(v is not None for v in other_updates.values()):
        _write_to(_path_for_scope(scope), other_updates)


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
