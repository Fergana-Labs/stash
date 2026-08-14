"""The stash CLI release clients should be running.

Sourced from the repo's pyproject version — the same number publish.yml pushes
to PyPI — so cutting a release stays a one-line edit. Served on every response
as X-Stash-Cli-Latest; a CLI that finds itself older upgrades in the background
(see stashai/self_upgrade.py).

Missing pyproject.toml raises at import: a backend that can't name the current
release would silently stop upgrading every client on the fleet, which is the
failure this whole path exists to end.
"""

import tomllib
from pathlib import Path

LATEST_VERSION_HEADER = "X-Stash-Cli-Latest"

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

with _PYPROJECT.open("rb") as _f:
    LATEST_CLI_VERSION: str = tomllib.load(_f)["project"]["version"]
