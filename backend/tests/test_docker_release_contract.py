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

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.local.yml"
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
PYPROJECT = REPO_ROOT / "pyproject.toml"
PLUGIN_MANIFEST = REPO_ROOT / "plugins" / "claude-plugin" / ".claude-plugin" / "plugin.json"
MARKETPLACE_MANIFEST = REPO_ROOT / ".claude-plugin" / "marketplace.json"

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


# A GHCR image reference to one of our two release images, capturing its tag.
# This mirrors the same shape the (currently inert) bump automation rewrites.
GHCR_PIN = re.compile(r"ghcr\.io/fergana-labs/(stash-[a-z]+):(\S+)")


def cli_version() -> str:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def test_compose_pins_track_the_cli_version():
    """Every GHCR pin in the prod compose file must equal the CLI version.

    Since the bump automation can no longer land its edits, this test is the
    only surviving enforcement that the five self-host pins and the CLI
    release version stay in lockstep. Pins are bare (no `v` prefix): the git
    tag carries the `v`, the published image tags do not.
    """
    version = cli_version()
    pins = GHCR_PIN.findall(PROD_COMPOSE.read_text())
    assert pins, "prod compose must pin our release images"
    images = {image for image, _ in pins}
    assert images == {"stash-backend", "stash-frontend"}, f"unexpected pinned images: {images}"
    for image, tag in pins:
        assert not tag.startswith("v"), f"{image} pinned with a v-prefixed tag: {tag}"
        assert tag == version, f"{image} pinned to {tag}, but CLI version is {version}"


def test_plugin_manifests_agree_with_each_other():
    """The Claude plugin manifest and the marketplace entry must agree.

    This is the invariant the bump automation enforced by copying the plugin
    number into the marketplace file; keep it asserted now that the
    automation cannot land edits.
    """
    plugin = json.loads(PLUGIN_MANIFEST.read_text())["version"]
    marketplace = json.loads(MARKETPLACE_MANIFEST.read_text())["plugins"][0]["version"]
    assert plugin == marketplace, f"plugin.json {plugin} != marketplace {marketplace}"


def test_plugin_manifest_is_not_the_cli_version():
    """The plugin/marketplace pair is an independent, higher sequence.

    It is bumped on its own schedule and is NOT part of the CLI release, so
    it must not be expected to equal the pyproject version. Asserted so a
    future hand-bump that conflates the two is caught.
    """
    plugin = json.loads(PLUGIN_MANIFEST.read_text())["version"]
    assert plugin != cli_version(), (
        f"plugin manifest {plugin} collides with the CLI version; "
        "the marketplace sequence is independent"
    )


def test_dockerfiles_install_no_pi():
    """Operator directive: the Docker image must not install pi at all."""
    for path in (BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE):
        offenders = [line for line in path.read_text().splitlines() if PI_REFERENCE.search(line)]
        assert offenders == [], f"{path.name} references pi: {offenders}"
