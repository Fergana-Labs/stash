"""Parse-time validation of backend-enum CLI values (STAS-120).

Eight CLI parameters feed values the backend validates against a small enum.
Before this change an invalid value (e.g. `browse --sort=trnding`) burned a
backend round-trip and died with a raw server error (422/400) and no context.
After it, each parameter is a click.Choice at parse time: an invalid value
fails before any backend call with Click's "not one of ..." message (which
names the allowed set), the STAS-080 ``Hint:`` line, and Click's usage-error
exit code 2 — stdout stays empty in every mode. Every previously-valid
value, including the nine source types the CLI help never documented, still
parses and reaches the command body.

The expected sets below mirror the backend source of truth (single source of
truth — the CLI may reject exactly what the backend rejects, nothing else):

- ``browse --sort``:         backend/routers/discover.py:13
- shares object types:       backend/services/share_service.py:22 (_SHAREABLE)
- shares ``--permission``:   backend/services/share_service.py:23 (_PERMISSIONS)
- ``sources add`` type:      backend/services/source_service.py:115 (SOURCE_CAPABILITY)
- ``tables add-column --type``: backend/models.py (ColumnAddRequest.type pattern)
- ``tables export --order``: backend/services/table_service.py:643
"""

from __future__ import annotations

import pytest

from cli import main
from cli.exit_codes import EXIT_SUCCESS
from cli.tests.test_usage_hints import _hint_line, _run_cli

# Expected sets, mirrored from the backend sources listed in the module docstring.
BROWSE_SORTS = ["trending", "newest", "popular"]
SHARE_OBJECT_TYPES = ["file", "page", "folder", "session", "table"]
SHARE_PERMISSIONS = ["read", "comment", "write"]
SOURCE_TYPES = [
    "github_repo",
    "gmail",
    "google_drive",
    "google_drive_folder",
    "notion",
    "slack",
    "granola",
    "jira_project",
    "asana_project",
    "linear",
    "posthog_project",
    "gong_calls",
    "heavi_learnings",
    "instagram_saves",
    "x_saves",
]
COLUMN_TYPES = [
    "text",
    "number",
    "boolean",
    "date",
    "datetime",
    "url",
    "email",
    "select",
    "multiselect",
    "json",
]
EXPORT_ORDERS = ["asc", "desc"]


class _NeverClient:
    """Stands in for ``main._client`` in the invalid-value tests: entering the
    context means a backend round-trip was attempted, which parse-time
    validation exists precisely to prevent."""

    def __init__(self, state: dict):
        self._state = state

    def __enter__(self):
        self._state["entered"] = True
        raise AssertionError("backend round-trip attempted on a parse-time failure")

    def __exit__(self, *_args):
        return None


def _patch_client_never(monkeypatch) -> dict:
    """Patch ``main._client`` to a sentinel that records (and aborts) any entry."""
    state = {"entered": False}
    monkeypatch.setattr(main, "_client", lambda *a, **k: _NeverClient(state))
    return state


class _Response:
    """Minimal stand-in for the httpx response ``tables export`` reads ``.text`` off."""

    def __init__(self, text: str):
        self.text = text


class _StubClient:
    """Records each call and returns the minimal payload the command body needs."""

    def __init__(self, **returns):
        self.calls: dict = {}
        self._returns = returns

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def _record(self, name, *args, **kwargs):
        self.calls[name] = (args, kwargs)
        return self._returns.get(name)

    def share_object(self, *args, **kwargs):
        return self._record("share_object", *args, **kwargs)

    def list_object_shares(self, *args, **kwargs):
        return self._record("list_object_shares", *args, **kwargs)

    def unshare_object(self, *args, **kwargs):
        return self._record("unshare_object", *args, **kwargs)

    def add_source(self, *args, **kwargs):
        return self._record("add_source", *args, **kwargs)

    def add_table_column(self, *args, **kwargs):
        return self._record("add_table_column", *args, **kwargs)

    def _request(self, *args, **kwargs):
        return self._record("_request", *args, **kwargs)


def _patch_client_stub(monkeypatch, stub: _StubClient) -> None:
    monkeypatch.setattr(main, "_client", lambda *a, **k: stub)


# --- browse --sort -------------------------------------------------------------


