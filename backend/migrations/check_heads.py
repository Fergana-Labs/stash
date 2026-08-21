"""Fail unless every migration has a unique revision id and the graph has one head.

Two PRs that each add a migration on top of the same parent merge cleanly in
git but leave alembic with two heads (or two files claiming the same revision
id) — and every `alembic upgrade head` after that refuses to run: deploys,
fresh test databases, local setups. That race shipped as #712 + #713 (both
"0125") and again as #965 + #1040 (both "0185"); this check turns it into a
red PR check instead of a broken deploy. The workflow merges current main
before running it, because PR CI otherwise checks a merge ref built when the
branch last pushed — #965 passed this check against a base from ten days
earlier that did not yet contain the migration it collided with.

Run from the repo root: `python backend/migrations/check_heads.py`.
Needs only alembic installed — no database, no backend settings.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util import CommandError

FIX = (
    "Fix: renumber this branch's migration to sit on main's current head — "
    "bump its filename/revision to the next number and set down_revision to "
    "the current head, then rebase."
)

VERSIONS = Path(__file__).parent / "versions"
REVISION_LINE = re.compile(r'^revision = "([^"]+)"', re.MULTILINE)


def duplicate_revision_ids() -> dict[str, list[str]]:
    """Revision ids claimed by more than one file, mapped to those filenames.

    Alembic keys its script map by revision id, so a duplicate silently drops
    one of the two files instead of erroring — worth naming explicitly, since
    the head count alone does not say which files collided.
    """
    files_by_id: dict[str, list[str]] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        match = REVISION_LINE.search(path.read_text())
        if not match:
            print(f'{path.name} has no `revision = "..."` line', file=sys.stderr)
            sys.exit(1)
        files_by_id.setdefault(match.group(1), []).append(path.name)
    return {rev: files for rev, files in files_by_id.items() if len(files) > 1}


def main() -> int:
    duplicates = duplicate_revision_ids()
    if duplicates:
        for revision, files in sorted(duplicates.items()):
            print(
                f"revision id {revision} is claimed by {' and '.join(files)}; "
                f"alembic keeps only one of them.\n{FIX}",
                file=sys.stderr,
            )
        return 1

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    try:
        heads = script.get_heads()
    except CommandError as e:
        # A down_revision pointing at a revision id no file defines fails
        # before heads can even be computed.
        print(f"migration graph is broken: {e}\n{FIX}", file=sys.stderr)
        return 1
    if len(heads) != 1:
        print(
            f"migration graph has {len(heads)} heads ({', '.join(sorted(heads))}); "
            f"every alembic upgrade will refuse to run.\n{FIX}",
            file=sys.stderr,
        )
        return 1
    print(f"migration graph ok: single head {heads[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
