"""Top-level entry boundary for the stash CLI (`main`).

Commands that route through `_err` classify transport failures to exit 2 (see
`test_axi_exit_codes.py`). But the re-raise call sites in share/page-create
intentionally re-raise a non-409 StashError, and any raw httpx.TransportError
that escapes the request layer — neither of which `_err` (a `StashError`-only
router) sees. The `main()` entry boundary catches these escaped errors with
`app(standalone_mode=False)` and routes them through the same classification
and stderr emission, so *any* API-backed failure surfaces as the classified
exit code with stderr (never stdout) and no raw traceback.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from cli import main
from cli.client import StashError
from cli.exit_codes import (
    EXIT_INTERNAL_ERROR,
    EXIT_SUCCESS,
    EXIT_USER_ERROR,
    TRANSPORT_ERROR_STATUS,
)


class _EscapingApp:
    """Stand-in for the Typer app that raises the escaped error `main` must
    catch — exactly what a command body that re-raises a StashError produces
    when its error escapes through `app(standalone_mode=False)`."""

    def __init__(self, exc):
        self._exc = exc

    def __call__(self, standalone_mode=False):
        raise self._exc


def _run_main(monkeypatch, capsys, argv, app_override=None, client=None) -> tuple:
    """Invoke `main()` with the given argv and capture (exit_code, out, err).

    Keeps the boundary test deterministic: the app is either the real `main.app`
    (pass a `client`) or an override that raises the escaped error directly.
    """
    monkeypatch.setattr(main, "_require_auth", lambda: None)
    if client is not None:
        monkeypatch.setattr(main, "_client", lambda: client)
    if app_override is not None:
        monkeypatch.setattr(main, "app", app_override)
    monkeypatch.setattr("sys.argv", list(argv))
    with pytest.raises(SystemExit) as excinfo:
        main.main()
    captured = capsys.readouterr()
    return excinfo.value.code, captured.out, captured.err


# --- Escaped-error routing through the boundary (deterministic) --------------


def test_escaped_transport_stasherror_surfaces_exit_2(monkeypatch, capsys) -> None:
    """A re-raised transport StashError escaping a command body exits 2."""
    app_override = _EscapingApp(StashError(TRANSPORT_ERROR_STATUS, "connection refused"))
    code, out, err = _run_main(monkeypatch, capsys, ["stash"], app_override=app_override)

    assert code == EXIT_INTERNAL_ERROR
    assert "connection refused" in err
    assert out == ""


def test_escaped_4xx_stasherror_still_exits_1(monkeypatch, capsys) -> None:
    """An HTTP 4xx StashError escaping to the boundary still exits 1."""
    app_override = _EscapingApp(StashError(404, "not found"))
    code, out, err = _run_main(monkeypatch, capsys, ["stash"], app_override=app_override)

    assert code == EXIT_USER_ERROR
    assert "not found" in err
    assert out == ""


def test_escaped_raw_transport_exits_internal(monkeypatch, capsys) -> None:
    """A raw httpx.TransportError escaping to the boundary exits 2."""
    app_override = _EscapingApp(
        httpx.ConnectError("refused", request=httpx.Request("GET", "http://x"))
    )
    code, out, err = _run_main(monkeypatch, capsys, ["stash"], app_override=app_override)

    assert code == EXIT_INTERNAL_ERROR
    assert "refused" in err
    assert out == ""


def test_non_stash_or_transport_error_reraises(monkeypatch, capsys) -> None:
    """Genuine bugs (a non-classified exception) re-raise so a traceback shows."""

    class Boom(Exception):
        pass

    monkeypatch.setattr(main, "app", _EscapingApp(Boom("splat")))
    monkeypatch.setattr("sys.argv", ["stash"])
    with pytest.raises(Boom):
        main.main()


# --- Real command routing through the boundary -------------------------------


class _FakeSearchClient:
    def __init__(self, search_sources):
        self._search_sources = search_sources

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def search_sources(self, *args, **kwargs):
        if isinstance(self._search_sources, Exception):
            raise self._search_sources
        return self._search_sources


def test_real_search_transport_through_entry_exits_internal(monkeypatch, capsys) -> None:
    """The real `app(standalone_mode=False)` + `_err` path closes at the same
    exit code: a wrapped transport failure on `stash search` exits 2 via the
    entry function, with clean stdout."""
    client = _FakeSearchClient(StashError(TRANSPORT_ERROR_STATUS, "connection refused"))
    code, out, err = _run_main(monkeypatch, capsys, ["stash", "search", "test"], client=client)

    assert code == EXIT_INTERNAL_ERROR
    assert "connection refused" in err
    assert out == ""


def test_real_search_success_through_entry_exits_zero(monkeypatch, capsys) -> None:
    client = _FakeSearchClient(
        {"results": [{"source": "files", "ref": "p1", "name": "Runbook"}], "has_more": False}
    )
    code, out, err = _run_main(monkeypatch, capsys, ["stash", "search", "test"], client=client)

    assert code == EXIT_SUCCESS
    assert "Runbook" in out


def test_missing_argument_usage_error_stays_clean(monkeypatch, capsys) -> None:
    """A missing required argument exits with Click's clean usage message, not
    a raw traceback.

    ``stash search`` requires a positional ``query``. With ``main()``'s
    ``app(standalone_mode=False)``, Click raises a ``MissingParameter``
    (a ``UsageError`` subclass) during parsing — before any command body or
    client call runs — instead of rendering the error itself. The boundary
    catch must route that through Click's ``show()`` (stderr) and exit 2, the
    same exit a dependencyless success invocation would, so a missing arg
    never surfaces as an unhandled Click traceback.
    """
    code, out, err = _run_main(monkeypatch, capsys, ["stash", "search"])

    assert code == EXIT_INTERNAL_ERROR
    assert "Missing argument" in err
    assert out == ""


class _FakeShareClient:
    """Drives `stash share` to the upload_transcript re-raise site (the real
    production path): folder/page creation succeed, then upload_transcript
    raises, which share's `except StashError: if status != 409: raise` block
    re-raises for the boundary to catch."""

    def __init__(self, upload_exc):
        self._upload_exc = upload_exc

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def resolve_session(self, ref, trashed=False):
        return {"matched": False, "session_id": ref, "id": ref, "name": None}

    def create_folder(self, name, parent_folder_id=None):
        return {"id": "f1", "name": name}

    def create_page(self, name, content="", folder_id=None, content_type=None):
        return {"id": "p1"}

    def upload_transcript(self, *args, **kwargs):
        if isinstance(self._upload_exc, Exception):
            raise self._upload_exc
        return {"imported": 1}

    def publish_skill_folder(self, folder_id, **kwargs):
        return {"id": "s1", "slug": "x", "title": "x"}


def _wire_share(monkeypatch, tmp_path, jsonl_text) -> Path:
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(jsonl_text)
    monkeypatch.setattr(main, "_find_session_jsonl", lambda sid: jsonl)
    return jsonl


def test_share_reraises_transport_through_entry_exits_internal(
    monkeypatch, capsys, tmp_path
) -> None:
    """The share re-raise site (the original escape path) now exits 2 via the
    boundary, with the failure on stderr and off stdout."""
    jsonl_text = (
        '{"sessionId":"s1","type":"assistant","message":{"role":"assistant","content":"answer"}}\n'
    )
    _wire_share(monkeypatch, tmp_path, jsonl_text)
    client = _FakeShareClient(StashError(TRANSPORT_ERROR_STATUS, "network down"))

    code, out, err = _run_main(
        monkeypatch, capsys, ["stash", "share", "--session", "s1"], client=client
    )

    assert code == EXIT_INTERNAL_ERROR
    assert "network down" in err
    assert "network down" not in out


def test_share_reraises_4xx_through_entry_exits_user_error(monkeypatch, capsys, tmp_path) -> None:
    """A 4xx StashError re-raised by the share site still exits 1 at the
    boundary — no regression in the re-raise classification."""
    jsonl_text = (
        '{"sessionId":"s1","type":"assistant","message":{"role":"assistant","content":"answer"}}\n'
    )
    _wire_share(monkeypatch, tmp_path, jsonl_text)
    client = _FakeShareClient(StashError(404, "not found"))

    code, out, err = _run_main(
        monkeypatch, capsys, ["stash", "share", "--session", "s1"], client=client
    )

    assert code == EXIT_USER_ERROR
    assert "not found" in err
    assert "not found" not in out
