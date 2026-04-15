"""Per-plugin persistent state and local cache.

Each agent plugin passes in its own data_dir (e.g. ~/.claude/plugins/data/octopus,
~/.cursor/octopus, ~/.gemini/octopus). The shape of what we write is identical
across agents — only the directory differs.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

CACHE_TTL = 300  # 5 minutes

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
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def load_state(data_dir: Path) -> dict:
    return _read_json(data_dir / "state.json", dict(DEFAULT_STATE))


def save_state(data_dir: Path, state: dict) -> None:
    _write_json(data_dir / "state.json", state)


def load_cache(data_dir: Path) -> dict | None:
    path = data_dir / "context_cache.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    if time.time() - data.get("_timestamp", 0) > CACHE_TTL:
        return None
    return data


def save_cache(data_dir: Path, profile: dict, recent_events: list) -> None:
    _write_json(data_dir / "context_cache.json", {
        "_timestamp": time.time(),
        "profile": profile,
        "recent_events": recent_events,
    })


def load_escalations(escalation_dir: Path) -> str:
    """Read up to 5 pending notification files from a shared notifications dir."""
    if not escalation_dir.exists():
        return ""

    lines = []
    for nf in sorted(escalation_dir.glob("*.json"))[:5]:
        try:
            nd = json.loads(nf.read_text())
        except Exception:
            continue
        detail = nd.get("detail", nd.get("content", ""))[:300]
        ntype = nd.get("type", "info")
        lines.append(f"- [{ntype}] {detail}")

    if not lines:
        return ""
    return "\n\n## Pending Manager Escalations\n" + "\n".join(lines) + "\n"
