"""Plugin hooks only push events when a `.stash/stash.json`
manifest is discoverable from cwd (in the current directory or any ancestor).
"""

from __future__ import annotations

import json
from pathlib import Path

_MANIFEST_FILENAME = "stash.json"
_CONFIG_FILENAME = "config.json"


def find_manifest(cwd: str | None) -> dict | None:
    """Walk up from cwd and return the first `.stash/stash.json` as a dict, or None."""
    if not cwd:
        return None
    cur = Path(cwd).resolve()
    for parent in [cur, *cur.parents]:
        path = parent / ".stash" / _MANIFEST_FILENAME
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                return None
    return None


def cwd_in_scope(cwd: str | None) -> bool:
    """True if `.stash/stash.json` exists in cwd or any ancestor."""
    return find_manifest(cwd) is not None


def repo_stash_disabled(cwd: str | None) -> bool:
    """True if the repo containing `cwd` has opted out of stash streaming
    via `stash_disabled_here=true` in .stash/config.json. Walks up from cwd
    looking for the marker. Never raises — a missing / malformed file is
    treated as 'not disabled'."""
    if not cwd:
        return False
    cur = Path(cwd).resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / ".stash" / _CONFIG_FILENAME
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text())
        except Exception:
            return False
        return bool(data.get("stash_disabled_here", False))
    return False
