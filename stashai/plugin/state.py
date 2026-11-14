"""Per-plugin persistent state.

Per-plugin state (session_id) lives under each agent's `data_dir`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_STATS = {"tool_count": 0, "tools_used": [], "files_touched": []}

DEFAULT_STATE = {
    "session_id": "",
    "last_sync": None,
    "stats": dict(_DEFAULT_STATS),
}


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # pid-suffix the tmp so concurrent writers from different processes don't
    # clobber each other's in-flight tmp file. os.replace itself is atomic.
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def load_state(data_dir: Path) -> dict:
    """Return per-plugin state with centralized toggles overlaid."""
    state = _read_json(data_dir / "state.json", dict(DEFAULT_STATE))
    return state


def save_state(data_dir: Path, state: dict) -> None:
    _write_json(data_dir / "state.json", state)


# ---------------------------------------------------------------------------
# Session stats: incremented on every tool_use, read at session_end.
#
# Replaces reading the agent's transcript at session_end, which was Claude-only
# and blew through Codex's 5s hook timeout on huge sessions. One read+write of
# state.json per tool_use amortizes the cost and works for every plugin.
# ---------------------------------------------------------------------------

def _load_stats(state: dict) -> dict:
    stats = state.get("stats")
    if not isinstance(stats, dict):
        return dict(_DEFAULT_STATS)
    return {
        "tool_count": int(stats.get("tool_count", 0) or 0),
        "tools_used": list(stats.get("tools_used") or []),
        "files_touched": list(stats.get("files_touched") or stats.get("files_changed") or []),
    }


def record_tool_use(data_dir: Path, tool_name: str, file_path: str | None) -> None:
    """Increment tool counter + sets. Called from every plugin's on_tool_use."""
    if not tool_name:
        return
    state = _read_json(data_dir / "state.json", dict(DEFAULT_STATE))
    stats = _load_stats(state)
    stats["tool_count"] += 1
    if tool_name not in stats["tools_used"]:
        stats["tools_used"].append(tool_name)
    if file_path and tool_name in ("edit", "write", "read") and file_path not in stats["files_touched"]:
        stats["files_touched"].append(file_path)
    state["stats"] = stats
    _write_json(data_dir / "state.json", state)


def reset_stats(data_dir: Path) -> None:
    """Called from session_start after session_id is saved."""
    state = _read_json(data_dir / "state.json", dict(DEFAULT_STATE))
    state["stats"] = dict(_DEFAULT_STATS)
    _write_json(data_dir / "state.json", state)


def read_stats(state: dict) -> dict:
    """Pull stats out of an already-loaded state dict. Used by stream_session_end."""
    return _load_stats(state)
