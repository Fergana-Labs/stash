"""Plugin hooks only push events when a `.stash` manifest file is discoverable
from cwd (in the current directory or any ancestor), or from the main worktree
when cwd is inside a git worktree.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_MANIFEST_FILE = ".stash"


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
        main_path = main_root / _MANIFEST_FILE
        if main_path.is_file():
            try:
                return json.loads(main_path.read_text())
            except Exception:
                return None

    for parent in [cur, *cur.parents]:
        path = parent / _MANIFEST_FILE
        if path.is_file():
            try:
                return json.loads(path.read_text())
            except Exception:
                return None
    return None


def cwd_in_scope(cwd: str | None) -> bool:
    """True if a `.stash` manifest file exists in cwd or any ancestor."""
    return find_manifest(cwd) is not None
