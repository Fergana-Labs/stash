"""Per-plugin persistent state plus shared curate-gating helpers.

Per-plugin state (session_id) lives under each agent's `data_dir`.
Auto-curate toggling, the cross-agent cooldown, and the streaming kill switch
live in the central CLI config at `~/.octopus/config.json` so one toggle
controls every installed plugin.
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

CENTRAL_CONFIG_PATH = Path.home() / ".octopus" / "config.json"

DEFAULT_STATE = {
    "streaming_enabled": True,
    "session_id": "",
    "last_sync": None,
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
    """Return per-plugin state merged with centralized toggles.

    `streaming_enabled` lives in central config (~/.octopus/config.json) so one
    toggle controls every installed plugin. Per-plugin `session_id` still lives
    under `data_dir/state.json`.
    """
    state = _read_json(data_dir / "state.json", dict(DEFAULT_STATE))
    central = _read_central()
    if "streaming_enabled" in central:
        state["streaming_enabled"] = bool(central["streaming_enabled"])
    return state


def save_state(data_dir: Path, state: dict) -> None:
    _write_json(data_dir / "state.json", state)


# ---------------------------------------------------------------------------
# Central config helpers (auto_curate flag, streaming kill switch, cooldown)
# ---------------------------------------------------------------------------

def _read_central() -> dict:
    return _read_json(CENTRAL_CONFIG_PATH, {})


def _write_central(updates: dict) -> None:
    existing = _read_central()
    existing.update(updates)
    _write_json(CENTRAL_CONFIG_PATH, existing)


def set_streaming_enabled(enabled: bool) -> None:
    _write_central({"streaming_enabled": bool(enabled)})


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
