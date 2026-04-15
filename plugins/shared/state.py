"""Per-plugin persistent state.

Each agent plugin passes in its own data_dir (e.g. ~/.claude/plugins/data/octopus,
~/.cursor/octopus, ~/.gemini/octopus). The shape of what we write is identical
across agents — only the directory differs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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
