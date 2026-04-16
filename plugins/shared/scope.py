"""Repo-scope gate. With `scope=repo` (default), plugins only push events
and transcripts for sessions run in the repo captured at `stash connect`
time — or any of its worktrees (they share the git common-dir).
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache


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
