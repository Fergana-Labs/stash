"""Per-plugin persistent state plus shared curate-gating helpers.

Per-plugin state (session_id) lives under each agent's `data_dir`.
Auto-curate toggling and the cross-agent cooldown live in the central CLI
config at `~/.stash/config.json` so one toggle controls every installed plugin.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

CURATE_COOLDOWN_SECONDS = 30 * 60

# How recently codex_hooks Stop must have fired for the `notify` fallback to
# self-suppress. One turn is usually well under a minute; 60s is generous
# without leaving a long window where a downgraded Codex would get no events.
CODEX_HOOKS_FRESHNESS_SECONDS = 60

CENTRAL_CONFIG_PATH = Path.home() / ".stash" / "config.json"

_DEFAULT_STATS = {"tool_count": 0, "tools_used": [], "files_changed": []}

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
        "files_changed": list(stats.get("files_changed") or []),
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
    if file_path and tool_name in ("edit", "write") and file_path not in stats["files_changed"]:
        stats["files_changed"].append(file_path)
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


# ---------------------------------------------------------------------------
# Central config helpers (auto_curate flag, streaming kill switch, cooldown)
# ---------------------------------------------------------------------------

def _read_central() -> dict:
    return _read_json(CENTRAL_CONFIG_PATH, {})


def _write_central(updates: dict) -> None:
    existing = _read_central()
    existing.update(updates)
    _write_json(CENTRAL_CONFIG_PATH, existing)


def auto_curate_enabled() -> bool:
    """Read the central `auto_curate` flag. Defaults to True when unset."""
    raw = _read_central().get("auto_curate", True)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def set_auto_curate(enabled: bool) -> None:
    _write_central({"auto_curate": bool(enabled)})


def curate_cooldown_active() -> bool:
    last = _read_central().get("last_curate_at", 0) or 0
    try:
        last_f = float(last)
    except Exception:
        return False
    return (time.time() - last_f) < CURATE_COOLDOWN_SECONDS


def record_curate_run() -> None:
    _write_central({"last_curate_at": time.time()})


# ---------------------------------------------------------------------------
# Codex dedup: codex_hooks Stop and the notify fallback both push
# assistant_message. If a user enables both, every turn double-fires. The
# Stop hook stamps a heartbeat; the notify path skips when that heartbeat
# is fresh.
# ---------------------------------------------------------------------------

def mark_codex_hooks_active() -> None:
    _write_central({"codex_hooks_last_seen": time.time()})


def codex_hooks_recently_active() -> bool:
    last = _read_central().get("codex_hooks_last_seen", 0) or 0
    try:
        last_f = float(last)
    except Exception:
        return False
    return (time.time() - last_f) < CODEX_HOOKS_FRESHNESS_SECONDS
