"""Migrations must use asyncpg's parameter style.

The app runs migrations at boot over asyncpg, which binds `$1`, `$2` — not
psycopg2's `%s`. A `%s` in a data migration is invisible until the loop it
sits in finally has a row to touch, and then it takes down the backend on
startup. 0169 shipped with exactly that latent bug: its loop only runs for
users who already had a Bookmarks table, so every test and dev DB skipped it.
"""

import re
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
# A `%s` only matters when it's a query parameter. Requiring a SQL verb on the
# same line keeps logging format strings ("0036 step: %s") out of the results.
_PLACEHOLDER = re.compile(r"%s")
_SQL_VERB = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|ALTER|CREATE|DROP)\b")


@pytest.mark.parametrize("path", sorted(VERSIONS.glob("*.py")), ids=lambda p: p.stem)
def test_migration_uses_asyncpg_placeholders(path: Path):
    offenders = [
        line.strip()
        for line in path.read_text().splitlines()
        if _PLACEHOLDER.search(line) and _SQL_VERB.search(line)
    ]
    assert not offenders, (
        f"{path.name} uses psycopg-style %s placeholders; asyncpg needs $1, $2:\n"
        + "\n".join(offenders)
    )