def test_browse_sort_invalid_fails_at_parse(monkeypatch, capsys) -> None:
    """`--sort=trnding` → Click's invalid-value message + Hint, exit 2, no backend call."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["browse", "--sort=trnding"])

    assert code == 2
    assert out == ""
    assert "Invalid value for '--sort'" in err
    for value in BROWSE_SORTS:
        assert value in err
    _hint_line(err)
    assert state["entered"] is False


def test_browse_sort_is_case_sensitive(monkeypatch, capsys) -> None:
    """`--sort=TRENDING` → exit 2: the documented values are lowercase."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["browse", "--sort=TRENDING"])

    assert code == 2
    assert out == ""
    assert "Invalid value for '--sort'" in err
    assert state["entered"] is False


def test_browse_sort_invalid_json_mode_keeps_stdout_empty(monkeypatch, capsys) -> None:
    """Global --json: the usage failure still never writes the data channel."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["--json", "browse", "--sort=trnding"])

    assert code == 2
    assert out == ""
    assert "Invalid value for '--sort'" in err
    assert "Hint:" in err
    assert state["entered"] is False


def test_browse_help_still_shows_sort_values(monkeypatch, capsys) -> None:
    """`browse --help` still exits 0 and names the three canonical values."""
    code, out, err = _run_cli(monkeypatch, capsys, ["browse", "--help"])

    assert code == EXIT_SUCCESS
    for value in BROWSE_SORTS:
        assert value in out


# --- shares ls / add / rm object_type -------------------------------------------


def test_shares_add_object_type_invalid_lists_all_kinds(monkeypatch, capsys) -> None:
    """`shares add bogus …` → exit 2 naming all 5 backend object kinds, no backend call."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["shares", "add", "bogus", "obj-1", "x@y.z"])

    assert code == 2
    assert out == ""
    for kind in SHARE_OBJECT_TYPES:
        assert kind in err
    _hint_line(err)
    assert state["entered"] is False


@pytest.mark.parametrize("kind", ["session_folder", "source"])
def test_shares_add_unshareable_kind_rejected_at_parse(monkeypatch, capsys, kind) -> None:
    """`session_folder` and `source` are not in the backend's _SHAREABLE: the
    400 the server used to return now fails at parse time, and no
    previously-working input is rejected."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["shares", "add", kind, "obj-1", "x@y.z"])

    assert code == 2
    assert out == ""
    assert "Invalid value" in err
    _hint_line(err)
    assert state["entered"] is False


def test_shares_ls_object_type_invalid(monkeypatch, capsys) -> None:
    """`shares ls bogus obj-1` → exit 2 naming all 5 backend object kinds."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["shares", "ls", "bogus", "obj-1"])

    assert code == 2
    assert out == ""
    for kind in SHARE_OBJECT_TYPES:
        assert kind in err
    _hint_line(err)
    assert state["entered"] is False


def test_shares_rm_object_type_invalid(monkeypatch, capsys) -> None:
    """`shares rm bogus obj-1 u1` → exit 2 naming all 5 backend object kinds."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["shares", "rm", "bogus", "obj-1", "u1"])

    assert code == 2
    assert out == ""
    for kind in SHARE_OBJECT_TYPES:
        assert kind in err
    _hint_line(err)
    assert state["entered"] is False


# --- shares add --permission ----------------------------------------------------


def test_shares_add_permission_invalid_lists_all(monkeypatch, capsys) -> None:
    """`--permission=own` → exit 2 naming read/comment/write, no backend call."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(
        monkeypatch, capsys, ["shares", "add", "page", "obj-1", "x@y.z", "--permission=own"]
    )

    assert code == 2
    assert out == ""
    assert "Invalid value for '--permission'" in err
    for perm in SHARE_PERMISSIONS:
        assert perm in err
    _hint_line(err)
    assert state["entered"] is False


def test_shares_add_valid_permission_passes(monkeypatch, capsys) -> None:
    """`--permission=comment` (a previously-unlisted valid value) still parses
    and reaches the client with the exact value."""
    stub = _StubClient(share_object={})
    _patch_client_stub(monkeypatch, stub)
    code, out, err = _run_cli(
        monkeypatch, capsys, ["shares", "add", "page", "obj-1", "x@y.z", "--permission=comment"]
    )

    assert code == EXIT_SUCCESS
    assert stub.calls["share_object"][0][:3] == ("page", "obj-1", "x@y.z")
    assert stub.calls["share_object"][1]["permission"] == "comment"


# --- shares parse-pass wiring ---------------------------------------------------


