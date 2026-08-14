"""The backend names the CLI release every client should be on.

This header is the only thing that tells a stale install to upgrade — without
it the CLI has no idea it is behind, which is exactly how installs sat 30
releases back for weeks. It rides on responses clients already make, so it must
be present unconditionally, including on requests that carry no auth.
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
    it is stale, since an upgrade may be what fixes it."""
    response = await client.get("/api/v1/me/files")
    assert response.status_code in (401, 403)
    assert response.headers["X-Stash-Cli-Latest"] == cli_release.LATEST_CLI_VERSION


def test_release_is_the_published_version():
    """One source of truth: the number publish.yml ships to PyPI. If these ever
    diverge, clients chase a release that does not exist."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        assert cli_release.LATEST_CLI_VERSION == tomllib.load(f)["project"]["version"]
