"""Plugin hooks only push events when a `.stash` file is discoverable from cwd
(in the current directory or any ancestor), or from the main worktree when cwd
is inside a git worktree.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_MANIFEST_NAME = ".stash"


def _read_manifest(base: Path) -> dict | None:
    """Read a manifest from base/.stash (file) or base/.stash/stash.json (dir)."""
    candidate = base / _MANIFEST_NAME
    if candidate.is_file():
        return json.loads(candidate.read_text())
    inner = candidate / "stash.json"
    if inner.is_file():
        return json.loads(inner.read_text())
    return None


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
            common_dir = (toplevel / common_dir).resolve()
        main_root = common_dir.parent
        return toplevel, main_root
    except Exception:
        return None, None


def find_manifest(cwd: str | None) -> dict | None:
    """Return the parsed `.stash` manifest for cwd.

    If inside a git repo, checks the main worktree root (works for both
    regular checkouts and linked worktrees). Falls back to walking up
    from cwd for non-git directories.
    """
    if not cwd:
        return None
    cur = Path(cwd).resolve()

    _toplevel, main_root = _git_repo_info(cur)
    if main_root:
        try:
            result = _read_manifest(main_root)
            if result is not None:
                return result
        except Exception:
            return None

    for parent in [cur, *cur.parents]:
        try:
            result = _read_manifest(parent)
            if result is not None:
                return result
        except Exception:
            return None
    return None


def cwd_in_scope(cwd: str | None) -> bool:
    """True if a `.stash` manifest file exists in cwd or any ancestor."""
    return find_manifest(cwd) is not None
