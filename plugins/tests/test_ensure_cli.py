"""Cover the CLI floor check that Claude Code's SessionStart hook runs first.

The Claude plugin auto-updates through the marketplace while the CLI does not,
so a plugin release can land on a machine whose CLI is too old to run
`stash hook run claude`. That happened: the plugin pinned users to CLI 0.1.314,
a later plugin required 0.1.318, and because the only upgrade call site lived
*inside* the scripts the old CLI refused to execute, no machine could recover on
its own. ensure_cli.sh is the fix — the one upgrade path a stale install can
still reach — so these tests pin the properties that make it work.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "plugins" / "claude-plugin"
ENSURE_CLI = PLUGIN_DIR / "scripts" / "ensure_cli.sh"
HOOKS_JSON = PLUGIN_DIR / "hooks" / "hooks.json"


def _min_version() -> str:
    match = re.search(r'(?m)^MIN_VERSION="([^"]+)"$', ENSURE_CLI.read_text())
    assert match, "ensure_cli.sh must declare MIN_VERSION"
    return match.group(1)


def _as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _run(
    tmp_path: Path,
    *,
    stash_version: str | None,
    uv_present: bool,
    uv_seconds: int = 0,
) -> subprocess.CompletedProcess:
    """Run ensure_cli.sh against stub `stash`/`uv` binaries on a minimal PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "upgraded"

    if stash_version is not None:
        stash = bin_dir / "stash"
        stash.write_text(
            "#!/usr/bin/env bash\n"
            f'if [ -f "{marker}" ]; then echo "stash 9.9.9"; else '
            f'echo "stash {stash_version}"; fi\n'
        )
        stash.chmod(0o755)

    if uv_present:
        uv = bin_dir / "uv"
        uv.write_text(f'#!/usr/bin/env bash\nsleep {uv_seconds}\ntouch "{marker}"\n')
        uv.chmod(0o755)

    return subprocess.run(
        ["bash", str(ENSURE_CLI)],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
    )


def test_stdout_stays_empty_so_the_hook_payload_is_not_corrupted(tmp_path):
    """SessionStart's stdout is the hook's JSON. Anything this script prints
    there would be parsed as part of that payload."""
    result = _run(tmp_path, stash_version="9.9.9", uv_present=True)
    assert result.stdout == ""


def test_current_cli_refreshes_without_blocking(tmp_path):
    """A CLI at or above the floor still gets a background refresh — the hook
    scripts ship inside the package, so they have to keep pace with the plugin.
    That refresh must never hold up session start."""
    started = time.monotonic()
    result = _run(tmp_path, stash_version="9.9.9", uv_present=True, uv_seconds=5)
    elapsed = time.monotonic() - started

    assert result.returncode == 0
    assert elapsed < 4, f"session start blocked for {elapsed:.1f}s on a background refresh"


def test_stale_cli_is_upgraded_before_the_hook_runs(tmp_path):
    """The regression itself: a CLI below the floor must be repaired here,
    because no code path inside the CLI's own scripts can do it."""
    stale = "0.1.314"
    assert _as_tuple(stale) < _as_tuple(_min_version())
    result = _run(tmp_path, stash_version=stale, uv_present=True)
    assert result.returncode == 0
    assert (tmp_path / "upgraded").exists()


def test_stale_cli_without_uv_fails_loudly(tmp_path):
    """No silent no-op: a machine that cannot self-repair has to say so, or the
    outage stays invisible the way the original one did."""
    result = _run(tmp_path, stash_version="0.1.314", uv_present=False)
    assert result.returncode == 1
    assert "not being recorded" in result.stderr
    assert result.stdout == ""


def test_missing_cli_is_treated_as_stale(tmp_path):
    result = _run(tmp_path, stash_version=None, uv_present=True)
    assert (tmp_path / "upgraded").exists()
    # Installed but still unreachable on this PATH, which is its own failure.
    assert result.returncode == 1
    assert "not on PATH" in result.stderr


def test_session_start_hook_routes_through_the_floor_check():
    """Reverting SessionStart to a bare `stash hook run` would reopen the hole,
    since that command is exactly what a stale CLI rejects."""
    hooks = json.loads(HOOKS_JSON.read_text())
    command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "ensure_cli.sh" in command
    assert command.index("ensure_cli.sh") < command.index("stash hook run"), (
        "the floor check has to run before the hook it protects"
    )


def test_session_start_timeout_allows_a_synchronous_upgrade():
    hooks = json.loads(HOOKS_JSON.read_text())
    timeout = hooks["hooks"]["SessionStart"][0]["hooks"][0]["timeout"]
    assert timeout >= 30000, "a repair runs `uv tool install` inline and needs room"


def test_min_version_is_already_published():
    """Release-ordering guard. The plugin requiring a CLI that PyPI does not
    have yet is how this broke: the floor must never lead the release train."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
    assert match
    assert _as_tuple(_min_version()) <= _as_tuple(match.group(1))


def test_script_is_executable():
    assert ENSURE_CLI.stat().st_mode & 0o111, "hooks invoke this via bash, but keep it runnable"
