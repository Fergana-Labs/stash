"""Detect duplicate `stash` installs that shadow each other.

A bare `pip install stashai` under a pyenv or system interpreter leaves a
second `stash` entry point on PATH. It never auto-updates (only the uv/pipx
install does), and which copy wins differs by context — pyenv shims prepend
their version's bin dir, so a hook can resolve a stale copy the shell never
sees. The result is months-old code failing long after the install that
caused it. Warn the moment more than one install is visible.
"""

from __future__ import annotations

import os
from pathlib import Path


def find_stash_installs() -> list[Path]:
    """Distinct `stash` executables on PATH, in PATH order, deduped by realpath."""
    seen: set[Path] = set()
    installs: list[Path] = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        candidate = Path(entry) / "stash"
        if not (candidate.is_file() and os.access(candidate, os.X_OK)):
            continue
        real = candidate.resolve()
        if real in seen:
            continue
        seen.add(real)
        installs.append(candidate)
    return installs


def shadow_install_warning() -> str | None:
    """Warning text when multiple `stash` installs can shadow each other, else None.

    An activated virtualenv (VIRTUAL_ENV set) is the documented dev-mode
    setup — its `stash` deliberately coexists with the released one — so the
    check is skipped entirely rather than special-cased per install.
    """
    if os.environ.get("VIRTUAL_ENV"):
        return None
    installs = find_stash_installs()
    if len(installs) <= 1:
        return None
    listing = "\n".join(f"  {path} -> {path.resolve()}" for path in installs)
    return (
        "Multiple `stash` installs found on PATH. The extras never "
        "auto-update and can shadow the active one in some contexts "
        "(pyenv shims, agent hooks), eventually breaking with stale code:\n"
        f"{listing}\n"
        "Keep one (`uv tool install stashai`) and remove the rest — for a "
        "pip install under pyenv: `pip uninstall stashai`, then `pyenv rehash`."
    )
