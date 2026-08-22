"""Assert the pi-plugin hook scripts route hook-runner data through echo_stdout.

`echo_stdout` (from STAS-066's CLI channel discipline) is the single path for
parseable stdout data. The pi hooks emit exactly one piece of parseable data to
the hook runner — the upload/disabled `systemMessage` JSON — and it must go
through `echo_stdout`, never a raw ``print``, so stdout stays machine-parseable.
This invariant is enforced on BOTH the canonical source
(`plugins/pi-plugin/scripts/`) and the shipped copy
(`stashai/plugin/assets/pi/scripts/`) so neither regresses independently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SRC_DIR = REPO_ROOT / "plugins" / "pi-plugin" / "scripts"
DST_DIR = REPO_ROOT / "stashai" / "plugin" / "assets" / "pi" / "scripts"

RAW_SYSTEM_MESSAGE_PRINT = re.compile(r"print\(json\.dumps\(\{\"systemMessage\"")

_EMITTING_SCRIPTS = ("on_session_start.py", "on_stop.py")


def _py_scripts(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def test_system_message_never_emitted_via_raw_print():
    """The hook runner reads the `systemMessage` payload from stdout; routing it
    through a raw ``print`` bypasses the STAS-066 channel discipline and risks
    polluting stdout, so the pi hooks must use echo_stdout instead."""
    for root in (SRC_DIR, DST_DIR):
        for path in _py_scripts(root):
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                assert not RAW_SYSTEM_MESSAGE_PRINT.search(line), (
                    f"{path.relative_to(REPO_ROOT)}:{lineno} emits a systemMessage "
                    f"via raw print: {line.strip()!r} (use echo_stdout)"
                )


def test_emitting_scripts_route_system_message_through_echo_stdout():
    """The scripts that emit parseable data import and use echo_stdout."""
    for name in _EMITTING_SCRIPTS:
        text = (SRC_DIR / name).read_text()
        assert "from cli.formatting import echo_stdout" in text, (
            f"{SRC_DIR / name} does not import echo_stdout"
        )
        assert "echo_stdout(json.dumps" in text, (
            f"{SRC_DIR / name} does not route its systemMessage through echo_stdout"
        )


def test_both_pi_copies_carry_the_wiring():
    """The canonical source and the shipped copy must both route via echo_stdout."""
    for name in _EMITTING_SCRIPTS:
        for root in (SRC_DIR, DST_DIR):
            text = (root / name).read_text()
            assert "from cli.formatting import echo_stdout" in text
            assert "echo_stdout(json.dumps" in text
