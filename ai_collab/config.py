import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "ai-collab.json"


def _load_local_config() -> dict:
    """Load saved config from ~/.config/ai-collab.json."""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_local_config(config: dict) -> None:
    """Save config to ~/.config/ai-collab.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


_local = _load_local_config()


class Settings:
    DATABASE_URL: str = os.getenv(
        "AI_COLLAB_DATABASE_URL",
        os.getenv("DATABASE_URL", ""),
    )
    API_URL: str = os.getenv(
        "AI_COLLAB_API_URL",
        _local.get("api_url", ""),
    )
    API_KEY: str = os.getenv(
        "AI_COLLAB_API_KEY",
        _local.get("api_key", ""),
    )


settings = Settings()
