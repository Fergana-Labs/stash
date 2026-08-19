"""Tell the user when their `stash` is behind the current release.

Every API response carries the release the backend was built from
(X-Stash-Cli-Latest). When the running install is older, we print one line to
stderr and stop. We deliberately do not upgrade anything from here: the agent
plugins already run an upgrade at session start, and a warning that is always
true is worth more than an upgrade that fails somewhere nobody can see.

That is the whole point. A CLI could sit weeks behind while its session-start
upgrade ran thousands of times, because nothing ever compared the running
version to anything or reported it to the server — so the failure was invisible
to the user and to us. Printing the comparison, and sending the version with
CLI telemetry, turns "why is this install stale?" into a question we can answer
from the machines it actually happens on, instead of guessing at causes.

`upgrade_command()` is what `stash upgrade` runs. It resolves the install kind
from the running interpreter, so a pip install under pyenv is upgraded by its
own pip instead of by uv refreshing a copy that is not the one on PATH.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import sysconfig
from functools import lru_cache
from importlib.metadata import distribution, version
from pathlib import Path

LATEST_VERSION_HEADER = "X-Stash-Cli-Latest"

INSTALLER = 'bash -c "$(curl -fsSL https://joinstash.ai/install)"'

_warned = False


@lru_cache(maxsize=1)
def current_version() -> str:
    """Cached: this runs on every API response, and a process cannot change the
    version it is running."""
    return version("stashai")


def note_latest(latest: str) -> None:
    """Handle the release header from an API response. At most one line per
    process: a single command can make a dozen requests, and the user needs to
    read this once."""
    global _warned
    if not latest or _warned:
        return
    current = current_version()
    if not _is_older(current, latest):
        return
    _warned = True
    if is_editable():
        _say(
            f"this checkout is {current}; the current release is {latest}. `git pull` to update it."
        )
        return
    _say(
        f"stash {current} is out of date; the current release is {latest}. "
        "Run `stash upgrade` to update."
    )


def _is_older(have: str, want: str) -> bool:
    return _parts(have) < _parts(want)


def _parts(release: str) -> tuple[int, ...]:
    """Dotted release as a comparable tuple. Non-numeric trailers ('.dev0',
    '+local') drop out, so a locally built wheel compares on its release
    numbers instead of raising mid-request."""
    return tuple(int(part) for part in release.split(".") if part.isdigit())


def upgrade_command() -> list[str] | None:
    """How to upgrade *this* install, or None when it has no working upgrader.
    The kind is decided by where the running interpreter lives, so a pip
    install under pyenv is upgraded by that pip instead of by uv quietly
    refreshing a copy nobody runs."""
    if _is_uv_tool():
        uv = _find_uv()
        return [uv, "tool", "install", "--quiet", "stashai@latest"] if uv else None
    if not _has_pip():
        # uv venvs ship without pip, so `python -m pip` there fails on a
        # missing module rather than on anything the user can act on.
        return None
    command = [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "stashai"]
    if _is_externally_managed():
        # PEP 668 pythons (Debian's, the Fly Sprites we provision) refuse plain
        # installs; these are the flags our own sprite setup installs with
        # (backend/services/sprite_service.py).
        command += ["--user", "--break-system-packages"]
    return command


def _has_pip() -> bool:
    return importlib.util.find_spec("pip") is not None


def _is_externally_managed() -> bool:
    """The PEP 668 marker: this python's distributor forbids installing into it
    without an explicit override."""
    return (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").is_file()


def _is_uv_tool() -> bool:
    """uv drops a receipt in every tool environment it creates.

    Recognising the environment by the shape of its path instead looks right on
    a default install and breaks the moment UV_TOOL_DIR is set, which would
    send a uv install down the pip branch — where a uv environment has no pip.
    The receipt is a fact about this install rather than a guess at its layout."""
    return (Path(sys.prefix) / "uv-receipt.toml").is_file()


def is_editable() -> bool:
    """PEP 610 records how a distribution was installed; `pip install -e .`
    writes dir_info.editable."""
    raw = distribution("stashai").read_text("direct_url.json")
    if raw is None:
        return False
    return bool(json.loads(raw).get("dir_info", {}).get("editable"))


def _find_uv() -> str | None:
    """uv, whether or not it is on this process's PATH. Agent hooks run with a
    minimal PATH, so a uv installed by Homebrew is invisible to `which`."""
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
