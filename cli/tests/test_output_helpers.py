"""Channel-discipline tests for the CLI stdout/stderr output helpers.

The stash CLI's contract is strict: stdout carries only parseable data, and
everything human-readable (progress, status, warnings, errors) goes to stderr
so agent consumers can parse stdout reliably. These tests pin that split with
``capsys`` and ``result.stdout``/``result.stderr`` assertions on the explicit
channel (this Click version never mixes stderr into ``result.stdout``), and pin
the suppression seam STAS-060's ``--json`` mode will toggle: non-error progress
is suppressible, errors and data never are.
"""

import re

from typer.testing import CliRunner

from cli import main
from cli.client import StashError
from cli.formatting import (
    echo_error,
    echo_stderr,
    echo_stdout,
    set_progress_suppressed,
)


def _strip_markup(text: str) -> str:
    """Strip ANSI/Rich styling so assertions run on the plain message text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_stdout_helper_writes_only_stdout(capsys) -> None:
    echo_stdout("data")
    captured = capsys.readouterr()
    assert captured.out == "data\n"
    assert captured.err == ""


def test_stdout_helper_never_wraps_parseable_data(capsys) -> None:
    """Parseable data must arrive byte-for-byte intact: a single logical line
    wider than the console must not be wrapped, or it would corrupt the JSON a
    hook runner reads from stdout (e.g. a plugin ``systemMessage`` payload)."""
    long_line = "alphabet " * 40  # far wider than any console width
    echo_stdout(long_line)
    captured = capsys.readouterr()
    assert captured.out == long_line + "\n"
    assert "\n" not in captured.out[:-1]
    assert captured.err == ""


def test_stderr_helper_writes_only_stderr(capsys) -> None:
    echo_stderr("note")
    captured = capsys.readouterr()
    assert captured.err == "note\n"
    assert captured.out == ""


def test_error_helper_writes_only_stderr(capsys) -> None:
    echo_error("boom")
    captured = capsys.readouterr()
    assert _strip_markup(captured.err) == "boom\n"
    assert captured.out == ""


def test_multiline_helper_messages_keep_every_line(capsys) -> None:
    echo_stderr("line one\nline two")
    captured = capsys.readouterr()
    assert captured.err == "line one\nline two\n"
    assert captured.out == ""


def test_empty_string_helper_message_emits_blank_line_only(capsys) -> None:
    echo_stderr("")
    captured = capsys.readouterr()
    assert captured.err == "\n"
    assert captured.out == ""


def _reset_suppression() -> None:
    set_progress_suppressed(False)


def test_suppression_silences_only_non_error_progress(capsys) -> None:
    """With suppression on, progress is silent but errors and data still emit."""
    try:
        set_progress_suppressed(True)

        echo_stderr("note")
        echo_error("boom")
        echo_stdout("data")

        captured = capsys.readouterr()
        assert captured.err == _strip_markup("boom\n")
        assert captured.out == "data\n"
    finally:
        _reset_suppression()


def test_unsuppressed_emits_everything(capsys) -> None:
    """With suppression off, all three helpers emit normally."""
    try:
        set_progress_suppressed(False)

        echo_stderr("note")
        echo_error("boom")
        echo_stdout("data")

        captured = capsys.readouterr()
        assert captured.err == _strip_markup("note\nboom\n")
        assert captured.out == "data\n"
    finally:
        _reset_suppression()


def test_error_helper_emits_even_while_suppressed(capsys) -> None:
    """Errors are never silenced by the suppression seam."""
    try:
        set_progress_suppressed(True)
        echo_error("boom")
        captured = capsys.readouterr()
        assert "boom" in _strip_markup(captured.err)
        assert captured.out == ""
    finally:
        _reset_suppression()


class _FailingClient:
    """Context-manager client whose search raises the StashError under test."""

    def __init__(self, exc: StashError):
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def search_sources(self, query, **kwargs):
        raise self._exc


def test_error_handler_routes_errors_to_stderr(monkeypatch) -> None:
    """A command that hits a StashError must put the error on stderr and keep
    stdout clean — the split that lets agents parse stdout as pure data."""
    monkeypatch.setattr(main, "_client", lambda: _FailingClient(StashError(500, "boom")))

    runner = CliRunner()
    result = runner.invoke(main.app, ["search", "q"])

    # A 500 is an internal/backend failure, so under the approved AXI contract
    # (0=success, 1=user error, 2=internal error) this exits 2, not 1.
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Error [500]" in result.stderr
    assert "boom" in result.stderr
