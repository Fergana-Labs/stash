"""Plugin hooks only push events when a `.stash/stash.json`
manifest is discoverable from cwd (in the current directory or any ancestor).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_MANIFEST_FILENAME = "stash.json"
_CONFIG_FILENAME = "config.json"


@lru_cache(maxsize=64)
def _has_manifest(cwd: str | None) -> bool:
    """True if `.stash/stash.json` exists in cwd or any ancestor."""
    if not cwd:
        return False
    try:
        cur = Path(cwd).resolve()
    except Exception:
        return False
    for parent in [cur, *cur.parents]:
        if (parent / ".stash" / _MANIFEST_FILENAME).exists():
            return True
    return False


def cwd_in_scope(cwd: str | None) -> bool:
    """True when cwd is within a stash-installed tree.

    Callers used to pass a scope config dict here; the concept has been
    folded into the manifest's location so that's no longer needed.
    """
    return _has_manifest(cwd)


@lru_cache(maxsize=64)
def repo_stash_disabled(cwd: str | None) -> bool:
    """True if the repo containing `cwd` has opted out of stash streaming
    via `stash_disabled_here=true` in .stash/config.json. Walks up from cwd
    looking for the marker. Never raises — a missing / malformed file is
    treated as 'not disabled'."""
    if not cwd:
        return False
    try:
        cur = Path(cwd).resolve()
    except Exception:
        return False
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
