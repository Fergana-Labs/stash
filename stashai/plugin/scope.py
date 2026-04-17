"""Repo-scope gate. With `scope=repo` (default), plugins only push events
and transcripts for sessions run in the repo captured at `stash connect`
time — or any of its worktrees (they share the git common-dir).
"""

from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=64)
def _common_dir(cwd: str) -> str | None:
    if not cwd:
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return os.path.abspath(os.path.join(cwd, proc.stdout.strip()))
    except Exception:
        pass
    return None


def cwd_in_scope(cwd: str | None, cfg: dict) -> bool:
    scope = (cfg.get("scope") or "repo").strip().lower()
    if scope in ("all", "workspace"):
        return True
    install = cfg.get("install_repo_common_dir") or ""
    if not install or not cwd:
        return False
    current = _common_dir(cwd)
    return bool(current) and os.path.normpath(current) == os.path.normpath(install)


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
        candidate = parent / ".stash" / "config.json"
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text())
        except Exception:
            return False
        return bool(data.get("stash_disabled_here", False))
    return False
