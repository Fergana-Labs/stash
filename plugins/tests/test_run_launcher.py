"""The hook launcher must refuse loudly when no stashai interpreter exists.

Exec'ing a fallback python3 in that case is how a stale pip-installed client
ran (and 404'd) for a month without anyone seeing an error: whatever python
happened to resolve could import old code and fail silently forever.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

RUN_SH = Path(__file__).resolve().parent.parent / "claude-plugin" / "scripts" / "_run.sh"


def test_missing_stashai_is_a_loud_error_not_a_fallback_python(tmp_path):
    # A PATH with core utilities but no `stash` and no `uv`: resolution finds
    # nothing, and the launcher must exit nonzero with a human-readable reason
    # instead of exec'ing whatever python3 is lying around.
    proc = subprocess.run(
        ["bash", str(RUN_SH), "on_prompt"],
        input="{}",
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        timeout=30,
    )
    assert proc.returncode == 1
    assert "NOT uploading" in proc.stderr
