"""Plugin hooks only push events when a `.stash/stash.json`
manifest is discoverable from cwd (in the current directory or any ancestor),
or from the main worktree when cwd is inside a git worktree.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_MANIFEST_FILENAME = "stash.json"
_CONFIG_FILENAME = "config.json"


def _git_repo_info(cwd: Path) -> tuple[Path | None, Path | None]:
    """Return (worktree_toplevel, main_worktree_root) for cwd.

    For linked worktrees these differ; for the main worktree they're the same.
    Returns (None, None) if not inside a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel", "--git-common-dir"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            return None, None
        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return None, None
        toplevel = Path(lines[0]).resolve()
        common_dir = Path(lines[1])
        if not common_dir.is_absolute():
            common_dir = (cwd / common_dir).resolve()
        main_root = common_dir.parent
        return toplevel, main_root
    except Exception:
        return None, None


def find_manifest(cwd: str | None) -> dict | None:
    """Walk up from cwd and return the most relevant `.stash/stash.json`.

    Priority (highest first):
    1. Manifest in cwd or ancestors within this worktree
    2. Manifest in the main worktree's root (the repo this worktree belongs to)
    3. Manifest in ancestors above the worktree (e.g. global ~/.stash/)
    """
    if not cwd:
        return None
    cur = Path(cwd).resolve()

    found_manifest = None
    found_at: Path | None = None
    for parent in [cur, *cur.parents]:
        path = parent / ".stash" / _MANIFEST_FILENAME
        if path.exists():
            try:
                found_manifest = json.loads(path.read_text())
                found_at = parent
            except Exception:
                pass
            break

    toplevel, main_root = _git_repo_info(cur)
    if main_root and main_root != toplevel:
        # We're in a linked worktree — main repo manifest takes precedence
        # over a distant ancestor, but not over a manifest local to this worktree.
        if found_at and toplevel and found_at.is_relative_to(toplevel):
            return found_manifest
        main_path = main_root / ".stash" / _MANIFEST_FILENAME
        if main_path.exists():
            try:
                return json.loads(main_path.read_text())
            except Exception:
                pass

    return found_manifest


def cwd_in_scope(cwd: str | None) -> bool:
    """True if `.stash/stash.json` exists in cwd or any ancestor."""
    return find_manifest(cwd) is not None


def repo_stash_disabled(cwd: str | None) -> bool:
    """True if the repo containing `cwd` has opted out of stash streaming
    via `stash_disabled_here=true` in .stash/config.json.

    Uses the same precedence as find_manifest: local worktree config wins,
    then main repo config, then ancestor config.
    Never raises — a missing / malformed file is treated as 'not disabled'."""
    if not cwd:
        return False
    cur = Path(cwd).resolve()

    found_disabled: bool | None = None
    found_at: Path | None = None
    for parent in [cur, *cur.parents]:
        candidate = parent / ".stash" / _CONFIG_FILENAME
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text())
        except Exception:
            break
        found_disabled = bool(data.get("stash_disabled_here", False))
        found_at = parent
        break

    toplevel, main_root = _git_repo_info(cur)
    if main_root and main_root != toplevel:
        if found_at and toplevel and found_at.is_relative_to(toplevel):
            return found_disabled or False
        candidate = main_root / ".stash" / _CONFIG_FILENAME
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text())
            except Exception:
                return False
            return bool(data.get("stash_disabled_here", False))

    return found_disabled or False
