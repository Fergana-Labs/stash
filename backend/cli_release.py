"""The stash CLI release clients should be running.

Sourced from the repo's pyproject version — the same number publish.yml pushes
to PyPI — so cutting a release stays a one-line edit. Served on every response
as X-Stash-Cli-Latest; a CLI that finds itself older upgrades in the background
(see stashai/self_upgrade.py).

A missing or malformed version raises at import: a backend that can't name a
release clients can compare would silently stop upgrading every client on the
fleet, which is the failure this whole path exists to end.
"""

import re
import tomllib
from pathlib import Path

LATEST_VERSION_HEADER = "X-Stash-Cli-Latest"

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _read_release(pyproject: Path) -> str:
    with pyproject.open("rb") as f:
        release = tomllib.load(f)["project"]["version"]
    # A pre-release ("0.1.365rc1") is PEP-440-valid and would publish fine,
    # but clients compare plain dotted numbers and would read it as *older* —
    # silently freezing every install until the next plain release.
    if not re.fullmatch(r"\d+(\.\d+)*", release):
        raise ValueError(
            f"pyproject version {release!r} is not a plain dotted release; "
            "clients cannot compare it and would stop upgrading."
        )
    return release


LATEST_CLI_VERSION: str = _read_release(_PYPROJECT)
