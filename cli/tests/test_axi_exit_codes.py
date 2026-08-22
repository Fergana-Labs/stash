"""Exit-code and stderr-routing tests for the stash CLI (AXI adoption).

Locks the approved exit-code contract — ``0=success, 1=user error,
2=internal error, 20+=agent signals`` — for the classifier in
:mod:`cli.exit_codes` and, in later steps, for every command surface: success
exits 0, user error exits 1, internal/backend error exits 2, and error text
never lands on stdout (stdout carries only parseable data).

A backend transport failure on an API-backed command is a delivery fault, never
the caller's: the request layer wraps a raw ``httpx.TransportError`` into a
:class:`~cli.client.StashError` carrying ``TRANSPORT_ERROR_STATUS``, which the
router classifies (like any 5xx) to the internal-error band (exit 2) with the
message on stderr.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli import main
from cli.client import StashError
from cli.exit_codes import (
    EXIT_AGENT_SIGNAL,
    EXIT_INTERNAL_ERROR,
    EXIT_SUCCESS,
    EXIT_USER_ERROR,
    TRANSPORT_ERROR_STATUS,
    classify_error,
    classify_status_code,
)

runner = CliRunner()


def test_exit_code_constants() -> None:
    assert EXIT_SUCCESS == 0
    assert EXIT_USER_ERROR == 1
    assert EXIT_INTERNAL_ERROR == 2
    assert EXIT_AGENT_SIGNAL == 20


@pytest.mark.parametrize("status", [200, 204, 301, 302, 399])
def test_success_statuses_map_to_exit_0(status: int) -> None:
    assert classify_status_code(status) == EXIT_SUCCESS


@pytest.mark.parametrize("status", [400, 404, 409, 422])
def test_user_error_statuses_map_to_exit_1(status: int) -> None:
    assert classify_status_code(status) == EXIT_USER_ERROR


@pytest.mark.parametrize("status", [500, 502, 503, 504, 599])
def test_internal_error_statuses_map_to_exit_2(status: int) -> None:
    assert classify_status_code(status) == EXIT_INTERNAL_ERROR


def test_classify_error_uses_http_status() -> None:
    assert classify_error(StashError(404, "Not found")) == EXIT_USER_ERROR
    assert classify_error(StashError(500, "Internal")) == EXIT_INTERNAL_ERROR
    assert classify_error(StashError(200, "ok")) == EXIT_SUCCESS


# ---------------------------------------------------------------------------
# Central error handler: HTTP status -> exit code + stderr-only routing
# ---------------------------------------------------------------------------


class _RaisingClient:
    """A stand-in for StashClient whose whoami() raises a given StashError."""

    def __init__(self, error: StashError):
        self._error = error

    def whoami(self):
        raise self._error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _wire_failing_whoami(monkeypatch, error: StashError) -> None:
    from cli import main

    monkeypatch.setattr(main, "_client", lambda: _RaisingClient(error))


def test_user_error_stash_error_exits_1_stderr_only(monkeypatch) -> None:
    from cli import main

    _wire_failing_whoami(monkeypatch, StashError(404, "Not Found"))
    result = runner.invoke(main.app, ["whoami"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "Not Found" in result.stderr
    assert result.stdout == ""


def test_internal_error_stash_error_exits_2_stderr_only(monkeypatch) -> None:
    from cli import main

    _wire_failing_whoami(monkeypatch, StashError(500, "Internal Server Error"))
    result = runner.invoke(main.app, ["whoami"])
    assert result.exit_code == EXIT_INTERNAL_ERROR
    assert "Internal Server Error" in result.stderr
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Inline failure paths: user-error helpers (exit 1) and internal-error (exit 2)
# ---------------------------------------------------------------------------


def test_hook_run_unknown_agent_exits_1() -> None:
    from cli import main

    result = runner.invoke(main.app, ["hook", "run", "bogus", "on_stop"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "Unknown hook agent" in result.stderr
    assert result.stdout == ""


def test_hook_auto_update_invalid_choice_exits_1() -> None:
    from cli import main

    result = runner.invoke(main.app, ["hook", "auto-update", "maybe"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "Pass 'on' or 'off'" in result.stderr
    assert result.stdout == ""


def test_share_with_no_detectable_session_exits_1(monkeypatch) -> None:
    from cli import main

    monkeypatch.setattr(main, "_require_auth", lambda: {})
    monkeypatch.setattr(main, "_current_session_id", lambda: None)
    result = runner.invoke(main.app, ["share"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "Could not detect session" in result.stderr
    assert result.stdout == ""


def test_files_text_extraction_failed_exits_2(monkeypatch) -> None:
    """An inline internal failure (backend extraction failed) exits 2, and
    the message never reaches stdout."""
    from cli import main

    class _TextFailedClient:
        def get_file_text(self, file_id):
            return {"status": "failed", "error": "pdf parse exploded"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(main, "_require_auth", lambda: {})
    monkeypatch.setattr(main, "_client", lambda: _TextFailedClient())
    result = runner.invoke(main.app, ["files", "text", "page-1"])
    assert result.exit_code == EXIT_INTERNAL_ERROR
    assert "Extraction failed" in result.stderr
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Success-path stdout cleanliness: data on stdout, no error text anywhere
# ---------------------------------------------------------------------------


def _fakeless_auth(monkeypatch) -> None:
    from cli import main

    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **k: None)


class _LsClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def sources_tree(self, depth=3):
        return [
            {
                "source": "files",
                "type": "native_files",
                "display_name": "Files",
                "tree": [],
            }
        ]


def test_success_list_command_exits_0_data_on_stdout_no_error(monkeypatch) -> None:
    from cli import main

    _fakeless_auth(monkeypatch)
    monkeypatch.setattr(main, "_client", lambda: _LsClient())
    result = runner.invoke(main.app, ["ls"])
    assert result.exit_code == EXIT_SUCCESS
    assert "files/" in result.stdout
    assert result.stderr == ""


def test_version_and_help_exit_0(monkeypatch) -> None:
    from cli import main

    version = runner.invoke(main.app, ["--version"])
    assert version.exit_code == EXIT_SUCCESS
    assert "stash " in version.stdout

    help_result = runner.invoke(main.app, ["--help"])
    assert help_result.exit_code == EXIT_SUCCESS
    assert "Usage" in help_result.stdout


# ---------------------------------------------------------------------------
# Surface matrix: empty-list success paths exit 0 for every list-style command
# ---------------------------------------------------------------------------


class _EmptyListClient:
    """Returns empty results for every list-style method a command may call."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def list_skills(self):
        return []

    def list_agent_names(self):
        return []

    def list_agents(self):
        return []

    def list_mcp_servers(self):
        return []

    def list_api_keys(self):
        return []

    def get_trash(self):
        return {"pages": [], "files": [], "sessions": []}

    def list_object_shares(self, object_type, object_id):
        return []


