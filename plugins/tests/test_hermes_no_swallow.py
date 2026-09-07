"""Assert the hermes plugin hook scripts never bare-catch Stash calls.

`stash connect hermes` hands users the hook scripts from the shipped assets,
so a swallowed error there silently drops telemetry. AGENTS.md forbids bare
catch-alls and silent swallow-and-continue: a failed upload / session-create /
session-end / assistant-message / tool-use must propagate to the hook runner
(fail loud) instead of vanishing.

Both the canonical source (`plugins/hermes-plugin/scripts/`) and the shipped
copy (`stashai/plugin/assets/hermes/scripts/`) are asserted separately so
neither side can regress independently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIRS = (
    REPO_ROOT / "plugins" / "hermes-plugin" / "scripts",
    REPO_ROOT / "stashai" / "plugin" / "assets" / "hermes" / "scripts",
)

# A bare catch-all swallows the exception with no log and no fail-loud:
# `except:` or `except Exception:` / `except BaseException:` with nothing but
# whitespace/comments between the keyword and the colon.
BARE_CATCH = re.compile(r"^\s*except\s*(?:Exception|BaseException)?\s*:\s*(#.*)?$")


def _offending_lines(scripts_dir: Path) -> list[tuple[str, int, str]]:
    offenders: list[tuple[str, int, str]] = []
    for script in sorted(scripts_dir.glob("*.py")):
        for lineno, line in enumerate(script.read_text().splitlines(), start=1):
            if BARE_CATCH.match(line):
                offenders.append((script.name, lineno, line))
    return offenders


def test_hermes_source_no_bare_catch_all():
    offenders = _offending_lines(SCRIPTS_DIRS[0])
    assert not offenders, (
        "hermes source hook scripts must not bare-catch Stash calls (fail loud). "
        f"Found: {offenders}"
    )


def test_hermes_assets_no_bare_catch_all():
    offenders = _offending_lines(SCRIPTS_DIRS[1])
    assert not offenders, (
        f"shipped hermes assets must not bare-catch Stash calls (fail loud). Found: {offenders}"
    )
