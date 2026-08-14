"""Keep the running `stash` install current without the user thinking about it.

Freshness used to depend entirely on a chain outside the CLI: an agent plugin
had to be installed, its session-start hook had to fire, uv had to be findable
from that hook's PATH, and the copy uv upgraded had to be the copy the user
actually runs. Every link failed silently, and the CLI itself had no idea what
version it was supposed to be — so an install could sit 30 releases behind for
weeks while its hooks fired thousands of times a day, and the user hit bugs
fixed a fortnight earlier.

Now the CLI settles it itself. Every API response carries the release the
backend expects (X-Stash-Cli-Latest); when the running install is older, we
upgrade *that* install — resolved from sys.executable rather than assumed to be
uv's — in a detached process, and say so in one line. That covers a bare
terminal, every agent harness, and the case where PATH resolves to a different
copy than the one uv manages.

An editable checkout (`uv pip install -e .`) is never upgraded: its version is
the developer's business, and clobbering it would delete their work. It gets
the notice and nothing else.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from importlib.metadata import distribution, version
from pathlib import Path

LATEST_VERSION_HEADER = "X-Stash-Cli-Latest"

_STAMP_PATH = Path.home() / ".stash" / "upgrade_attempt.json"

# One attempt per hour per release. The normal case needs no throttle at all —
# the upgrade lands and the next run is current — so this only bounds the
# broken case (no uv, no network, read-only install) to something that can't
# storm. A newly published release retries immediately regardless of the clock.
_THROTTLE_SECONDS = 3600

_INSTALLER = "curl -LsSf https://joinstash.ai/install.sh | sh"

_enabled = True


def disable() -> None:
    """Turn self-upgrade off for this process. For long-lived processes only
    (the session watcher): replacing the environment under an interpreter that
    imports lazily for the next several hours is how you get an ImportError
    halfway through someone's session."""
    global _enabled
    _enabled = False


@lru_cache(maxsize=1)
def current_version() -> str:
    """Cached: this runs on every API response, and a process cannot change the
    version it is running."""
    return version("stashai")


def note_latest(latest: str) -> None:
    """Handle the release header from an API response. Cheap and silent in the
    common case: a current install compares two strings and returns."""
    if not _enabled or not latest:
        return
    current = current_version()
    if not _is_older(current, latest):
        return
    if not _claim_attempt(latest):
        return
    _upgrade(current, latest)


def _is_older(have: str, want: str) -> bool:
    return _parts(have) < _parts(want)


def _parts(release: str) -> tuple[int, ...]:
    """Dotted release as a comparable tuple. Non-numeric trailers ('.dev0',
    '+local') drop out, so a locally built wheel compares on its release
    numbers instead of raising mid-request."""
    return tuple(int(part) for part in release.split(".") if part.isdigit())


def _claim_attempt(latest: str) -> bool:
    """True when this process should attempt the upgrade now. Writing the stamp
    before spawning means a failed attempt still counts — the throttle exists to
    bound failure, not success."""
    stamp = _read_stamp()
    attempted_at = stamp.get("at", 0) if stamp.get("version") == latest else 0
    if time.time() - attempted_at < _THROTTLE_SECONDS:
        return False
    _STAMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STAMP_PATH.write_text(json.dumps({"version": latest, "at": time.time()}))
    return True


def _read_stamp() -> dict:
    """The last attempt we made. A missing or unreadable file means we have
    never attempted this release, which is the state we want to act on."""
    if not _STAMP_PATH.is_file():
        return {}
    try:
        return json.loads(_STAMP_PATH.read_text())
    except (OSError, ValueError):
        return {}


def _upgrade(current: str, latest: str) -> None:
    if _is_editable():
        _say(
            f"this checkout is {current}; the current release is {latest}. "
            "Editable installs are left alone — `git pull` when you want the fix."
        )
        return

    command = _upgrade_command()
    if command is None:
        _say(
            f"{current} is behind {latest}, but uv is not installed so the "
            f"upgrade can't run. Reinstall with: {_INSTALLER}"
        )
        return

    # All three fds are detached: a background process holding the hook's
    # stdout keeps the agent waiting on that pipe for the whole upgrade.
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as e:
        # Spawning can genuinely fail on a user's machine (binary removed
        # mid-flight, noexec mount). Say so rather than leave them wondering
        # why the version never moves.
        _say(f"{current} is behind {latest} and the upgrade could not start ({e}).")
        return
    _say(f"upgrading {current} → {latest} in the background; this run used {current}.")


def _upgrade_command() -> list[str] | None:
    """How to upgrade *this* install. The kind is decided by where the running
    interpreter lives, so a pip install under pyenv is upgraded by that pip
    instead of by uv quietly refreshing a copy nobody runs."""
    if _is_uv_tool():
        uv = _find_uv()
        return [uv, "tool", "install", "--quiet", "stashai@latest"] if uv else None
    return [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "stashai"]


def _is_uv_tool() -> bool:
    """uv drops a receipt in every tool environment it creates.

    Recognising the environment by its path shape instead looks fine on a
    default install and breaks the moment UV_TOOL_DIR is set — sending a uv
    install down the pip branch, where a uv environment has no pip and the
    upgrade fails in a detached process nobody can see. The receipt is a fact
    about this install rather than a guess about its layout."""
    return (Path(sys.prefix) / "uv-receipt.toml").is_file()


def _is_editable() -> bool:
    """PEP 610 records how a distribution was installed; `pip install -e .`
    writes dir_info.editable."""
    raw = distribution("stashai").read_text("direct_url.json")
    if raw is None:
        return False
    return bool(json.loads(raw).get("dir_info", {}).get("editable"))


def _find_uv() -> str | None:
    """uv, whether or not it is on this process's PATH. Agent hooks run with a
    minimal PATH, which is how the previous upgrade path silently did nothing
    for anyone whose uv came from Homebrew."""
    found = shutil.which("uv")
    if found:
        return found
    candidates = [
        Path.home() / ".local/bin/uv",
        Path.home() / ".cargo/bin/uv",
        Path("/opt/homebrew/bin/uv"),
        Path("/usr/local/bin/uv"),
    ]
    for candidate in candidates:
        if os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _say(message: str) -> None:
    """stderr, always: hook stdout carries the JSON payload the agent parses."""
    print(f"stash: {message}", file=sys.stderr)
