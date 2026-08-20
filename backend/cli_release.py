"""The stash CLI release clients are told about.

Sourced from the repo's pyproject version — the same number publish.yml pushes
to PyPI — so cutting a release stays a one-line edit. Served on every response
as X-Stash-Cli-Latest; a CLI that finds itself older says so (see
stashai/release.py). Note this is the version of the build this backend was cut
from, which is the newest published release only because a merge to main
deploys the backend and publishes the CLI from the same commit.

A missing or malformed version raises at import: a backend that cannot name a
release clients can compare would silently stop warning anyone, which is the
failure this path exists to end.
"""

import re
import tomllib
from pathlib import Path

LATEST_VERSION_HEADER = "X-Stash-Cli-Latest"

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _read_release(pyproject: Path) -> str:
    with pyproject.open("rb") as f:
        release = tomllib.load(f)["project"]["version"]
    # A pre-release ("0.1.365rc1") is PEP-440-valid and would publish fine, but
    # clients compare plain dotted numbers and would read it as *older* —
    # silently muting the warning until the next plain release.
    if not re.fullmatch(r"\d+(\.\d+)*", release):
        raise ValueError(
            f"pyproject version {release!r} is not a plain dotted release; "
            "clients cannot compare it and would stop noticing new releases."
        )
    return release


LATEST_CLI_VERSION: str = _read_release(_PYPROJECT)
