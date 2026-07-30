"""The migration graph must have exactly one head.

Two PRs merged the same day each added a `0174`, both parented on `0173`.
Alembic could not resolve the graph, so `alembic upgrade head` — which
`database.py` runs at boot — failed, and the backend exited with status 3 on
every deploy. Prod sat on the previous release until someone noticed.

Nothing in the test suite caught it because each PR's migrations were fine in
isolation; only the merge was broken. So this asserts a property of the
directory rather than of any one file.
"""

import re
from collections import Counter
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
_REVISION = re.compile(r'^revision = "([^"]+)"', re.M)
_DOWN = re.compile(r'^down_revision = (?:"([^"]+)"|None)', re.M)


def _graph() -> dict[str, str | None]:
    graph: dict[str, str | None] = {}
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = _REVISION.search(text)
        if not rev:
            continue
        down = _DOWN.search(text)
        graph[rev.group(1)] = down.group(1) if down else None
    return graph


def test_no_duplicate_revision_ids():
    """Two files claiming the same revision is the failure mode that took
    prod down; alembic only warns about it, then errors later."""
    revisions = []
    for path in VERSIONS.glob("*.py"):
        match = _REVISION.search(path.read_text())
        if match:
            revisions.append(match.group(1))

    duplicates = [rev for rev, count in Counter(revisions).items() if count > 1]
    assert not duplicates, (
        f"revision id(s) used by more than one migration: {duplicates}. "
        "Two branches picked the same number — renumber the later one and "
        "re-chain its down_revision."
    )


def test_exactly_one_head():
    """A head is a revision nothing points at. More than one means the graph
    forked and `upgrade head` is ambiguous."""
    graph = _graph()
    parents = {down for down in graph.values() if down}
    heads = sorted(set(graph) - parents)
    assert len(heads) == 1, f"expected one head, found {heads}"


def test_every_parent_exists():
    """A down_revision pointing at a deleted or renamed migration breaks the
    chain just as hard, and is the easy mistake when renumbering."""
    graph = _graph()
    missing = {rev: down for rev, down in graph.items() if down is not None and down not in graph}
    assert not missing, f"down_revision points at a revision that doesn't exist: {missing}"
