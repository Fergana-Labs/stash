"""Tests for the MCP server tool functions against the currently shipped API.

Uses the self-contained _FakeClient monkeypatch pattern (mirrored from
test_sources_cli.py): patch mcp_server._client to inject a fake StashClient,
then verify the right client method is called with the right arguments and the
returned JSON envelope matches the shipped contract.

The shipped cli/mcp_server.py surface (STAS-086 reconciliation):
- stash_search maps its seven parameters onto StashClient.search_sources and
  returns the raw {"results", "has_more"} envelope via _json — client
  exceptions propagate (there is no try/except).
- stash_vfs maps onto StashClient.run_vfs(script, cwd=cwd) and returns
  {stdout, stderr, exit_code} via _json; a non-zero exit_code is a valid shell
  result (e.g. grep found nothing), not an error.
"""

import json

import httpx
import pytest

from cli import mcp_server
from cli.client import split_source_tokens


def _parse(result_str: str) -> object:
    """Parse the JSON string returned by an MCP tool."""
    return json.loads(result_str)


class _FakeClient:
    """Records every search_sources / run_vfs call made by the tools."""

    def __init__(self, calls: list):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def search_sources(
        self,
        query,
        source=None,
        include_sources=None,
        exclude_sources=None,
        limit=20,
        modified_after=None,
        modified_before=None,
    ):
        self._calls.append(
            (
                "search",
                query,
                source,
                include_sources,
                exclude_sources,
                limit,
                modified_after,
                modified_before,
            )
        )
        return {
            "results": [
                {
                    "source": "files",
                    "ref": "p1",
                    "name": "Runbook",
                    "snippet": "deploy instructions",
                },
            ],
            "has_more": False,
        }

    def run_vfs(self, script: str, cwd: str = "/") -> dict:
        self._calls.append(("vfs", script, cwd))
        return {
            "stdout": f"contents of {script} at {cwd}",
            "stderr": "",
            "exit_code": 0,
        }


