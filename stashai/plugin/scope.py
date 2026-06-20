"""Global streaming gate for the plugin.

There is no `.stash` manifest and no cwd/path-based scope anymore. A session
streams iff the plugin is configured (an api_key is present in the user CLI
config) and streaming has not been globally stopped (`stopped_streaming` in the
user config). The `cwd` argument is kept only for call-site compatibility; it
does not affect the result.
"""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_FILE = Path.home() / ".stash" / "config.json"


def _read_user_config() -> dict:
    if not _CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(_CONFIG_FILE.read_text())
    except Exception:
        return {}


def streaming_enabled() -> bool:
    """True if the plugin is configured and not globally stopped."""
    cfg = _read_user_config()
    if not cfg.get("api_key"):
        return False
    return not cfg.get("stopped_streaming")


def cwd_in_scope(cwd: str | None = None) -> bool:
    """True if streaming is globally enabled. `cwd` is ignored."""
    return streaming_enabled()
