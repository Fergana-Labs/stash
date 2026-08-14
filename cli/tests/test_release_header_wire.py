"""Both HTTP clients must read the release header off every response.

The upgrade logic is worthless if nothing feeds it. The CLI client covers
`stash <command>`; the plugin client covers hook traffic, which for an active
user is thousands of requests a day and the fastest way a stale install hears
about a new release.
"""

from __future__ import annotations

import httpx
import pytest

from cli.client import StashClient
from stashai import self_upgrade
from stashai.plugin.stash_client import StashClient as PluginClient


@pytest.fixture
def seen(monkeypatch) -> list[str]:
    latest: list[str] = []
    monkeypatch.setattr(self_upgrade, "note_latest", latest.append)
    return latest


def _transport(headers: dict[str, str]) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json={}, headers=headers))


def test_cli_client_reads_the_header(monkeypatch, seen):
    client = StashClient("https://example.test", api_key="k")
    client._http = httpx.Client(
        base_url="https://example.test",
        transport=_transport({self_upgrade.LATEST_VERSION_HEADER: "0.1.364"}),
    )

    client._get("/api/v1/me/files")

    assert seen == ["0.1.364"]


def test_plugin_client_reads_the_header(monkeypatch, seen):
    client = PluginClient("https://example.test", api_key="k")
    client._http = httpx.Client(
        base_url="https://example.test",
        transport=_transport({self_upgrade.LATEST_VERSION_HEADER: "0.1.364"}),
    )

    client._get("/api/v1/me/whoami")

    assert seen == ["0.1.364"]


def test_a_backend_without_the_header_says_nothing(monkeypatch, seen):
    """Self-hosters run their own backend; absence must read as 'no opinion',
    not as a version to chase."""
    client = StashClient("https://example.test", api_key="k")
    client._http = httpx.Client(base_url="https://example.test", transport=_transport({}))

    client._get("/api/v1/me/files")

    assert seen == [""]
