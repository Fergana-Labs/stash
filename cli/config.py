"""Auth credential and config storage for the boozle CLI."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".boozle"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "base_url": "http://localhost:3456",
    "api_key": "",
    "username": "",
    "default_workspace": "",
    "default_chat": "",
    "default_store": "",
    "output_format": "human",
    "notify_rooms": [],
}


def load_config() -> dict:
    """Load config, with env var overrides."""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    # Env var overrides
    if url := os.environ.get("BOOZLE_URL"):
        cfg["base_url"] = url
    if key := os.environ.get("BOOZLE_API_KEY"):
        cfg["api_key"] = key
    return cfg


def save_config(
    base_url: str | None = None,
    api_key: str | None = None,
    username: str | None = None,
    default_workspace: str | None = None,
    default_chat: str | None = None,
    default_store: str | None = None,
    output_format: str | None = None,
    notify_rooms: list[str] | None = None,
) -> None:
    """Save config, merging with existing values."""
    cfg = load_config()
    if base_url is not None:
        cfg["base_url"] = base_url
    if api_key is not None:
        cfg["api_key"] = api_key
    if username is not None:
        cfg["username"] = username
    if default_workspace is not None:
        cfg["default_workspace"] = default_workspace
    if default_chat is not None:
        cfg["default_chat"] = default_chat
    if default_store is not None:
        cfg["default_store"] = default_store
    if output_format is not None:
        cfg["output_format"] = output_format
    if notify_rooms is not None:
        cfg["notify_rooms"] = notify_rooms
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n")


def clear_config() -> None:
    """Remove stored config."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


def get_notify_rooms() -> list[str]:
    """Get list of rooms subscribed for notifications."""
    cfg = load_config()
    return cfg.get("notify_rooms", [])


def add_notify_room(room_id: str) -> None:
    """Subscribe to notifications for a room."""
    cfg = load_config()
    rooms = cfg.get("notify_rooms", [])
    if room_id not in rooms:
        rooms.append(room_id)
        save_config(notify_rooms=rooms)


def remove_notify_room(room_id: str) -> None:
    """Unsubscribe from notifications for a room."""
    cfg = load_config()
    rooms = cfg.get("notify_rooms", [])
    if room_id in rooms:
        rooms.remove(room_id)
        save_config(notify_rooms=rooms)
