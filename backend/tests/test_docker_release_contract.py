"""Release contract for the self-host Docker images.

These are static source-level guards: they read the compose files and
Dockerfiles as plain text (no YAML library is a declared dependency, and CI
installs only backend/requirements*.txt). They encode the operator directive
and the compose-merge invariant so neither can silently regress:

- pi must never be installed or referenced inside either image.
- every service key a local override declares must also exist in the prod
  file, so an override can never introduce a service with no image (the
  collab/#982 bug class).

The literal `docker compose config -q` / `up -d` reproduction is deliberately
NOT here: CI has no compose contract for it, and a conditional skip would
weaken the assertion. Those commands are run by the release executor with the
real exit status recorded.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.local.yml"
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"

# The operative pi-absence gate. A broad `pi|npm|node` alternation can never
# return zero: it matches `pip install`, `libatspi2.0-0`, and the mandatory
# node:20-alpine / npm ci lines that build a Next.js image. This narrow
# pattern names only real pi artifacts.
PI_REFERENCE = re.compile(r"earendil-works/pi|/pi/|pi install|pi-coding-agent", re.IGNORECASE)

# A service key: exactly two spaces of indent under the top-level `services:`
# mapping. Nested properties (four+ spaces) never match this shape.
SERVICE_KEY = re.compile(r"^  ([^\s#][^:]*):")


def service_keys(path: Path) -> list[str]:
    """Collect the service names declared under a top-level `services:` block."""
    keys: list[str] = []
    in_services = False
    for line in path.read_text().splitlines():
        if line.startswith("services:"):
            in_services = True
            continue
        if in_services:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" "):
                # A new top-level key ends the services block.
                break
            match = SERVICE_KEY.match(line)
            if match:
                keys.append(match.group(1))
    return keys


def test_no_override_only_services():
    """Every local override service must also exist in the prod file.

    Compose merge creates a service from an override that prod does not
    declare, then rejects it for lacking an image/build — the collab/#982
    bug class. This generalizes the fix so no override can reintroduce it.
    `caddy` is legitimate because prod declares it.
    """
    prod = set(service_keys(PROD_COMPOSE))
    local = set(service_keys(LOCAL_COMPOSE))
    assert prod, "prod compose must declare services"
    orphans = local - prod
    assert orphans == set(), f"override declares services with no prod entry: {sorted(orphans)}"


def test_compose_files_do_not_mention_collab():
    """Neither compose file may reference the deleted collab service or 3458."""
    for path in (PROD_COMPOSE, LOCAL_COMPOSE):
        text = path.read_text()
        assert "collab" not in text, f"{path.name} still mentions collab"
        assert "3458" not in text, f"{path.name} still mentions port 3458"


def test_dockerfiles_install_no_pi():
    """Operator directive: the Docker image must not install pi at all."""
    for path in (BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE):
        offenders = [line for line in path.read_text().splitlines() if PI_REFERENCE.search(line)]
        assert offenders == [], f"{path.name} references pi: {offenders}"
