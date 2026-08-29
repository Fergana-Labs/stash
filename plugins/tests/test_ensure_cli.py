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
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "plugins" / "claude-plugin"
ENSURE_CLI = PLUGIN_DIR / "scripts" / "ensure_cli.sh"
HOOKS_JSON = PLUGIN_DIR / "hooks" / "hooks.json"

# Everything ensure_cli.sh resolves through PATH, derived by dropping each entry and
# watching which scenario breaks. Everything else it uses is a bash builtin (`command
# -v`, `[ -x ]`, `echo`). `bash` is here because the child's own program name is
# resolved against the supplied env, so without it subprocess.run raises
# FileNotFoundError. `awk` serves version_below() and the `--version` parse. `touch`
# writes the uv stub's upgrade marker. `sleep` looks disposable — the stub would just
# exit sooner — but that is exactly how both "must not block session start" tests
# would start passing vacuously. `sh` and `env` are deliberately absent: the stub
# shebangs name /usr/bin/env by absolute path, which the kernel resolves without PATH.
SANDBOX_UTILITIES = ("bash", "awk", "sleep", "touch")

# find_uv() in plugins/claude-plugin/scripts/ensure_cli.sh also stats uv at these
# absolute paths, which no PATH sandbox can neutralise: the child finds them without
# looking at PATH at all. Keep this list in step with that candidate list.
UNSANDBOXABLE_UV_CANDIDATES = (Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv"))


def _min_version() -> str:
    match = re.search(r'(?m)^MIN_VERSION="([^"]+)"$', ENSURE_CLI.read_text())
    assert match, "ensure_cli.sh must declare MIN_VERSION"
    return match.group(1)


def _as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _hermetic_bin_dir(bin_dir: Path) -> Path:
    """Populate the sandbox with exactly the allowlisted utilities.

    Each one is symlinked in by resolved absolute path so the child's PATH can stay
    equal to this single directory. An unresolvable utility aborts the run naming it:
    quietly dropping an entry is how a timing test turns into a no-op.
    """
    for name in SANDBOX_UTILITIES:
        source = shutil.which(name)
        if source is None:
            raise AssertionError(f"cannot build the test sandbox: {name} is not installed")
        os.symlink(source, bin_dir / name)
    return bin_dir


def _child_env(bin_dir: Path, home: Path) -> dict[str, str]:
    """The child's entire environment: the sandbox directory and a redirected HOME.

    Nothing else is on PATH, so no host binary can reach the script.
    """
    return {"PATH": str(bin_dir), "HOME": str(home)}


def _run(
    tmp_path: Path,
    *,
    stash_version: str | None,
    uv_present: bool,
    uv_seconds: int = 0,
) -> subprocess.CompletedProcess:
    """Run ensure_cli.sh with the sandbox as the child's only PATH entry.

    The child sees SANDBOX_UTILITIES plus the scenario's `stash`/`uv` stubs and nothing
    else, so host binaries — above all the machine's own `uv`, which `find_uv()` would
    happily find — cannot reach it. A `uv_present=False` scenario is therefore a true
    negative on any host, including one that has uv installed.
    """
    for candidate in UNSANDBOXABLE_UV_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            raise AssertionError(
                f"{candidate} is executable, and the sandbox cannot express 'absent' for a "
                "candidate find_uv() stats by absolute path. This scenario would silently "
                "take the uv-present branch. Fix find_uv()'s candidate list; do not weaken "
                "the assertion that depends on uv being absent."
            )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _hermetic_bin_dir(bin_dir)
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
        env=_child_env(bin_dir, tmp_path),
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


def test_stale_cli_starts_an_upgrade(tmp_path):
    """The regression itself: a CLI below the floor must be upgraded from here,
    because no code path inside the CLI's own scripts can do it."""
    stale = "0.1.314"
    assert _as_tuple(stale) < _as_tuple(_min_version())
    result = _run(tmp_path, stash_version=stale, uv_present=True)

    marker = tmp_path / "upgraded"
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists(), "no upgrade was started for a CLI below the floor"
    # Exit 1 short-circuits the `&&`, so this message is the only one the user
    # sees instead of the CLI's less useful "Unknown hook agent".
    assert result.returncode == 1
    assert "next one will be" in result.stderr


def test_stale_cli_does_not_block_session_start(tmp_path):
    """The upgrade is detached even on the stale path. One lost session is a
    far better trade than a stall the user feels at every session start."""
    started = time.monotonic()
    _run(tmp_path, stash_version="0.1.314", uv_present=True, uv_seconds=5)
    elapsed = time.monotonic() - started

    assert elapsed < 4, f"session start blocked for {elapsed:.1f}s on the upgrade"


def test_stale_cli_without_uv_fails_loudly(tmp_path):
    """No silent no-op: a machine that cannot self-repair has to say so, or the
    outage stays invisible the way the original one did."""
    result = _run(tmp_path, stash_version="0.1.314", uv_present=False)
    assert result.returncode == 1
    # Branch-unique phrase: the uv-present message also says a session is not
    # recorded, so a looser substring would match whichever branch ran.
    assert "Session activity is not being recorded" in result.stderr
    assert "next one will be" not in result.stderr
    assert result.stdout == ""


def test_no_host_binary_leaks_into_the_sandbox(tmp_path, monkeypatch):
    """A uv installed on the machine running these tests must stay unreachable.

    This is the regression itself: as long as the child could see a host directory,
    `find_uv()` preferred the real uv and the fail-loudly branch above was never
    executed here — it also forked a genuine upgrade on the developer's machine.
    """
    host_dir = tmp_path / "host-visible"
    host_dir.mkdir()
    hit = tmp_path / "host-uv-ran"
    sentinel = host_dir / "uv"
    sentinel.write_text(f'#!/usr/bin/env bash\n: > "{hit}"\n')
    sentinel.chmod(0o755)
    monkeypatch.setenv("PATH", f"{host_dir}{os.pathsep}{os.environ['PATH']}")

    # Positive control: prove the sentinel really is reachable when the ambient
    # environment is inherited. Without it, a broken fixture would make the
    # assertions below pass for the wrong reason — the failure mode this guards.
    control = subprocess.run(["bash", "-c", "command -v uv"], capture_output=True, text=True)
    assert control.stdout.strip() == str(sentinel), (
        "the sentinel uv is not visible to an inherited environment, so the "
        "negative assertions below would pass vacuously"
    )

    result = _run(tmp_path, stash_version="0.1.314", uv_present=False)

    assert not hit.exists(), "ensure_cli.sh reached the uv installed on this machine"
    assert "Session activity is not being recorded" in result.stderr


def test_the_sandbox_is_the_whole_child_environment(tmp_path):
    """PATH names the sandbox and nothing else, and the sandbox holds every
    allowlisted utility.

    `sleep` is the entry no scenario outcome depends on, so pin it here: drop it and
    the uv stub's `sleep 5` turns into "command not found", which makes both "must not
    block session start" tests green without exercising anything.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _hermetic_bin_dir(bin_dir)

    assert _child_env(bin_dir, tmp_path)["PATH"] == str(bin_dir)
    assert sorted(entry.name for entry in bin_dir.iterdir()) == sorted(SANDBOX_UTILITIES)
    for name in SANDBOX_UTILITIES:
        assert (bin_dir / name).is_file(), f"{name} is missing from the sandbox"


def test_missing_cli_is_treated_as_stale(tmp_path):
    result = _run(tmp_path, stash_version=None, uv_present=True)
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_session_start_hook_routes_through_the_floor_check():
    """Reverting SessionStart to a bare `stash hook run` would reopen the hole,
    since that command is exactly what a stale CLI rejects."""
    hooks = json.loads(HOOKS_JSON.read_text())
    command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "ensure_cli.sh" in command
    assert command.index("ensure_cli.sh") < command.index("stash hook run"), (
        "the floor check has to run before the hook it protects"
    )


def test_session_start_timeout_stays_short():
    """Nothing here waits on the network, so the timeout must not leave room
    for a long stall. A user notices a blocked session start immediately; they
    do not notice one missing transcript."""
    hooks = json.loads(HOOKS_JSON.read_text())
    timeout = hooks["hooks"]["SessionStart"][0]["hooks"][0]["timeout"]
    assert timeout <= 15000, "SessionStart must not be able to hang on the upgrade"


def test_min_version_is_already_published():
    """Release-ordering guard. The plugin requiring a CLI that PyPI does not
    have yet is how this broke: the floor must never lead the release train."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
    assert match
    assert _as_tuple(_min_version()) <= _as_tuple(match.group(1))


def test_script_is_executable():
    assert ENSURE_CLI.stat().st_mode & 0o111, "hooks invoke this via bash, but keep it runnable"