def _wire(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(mcp_server, "_client", lambda: _FakeClient(calls))
    return calls


def test_split_source_tokens() -> None:
    """split_source_tokens is the shared helper the tool uses for its
    comma-separated include/exclude params; its contract is reused verbatim."""
    assert split_source_tokens("") is None
    assert split_source_tokens(" , ") is None
    assert split_source_tokens("files") == ["files"]
    assert split_source_tokens("files, gmail") == ["files", "gmail"]


class TestStashSearch:
    """Tests for the shipped stash_search MCP tool.

    The tool is a thin wrapper: it maps its seven parameters onto
    StashClient.search_sources and returns the raw {"results", "has_more"}
    search envelope via _json — with no query/source/count wrapper keys and no
    try/except, so client exceptions propagate (fail-loud, per AGENTS.md).
    """

    def test_search_everything_passes_source_none(self, monkeypatch) -> None:
        """No source filter -> source=None, empty source filters -> None."""
        calls = _wire(monkeypatch)
        result_str = mcp_server.stash_search("migration")
        result = _parse(result_str)

        assert calls == [("search", "migration", None, None, None, 20, None, None)]
        assert result == {
            "results": [
                {
                    "source": "files",
                    "ref": "p1",
                    "name": "Runbook",
                    "snippet": "deploy instructions",
                },
            ],
            "has_more": False,
        }

    def test_search_scoped_to_source(self, monkeypatch) -> None:
        """source="src-abc" passed through untouched as the client keyword."""
        calls = _wire(monkeypatch)
        mcp_server.stash_search("rotate", source="src-abc")
        assert calls == [("search", "rotate", "src-abc", None, None, 20, None, None)]

    def test_search_splits_include_exclude_sources(self, monkeypatch) -> None:
        """Comma-separated include/exclude params -> token lists via
        split_source_tokens ("files, gmail" -> ["files", "gmail"])."""
        calls = _wire(monkeypatch)
        mcp_server.stash_search(
            "migration", include_sources="files, gmail", exclude_sources="slack"
        )
        assert calls == [
            ("search", "migration", None, ["files", "gmail"], ["slack"], 20, None, None)
        ]

    def test_search_forwards_limit(self, monkeypatch) -> None:
        """limit passed through as the client keyword."""
        calls = _wire(monkeypatch)
        mcp_server.stash_search("test", limit=5)
        assert calls == [("search", "test", None, None, None, 5, None, None)]

    def test_search_unset_modified_bounds_become_none(self, monkeypatch) -> None:
        """Blank modified_after/before -> None (no window restriction)."""
        calls = _wire(monkeypatch)
        mcp_server.stash_search("rotate", modified_after="", modified_before="")
        assert calls == [("search", "rotate", None, None, None, 20, None, None)]

    def test_search_forwards_modified_range(self, monkeypatch) -> None:
        """Set ISO bounds pass through untouched; the server parses them."""
        calls = _wire(monkeypatch)
        mcp_server.stash_search(
            "migration", modified_after="2026-01-01", modified_before="2026-02-01T00:00:00Z"
        )
        assert calls == [
            ("search", "migration", None, None, None, 20, "2026-01-01", "2026-02-01T00:00:00Z")
        ]

    def test_search_envelope_has_no_wrapper_keys(self, monkeypatch) -> None:
        """The returned JSON is exactly the raw {"results", "has_more"} server
        envelope — no query/source/count wrapper keys from the old API."""
        _wire(monkeypatch)
        result = _parse(mcp_server.stash_search("migration"))
        assert set(result.keys()) == {"results", "has_more"}

    def test_search_empty_results(self, monkeypatch) -> None:
        """Client returns the empty envelope -> it serializes verbatim."""

        class _EmptyClient:
            def search_sources(
                self,
                query,
                source=None,
                include_sources=None,
                exclude_sources=None,
                limit=20,
                modified_after=None,
                modified_before=None,
            ):
                return {"results": [], "has_more": False}

        monkeypatch.setattr(mcp_server, "_client", lambda: _EmptyClient())
        result = _parse(mcp_server.stash_search("nothing"))
        assert result == {"results": [], "has_more": False}

    def test_search_http_error_propagates(self, monkeypatch) -> None:
        """Shipped stash_search has no try/except, so an httpx.HTTPError from
        the client must propagate (fail-loud), not be swallowed into a
        structured-error envelope."""

        class _ErrorClient:
            def search_sources(self, query, **kwargs):
                raise httpx.HTTPError("500 Server Error")

        monkeypatch.setattr(mcp_server, "_client", lambda: _ErrorClient())
        with pytest.raises(httpx.HTTPError):
            mcp_server.stash_search("fail")

    def test_search_connect_error_propagates(self, monkeypatch) -> None:
        """The same fail-loud contract holds for connection errors."""

        class _ConnectErrorClient:
            def search_sources(self, query, **kwargs):
                raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(mcp_server, "_client", lambda: _ConnectErrorClient())
        with pytest.raises(httpx.ConnectError):
            mcp_server.stash_search("offline")

    def test_search_generic_error_propagates(self, monkeypatch) -> None:
        """A generic client failure (ValueError) also propagates rather than
        being shaped into a structured-error envelope."""

        class _GenericErrorClient:
            def search_sources(self, query, **kwargs):
                raise ValueError("Something went wrong")

        monkeypatch.setattr(mcp_server, "_client", lambda: _GenericErrorClient())
        with pytest.raises(ValueError):
            mcp_server.stash_search("boom")


class TestStashVfsTools:
    """Tests for the shipped script-based stash_vfs MCP tool.

    The tool is a thin wrapper over StashClient.run_vfs(script, cwd=cwd) that
    returns the {"stdout", "stderr", "exit_code"} shell result via _json. A
    non-zero exit_code (e.g. grep found nothing) is a valid shell result, not
    a raised error.
    """

    def test_vfs_runs_script_at_root(self, monkeypatch) -> None:
        """Defaults cwd="/": stash_vfs("ls /files") -> run_vfs("ls /files", "/")."""
        calls = _wire(monkeypatch)
        result = _parse(mcp_server.stash_vfs("ls /files"))
        assert calls == [("vfs", "ls /files", "/")]
        assert result == {
            "stdout": "contents of ls /files at /",
            "stderr": "",
            "exit_code": 0,
        }

    def test_vfs_passes_through_cwd(self, monkeypatch) -> None:
        """cwd is passed through to run_vfs untouched."""
        calls = _wire(monkeypatch)
        result = _parse(mcp_server.stash_vfs("ls", cwd="/sources"))
        assert calls == [("vfs", "ls", "/sources")]
        assert result["exit_code"] == 0

    def test_vfs_nonzero_exit_code_is_shell_result(self, monkeypatch) -> None:
        """A non-zero exit_code (grep/no-match) is a normal field in the
        returned shell result dict, not a raised error."""

        class _GrepNoMatchClient:
            def __init__(self, calls: list):
                self._calls = calls

            def run_vfs(self, script: str, cwd: str = "/") -> dict:
                self._calls.append(("vfs", script, cwd))
                return {"stdout": "", "stderr": "no matches found", "exit_code": 1}

        calls: list = []
        monkeypatch.setattr(mcp_server, "_client", lambda: _GrepNoMatchClient(calls))
        result = _parse(mcp_server.stash_vfs("grep nosuchterm /files"))
        assert calls == [("vfs", "grep nosuchterm /files", "/")]
        assert result == {"stdout": "", "stderr": "no matches found", "exit_code": 1}
