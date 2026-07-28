"""Streaming gate for the plugin.

A session streams iff the plugin is configured (an api_key is present in the
user CLI config), streaming has not been globally stopped (`stopped_streaming`
in the user config), and the session's working directory is not under any
entry in `excluded_paths` — the per-folder opt-out that Stash Desktop's
"Session uploads" card manages.
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


def _under(cwd: Path, excluded: Path) -> bool:
    return cwd == excluded or excluded in cwd.parents


def cwd_in_scope(cwd: str | None = None) -> bool:
    """True if a session in `cwd` should stream.

    Globally enabled AND cwd is not inside an excluded folder. An empty cwd
    (some per-turn events carry none) can't match an exclusion and streams.
    """
    if not streaming_enabled():
        return False
    if not cwd:
        return True
    cfg = _read_user_config()
    cwd_path = Path(cwd).resolve()
    for entry in cfg.get("excluded_paths") or []:
        if isinstance(entry, str) and entry and _under(cwd_path, Path(entry).resolve()):
            return False
    return True
