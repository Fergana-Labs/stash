"""Fail unless the migration graph has exactly one head.

Two PRs that each add a migration on top of the same parent merge cleanly in
git but leave alembic with two heads (or two files claiming the same revision
id) — and every `alembic upgrade head` after that refuses to run: deploys,
fresh test databases, local setups. That exact race shipped as #712 + #713
(both "0125") and broke main for an hour; this check turns it into a red PR
check instead of a broken deploy, because PR CI runs against the merge ref.

Run from the repo root: `python backend/migrations/check_heads.py`.
Needs only alembic installed — no database, no backend settings.
"""

from __future__ import annotations

import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util import CommandError

FIX = (
    "Fix: renumber this branch's migration to sit on main's current head — "
    "bump its filename/revision to the next number and set down_revision to "
    "the current head, then rebase."
)


def main() -> int:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    try:
        heads = script.get_heads()
    except CommandError as e:
        # Two files claiming the same revision id fail before heads can even
        # be computed.
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