def _wire_empty_list(monkeypatch) -> None:
    from cli import main

    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_client", lambda: _EmptyListClient())


@pytest.mark.parametrize(
    "argv",
    [
        ["skills", "list"],
        ["sessions", "agents"],
        ["agent", "list"],
        ["tools", "list"],
        ["keys", "list"],
        ["trash", "list"],
        ["shares", "ls", "page", "page-1"],
    ],
)
def test_list_commands_exit_0_on_empty(monkeypatch, argv) -> None:
    """Empty-result list commands are successful invocations: they exit 0 and
    print no error text (the empty-state note is informational, on stdout as
    data, and stderr stays clean)."""
    from cli import main

    _wire_empty_list(monkeypatch)
    result = runner.invoke(main.app, argv)
    assert result.exit_code == EXIT_SUCCESS
    assert "Error" not in result.stderr


# ---------------------------------------------------------------------------
# Surface matrix: backend-free user-error (exit 1) paths across sub-apps
# ---------------------------------------------------------------------------


def test_rm_invalid_ref_exits_1() -> None:
    from cli import main

    result = runner.invoke(main.app, ["rm", "bogus"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "Invalid item 'bogus'" in result.stderr
    assert result.stdout == ""


def test_mv_without_target_exits_1() -> None:
    from cli import main

    result = runner.invoke(main.app, ["mv", "page:1"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "Pass --to-folder" in result.stderr
    assert result.stdout == ""


def test_tools_add_missing_transport_exits_1() -> None:
    from cli import main

    result = runner.invoke(main.app, ["tools", "add", "myserver"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "exactly one of --command" in result.stderr
    assert result.stdout == ""


def test_vfs_not_signed_in_exits_1(monkeypatch) -> None:
    from cli import main

    # Force an empty stored api_key so vfs fails loud with a user error
    # before touching any backend (independent of any real config on the host).
    monkeypatch.setattr(main, "load_config", lambda: {"base_url": "", "api_key": "", "scope": None})
    result = runner.invoke(main.app, ["vfs", "ls", "/"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "Not signed in" in result.stderr
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Transport failures: a backend-delivery fault classifies to internal (exit 2)
# ---------------------------------------------------------------------------


class _FakeClient:
    """Stands in for StashClient on the routed commands (`search`, `whoami`).

    A stubbed method either returns a payload (success) or raises the given
    ``StashError``, exactly like the real client method would on a backend
    failure. ``search_sources`` runs the transport-and-stdout path through
    ``_print_search``; ``whoami`` runs the 5xx path through the same router.
    """

    def __init__(self, search_sources, whoami=None):
        self._search_sources = search_sources
        self._whoami = whoami

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def search_sources(self, *args, **kwargs):
        return _raise_if_exception(self._search_sources)

    def whoami(self):
        if self._whoami is None:
            return {"name": "test", "id": "u1"}
        return _raise_if_exception(self._whoami)


def _raise_if_exception(value):
    """Stub helper: raise the stubbed exception or return the payload."""
    if isinstance(value, Exception):
        raise value
    return value


def _wire(monkeypatch, client) -> None:
    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: client)


def test_search_success_exits_0_stdout_only(monkeypatch) -> None:
    client = _FakeClient(
        search_sources={
            "results": [{"source": "files", "ref": "p1", "name": "Runbook", "snippet": "deploy"}],
            "has_more": False,
        }
    )
    _wire(monkeypatch, client)

    result = runner.invoke(main.app, ["search", "test"])
    assert result.exit_code == EXIT_SUCCESS
    assert "Runbook" in result.stdout
    assert result.stderr == ""


def test_transport_failure_exits_internal_error(monkeypatch) -> None:
    """A backend transport failure exits 2 (internal/network error), not 1 —
    and routes the message to stderr with stdout untouched."""
    client = _FakeClient(search_sources=StashError(TRANSPORT_ERROR_STATUS, "connection refused"))
    _wire(monkeypatch, client)

    result = runner.invoke(main.app, ["search", "test"])
    assert result.exit_code == EXIT_INTERNAL_ERROR
    assert "connection refused" in result.stderr
    assert result.stdout == ""


def test_http_4xx_still_exits_user_error(monkeypatch) -> None:
    """An HTTP 4xx (the caller did something wrong) still exits 1 — no
    regression from the transport-error reclassification."""
    client = _FakeClient(search_sources=StashError(404, "not found"))
    _wire(monkeypatch, client)

    result = runner.invoke(main.app, ["search", "test"])
    assert result.exit_code == EXIT_USER_ERROR
    assert "not found" in result.stderr


def test_whoami_5xx_exits_internal_error(monkeypatch) -> None:
    """The same central router classifies a non-transport 5xx (exit 2) on a
    different routed command."""
    client = _FakeClient(search_sources=None, whoami=StashError(502, "bad gateway"))
    _wire(monkeypatch, client)

    result = runner.invoke(main.app, ["whoami"])
    assert result.exit_code == EXIT_INTERNAL_ERROR
    assert "bad gateway" in result.stderr


def test_classifier_pins_transport_to_internal() -> None:
    """The status classifier pins the AXI bands: 4xx -> 1, 5xx and the
    synthetic transport status -> 2."""
    assert classify_status_code(400) == EXIT_USER_ERROR
    assert classify_status_code(404) == EXIT_USER_ERROR
    assert classify_status_code(500) == EXIT_INTERNAL_ERROR
    assert classify_status_code(TRANSPORT_ERROR_STATUS) == EXIT_INTERNAL_ERROR
