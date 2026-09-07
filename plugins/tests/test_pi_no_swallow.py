"""Assert the pi-plugin hook scripts carry no bare catch-alls and no silent
default on a missing cwd.

AGENTS.md bans `except Exception` swallow-and-continue handlers and default
values papering over a missing input. These invariants are enforced on BOTH
the canonical source (`plugins/pi-plugin/scripts/`) and the shipped copy
(`stashai/plugin/assets/pi/scripts/`) so neither regresses independently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

BARE_EXCEPT_RE = re.compile(r"^\s*except (Exception|BaseException):")

SRC_DIR = REPO_ROOT / "plugins" / "pi-plugin" / "scripts"
DST_DIR = REPO_ROOT / "stashai" / "plugin" / "assets" / "pi" / "scripts"


def _walk_py_scripts(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def test_pi_hook_scripts_have_no_bare_except():
    for root in (SRC_DIR, DST_DIR):
        for path in _walk_py_scripts(root):
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                assert not BARE_EXCEPT_RE.match(line), (
                    f"{path.relative_to(REPO_ROOT)}:{lineno} has a bare catch-all: {line.strip()!r}"
                )


def test_pi_run_sh_has_no_bare_except():
    for path in (SRC_DIR / "_run.sh", DST_DIR / "_run.sh"):
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), 1):
            assert not BARE_EXCEPT_RE.match(line), (
                f"{path.relative_to(REPO_ROOT)}:{lineno} has a bare "
                f"catch-all: {line.strip()!r} (narrow to subprocess/OSError)"
            )


def test_pi_config_fails_loud_on_missing_cwd():
    """is_fusion_managed must raise on a missing cwd, never silently return False."""
    for root in (SRC_DIR, DST_DIR):
        src = (root / "config.py").read_text()
        # The function must fail loud on a missing cwd ...
        assert "raise ValueError" in src, f"{root.name}/config.py no longer raises on a missing cwd"
        # ... and the old silent-default branch (`if not cwd:` -> `return False`)
        # must be gone.
        assert re.search(r"if not cwd:\s*return False", src) is None, (
            f"{root.name}/config.py still silently returns False for a missing cwd"
        )
