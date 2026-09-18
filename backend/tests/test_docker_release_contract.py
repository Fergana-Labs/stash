"""Release contract for the self-host Docker setup.

Both invariants are read from the files as plain text: no YAML library is a
declared dependency, and CI installs only backend/requirements*.txt.

The compose-merge rule exists because the laptop override once declared a
`collab` service the self-host base file did not, which made the exact
two-file command published in the README fail with:

    service "collab" has neither an image nor a build context specified

The pin rule exists because `bump-plugin-version.yml` rewrites the five GHCR
tags alongside the project version, and a bump that reaches pyproject without
that rewrite leaves self-hosters pulling an older build than the repo ships.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.local.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# A service key is exactly two spaces of indent under the `services:` mapping;
# nested properties are indented deeper and never match.
SERVICE_KEY = re.compile(r"^  ([^\s#][^:]*):")
GHCR_PIN = re.compile(r"ghcr\.io/fergana-labs/(stash-[a-z]+):(\S+)")


def service_keys(path: Path) -> set[str]:
    lines = path.read_text().splitlines()
    if "services:" not in lines:
        return set()
    start = lines.index("services:") + 1
    keys = set()
    for line in lines[start:]:
        if line.strip() and not line.startswith(" "):
            break
        match = SERVICE_KEY.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def test_override_declares_no_service_the_base_lacks():
    """Compose creates a service from an override the base file never declares.

    The created service has no image and no build context, so `up` rejects the
    whole project. An override may only change services the base file defines.
    """
    base = service_keys(PROD_COMPOSE)
    assert base, "docker-compose.prod.yml must declare services"
    orphans = service_keys(LOCAL_COMPOSE) - base
    assert orphans == set(), f"override-only services: {sorted(orphans)}"


def test_compose_pins_match_the_released_version():
    """The five self-host pins must name the version this repo actually ships.

    Pins carry no `v` prefix: the git tag does, the published image tags do not.
    """
    with PYPROJECT.open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    pins = GHCR_PIN.findall(PROD_COMPOSE.read_text())
    assert pins, "docker-compose.prod.yml must pin the release images"
    assert {image for image, _ in pins} == {"stash-backend", "stash-frontend"}
    for image, tag in pins:
        assert not tag.startswith("v"), f"{image} pinned with a v-prefixed tag: {tag}"
        assert tag == version, f"{image} pinned to {tag}, but the project version is {version}"
