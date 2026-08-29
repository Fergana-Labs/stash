"""The collab sidecar is gone (PR #982); the repo must stop describing it.

The Yjs/Hocuspocus collaboration service was deleted — `collab/` and
`backend/routers/collab.py` no longer exist and migration 0182 dropped its
table — yet the architecture document and the self-hosting files kept naming
it. One of those stale references (`collab:` in docker-compose.local.yml) made
the exact self-host command README.md tells you to run fail outright with
`service "collab" has neither an image nor a build context specified`.

These are static source-level guards in the shape of
test_cli_release_header.py: they read repo files as plain text and assert the
invariant, so no one can quietly re-add a service description for something
that was deleted. docs/ is deliberately NOT scanned — docs/security-readiness.md
is owned by STAS-143, and asserting on a surface this task does not clean would
go RED whichever of the two independent PRs merges first.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ARCHITECTURE_DOC = REPO_ROOT / "ARCHITECTURE.md"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Surfaces that advertise what actually runs. docs/ is absent on purpose (see
# the module docstring): STAS-143 owns the collab lines there.
DEPLOYMENT_SURFACES = (
    ARCHITECTURE_DOC,
    REPO_ROOT / "render.yaml",
    ENV_EXAMPLE,
    REPO_ROOT / "docker-compose.prod.yml",
    REPO_ROOT / "docker-compose.local.yml",
)

ROUTER_REFERENCE = re.compile(r"backend/routers/([A-Za-z0-9_-]+\.py)")
COLLAB_MENTION = re.compile(r"\bcollab\b", re.IGNORECASE)


def test_architecture_doc_names_only_existing_routers():
    """Every router file ARCHITECTURE.md names must exist in the tree.

    The reverse assertion — every real router is documented — is deliberately
    absent: most real routers are undocumented today, so it would fail for
    unrelated reasons and bury the one discrepancy this guard exists to catch.
    """
    text = ARCHITECTURE_DOC.read_text()
    missing = sorted(
        name
        for name in set(ROUTER_REFERENCE.findall(text))
        if not (REPO_ROOT / "backend" / "routers" / name).is_file()
    )
    assert missing == [], f"ARCHITECTURE.md names routers that do not exist: {missing}"


def test_deployment_surfaces_do_not_mention_the_deleted_collab_service():
    """No surface describing the running system may name collab or port 3458.

    Both were properties of the deleted sidecar. The word-boundary match keeps
    real prose (`collaboration`) and the unrelated `prosemirror-collab` npm
    library out of scope; the port is checked plainly because a mapping such as
    `3458:3458` has no word boundary to anchor on.
    """
    offenders: list[str] = []
    for path in DEPLOYMENT_SURFACES:
        lines = path.read_text().splitlines()
        hits = [
            f"{path.name}:{number} {line.strip()}"
            for number, line in enumerate(lines, start=1)
            if COLLAB_MENTION.search(line) or "3458" in line
        ]
        offenders.extend(hits)
    assert offenders == [], f"deleted collab service is still advertised at: {offenders}"


def test_env_example_declares_no_dead_backend_url():
    """.env.example must not advertise a variable that nothing reads.

    BACKEND_URL sat under the collab header, documented as "used by the collab
    sidecar". With the sidecar gone it has zero consumers repo-wide, and
    docker-compose.prod.yml passes the differently-named BACKEND_INTERNAL_URL
    instead. Project rules forbid keeping a dead key as an alias or fallback,
    so the invariant to protect is that it stays deleted.
    """
    dead = [
        line for line in ENV_EXAMPLE.read_text().splitlines() if line.startswith("BACKEND_URL=")
    ]
    assert dead == [], f".env.example declares unread variables: {dead}"