def test_shares_ls_parse_passes(monkeypatch, capsys) -> None:
    """`shares ls page obj-1` still parses; the client receives the exact type."""
    stub = _StubClient(list_object_shares=[])
    _patch_client_stub(monkeypatch, stub)
    code, out, err = _run_cli(monkeypatch, capsys, ["shares", "ls", "page", "obj-1"])

    assert code == EXIT_SUCCESS
    assert stub.calls["list_object_shares"][0][:2] == ("page", "obj-1")


def test_shares_rm_parse_passes(monkeypatch, capsys) -> None:
    """`shares rm page obj-1 u1` still parses; the client receives the exact type."""
    stub = _StubClient(unshare_object=None)
    _patch_client_stub(monkeypatch, stub)
    code, out, err = _run_cli(monkeypatch, capsys, ["shares", "rm", "page", "obj-1", "u1"])

    assert code == EXIT_SUCCESS
    assert stub.calls["unshare_object"][0][:2] == ("page", "obj-1")
    assert stub.calls["unshare_object"][0][2] == "user"  # principal_type default
    assert stub.calls["unshare_object"][0][3] == "u1"


# --- sources add ----------------------------------------------------------------


def test_sources_add_invalid_type_lists_all_15(monkeypatch, capsys) -> None:
    """`sources add bogus` → exit 2 naming all 15 backend source types."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["sources", "add", "bogus"])

    assert code == 2
    assert out == ""
    for source_type in SOURCE_TYPES:
        assert source_type in err
    _hint_line(err)
    assert state["entered"] is False


def test_sources_add_previously_undocumented_type_passes(monkeypatch, capsys) -> None:
    """`sources add linear --ref me` (one of the 9 types the old help never
    listed) still parses and reaches the client with the exact value."""
    stub = _StubClient(add_source={"display_name": "Linear", "id": "src_linear"})
    _patch_client_stub(monkeypatch, stub)
    code, out, err = _run_cli(monkeypatch, capsys, ["sources", "add", "linear", "--ref", "me"])

    assert code == EXIT_SUCCESS
    assert stub.calls["add_source"][0] == ("linear",)
    assert stub.calls["add_source"][1]["external_ref"] == "me"


# --- tables add-column --type -----------------------------------------------------


def test_tables_add_column_invalid_type_lists_all_10(monkeypatch, capsys) -> None:
    """`--type=bogus` → exit 2 naming all 10 backend column types."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(
        monkeypatch, capsys, ["tables", "add-column", "t-1", "Col", "--type=bogus"]
    )

    assert code == 2
    assert out == ""
    assert "Invalid value for '--type'" in err
    for col_type in COLUMN_TYPES:
        assert col_type in err
    _hint_line(err)
    assert state["entered"] is False


def test_tables_add_column_valid_type_passes(monkeypatch, capsys) -> None:
    """`--type=select` still parses and reaches the client with the exact value."""
    stub = _StubClient(add_table_column=None)
    _patch_client_stub(monkeypatch, stub)
    code, out, err = _run_cli(
        monkeypatch, capsys, ["tables", "add-column", "t-1", "Col", "--type=select"]
    )

    assert code == EXIT_SUCCESS
    assert stub.calls["add_table_column"][0][:2] == ("t-1", "Col")
    assert stub.calls["add_table_column"][1]["col_type"] == "select"


# --- tables export --order --------------------------------------------------------


def test_tables_export_invalid_order(monkeypatch, capsys) -> None:
    """`--order=upwards` → exit 2 naming asc/desc (previously the backend
    silently mapped anything not literally `desc` to ASC)."""
    state = _patch_client_never(monkeypatch)
    code, out, err = _run_cli(monkeypatch, capsys, ["tables", "export", "t-1", "--order=upwards"])

    assert code == 2
    assert out == ""
    assert "Invalid value for '--order'" in err
    for order in EXPORT_ORDERS:
        assert order in err
    _hint_line(err)
    assert state["entered"] is False


def test_tables_export_valid_order_passes(monkeypatch, capsys) -> None:
    """`--order=desc` still parses; the request params carry the exact value."""
    stub = _StubClient(_request=_Response("name,value\na,1"))
    _patch_client_stub(monkeypatch, stub)
    code, out, err = _run_cli(monkeypatch, capsys, ["tables", "export", "t-1", "--order=desc"])

    assert code == EXIT_SUCCESS
    assert stub.calls["_request"][1]["params"] == {"sort_order": "desc"}
    assert out == "name,value\na,1"
