"""The backend names the current CLI release on every response.

This header is the only thing that tells a stale install it is stale — without
it the CLI has no idea, which is how an install sat weeks behind while its
session-start upgrade ran thousands of times. It rides on responses clients
already make, so it must be present unconditionally, including on requests that
carry no valid auth.
"""

import tomllib
from pathlib import Path

import pytest

from backend import cli_release

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_every_response_names_the_current_release(client):
    response = await client.get("/health")
    assert response.headers["X-Stash-Cli-Latest"] == cli_release.LATEST_CLI_VERSION


@pytest.mark.asyncio
async def test_error_responses_carry_it_too(client):
    """A CLI whose token expired still gets 401s — and still deserves to learn
    it is stale, since upgrading may be what fixes it."""
    response = await client.get("/api/v1/me/files")
    assert response.status_code in (401, 403)
    assert response.headers["X-Stash-Cli-Latest"] == cli_release.LATEST_CLI_VERSION


def test_release_is_the_published_version():
    """One source of truth: the number publish.yml ships to PyPI. If these
    diverge, clients are told to chase a release that does not exist."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        assert cli_release.LATEST_CLI_VERSION == tomllib.load(f)["project"]["version"]


def test_a_prerelease_version_is_refused_at_import(tmp_path):
    """Clients compare plain dotted numbers, so '0.1.365rc1' would read as
    *older* than what they run, and every install would go quiet. The backend
    must refuse to serve it rather than serve it silently."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "0.1.365rc1"\n')
    with pytest.raises(ValueError, match="not a plain dotted release"):
        cli_release._read_release(pyproject)
