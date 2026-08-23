"""Contextual help hints on invocation failures (AXI §8/§9).

The convention these tests lock: whenever Click fails to parse an
invocation — unknown command (top-level or under a group), unknown option,
missing argument, option requiring an argument — ``main`` renders typer's
unchanged Rich error panel to stderr, appends exactly one ``Hint:`` line to
stderr, and exits with Click's usage-error code (2). The hint prefers a
concrete runnable suggestion (``Did you mean `stash skills list`?``) over a
``--help`` pointer. Hints are guidance, not data: they never write to
stdout, so they can never enter the ``--json`` data channel, and they are
never suppressed. The success paths (``--version``, bare help) stay
hint-free and exit 0.
"""

from __future__ import annotations

import pytest

from cli import main
from cli.exit_codes import EXIT_SUCCESS


def _run_cli(monkeypatch, capsys, argv) -> tuple[int, str, str]:
    """Invoke the real ``main()`` with the given argv (as ``stash <argv>``)
    and return (exit_code, stdout, stderr). A ``main()`` return without
    SystemExit is the success path (exit 0)."""
    monkeypatch.setattr("sys.argv", ["stash", *argv])
    monkeypatch.setattr(main, "_JSON_MODE", False)
    try:
        main.main()
        code = EXIT_SUCCESS
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else EXIT_SUCCESS
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _hint_line(err: str) -> str:
    """The single Hint: line, asserted to be the last line stderr rendered."""
    lines = err.rstrip("\n").splitlines()
    assert lines[-1].startswith("Hint: "), f"hint must be the appended last line: {lines!r}"
    return lines[-1]


# --- Near-miss command names --------------------------------------------------


def test_top_level_typo_suggests_command(monkeypatch, capsys) -> None:
    """`stash skil list` → panel + Did-you-mean hint, stdout clean, exit 2."""
    code, out, err = _run_cli(monkeypatch, capsys, ["skil", "list"])

    assert code == 2
    assert out == ""
    assert "No such command 'skil'" in err  # the error panel is preserved
    hint = _hint_line(err)
    assert "Did you mean" in hint
    assert "stash skills" in hint


def test_group_level_typo_suggests_full_path(monkeypatch, capsys) -> None:
    """`stash skills lst` → hint carries the full runnable path."""
    code, out, err = _run_cli(monkeypatch, capsys, ["skills", "lst"])

    assert code == 2
    assert out == ""
    assert "No such command 'lst'" in err
    assert "Did you mean `stash skills list`?" in _hint_line(err)


def test_hyphenated_typo_suggests(monkeypatch, capsys) -> None:
    """`stash skil-list` (dash where a space belongs) still gets a suggestion."""
    code, out, err = _run_cli(monkeypatch, capsys, ["skil-list"])

    assert code == 2
    assert out == ""
    assert "Did you mean" in _hint_line(err)


def test_unmatched_command_gets_help_fallback(monkeypatch, capsys) -> None:
    """No close match at all → the root --help fallback, never a blank hint."""
    code, out, err = _run_cli(monkeypatch, capsys, ["zzznope"])

    assert code == 2
    assert out == ""
    assert "No such command 'zzznope'" in err
    hint = _hint_line(err)
    assert "stash --help" in hint
    assert "see all commands" in hint


# --- Missing / invalid argument or option -------------------------------------


def test_missing_required_argument_points_to_help(monkeypatch, capsys) -> None:
    """`stash skills add` (FOLDER missing) → --help pointer for that command."""
    code, out, err = _run_cli(monkeypatch, capsys, ["skills", "add"])

    assert code == 2
    assert out == ""
    assert "Missing argument" in err
    assert "Pass `stash skills add --help` to see this command's options." in _hint_line(err)


def test_unknown_option_points_to_help(monkeypatch, capsys) -> None:
    """`stash skills add --bogus x.md` → --help pointer, exit 2."""
    code, out, err = _run_cli(monkeypatch, capsys, ["skills", "add", "--bogus", "x.md"])

    assert code == 2
    assert out == ""
    assert "No such option" in err
    assert "Pass `stash skills add --help`" in _hint_line(err)


def test_option_requiring_argument_points_to_help(monkeypatch, capsys) -> None:
    """`stash browse --sort` (value required) → --help pointer, exit 2."""
    code, out, err = _run_cli(monkeypatch, capsys, ["browse", "--sort"])

    assert code == 2
    assert out == ""
    assert "requires an argument" in err
    assert "Pass `stash browse --help`" in _hint_line(err)


def test_root_unknown_option_points_to_root_help(monkeypatch, capsys) -> None:
    """An option Click can't resolve before any command gets the root hint."""
    code, out, err = _run_cli(monkeypatch, capsys, ["--bogus"])

    assert code == 2
    assert out == ""
    assert "Pass `stash --help` to see all commands and options." in _hint_line(err)


# --- Stream purity and exit codes ---------------------------------------------


def test_json_mode_keeps_stdout_empty(monkeypatch, capsys) -> None:
    """Global --json before a bad command: stdout stays empty, hint on stderr."""
    code, out, err = _run_cli(monkeypatch, capsys, ["--json", "skil", "list"])

    assert code == 2
    assert out == ""
    assert "Hint:" in err
    assert "Did you mean" in err


def test_hint_renders_exactly_once(monkeypatch, capsys) -> None:
    """One invocation failure appends exactly one Hint: line."""
    _code, out, err = _run_cli(monkeypatch, capsys, ["skills", "lst"])

    assert out == ""
    assert err.count("Hint:") == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["skil", "list"],
        ["skills", "lst"],
        ["skil-list"],
        ["zzznope"],
        ["skills", "add"],
        ["skills", "add", "--bogus", "x.md"],
        ["browse", "--sort"],
        ["--bogus"],
        ["--json", "skil", "list"],
    ],
)
def test_usage_failures_never_write_stdout(monkeypatch, capsys, argv) -> None:
    """Every usage-failure surface leaves stdout empty (stderr-only by
    construction, so --json mode can never carry a hint)."""
    code, out, err = _run_cli(monkeypatch, capsys, argv)

    assert code == 2
    assert out == ""
    assert "Hint:" in err


# --- Success paths stay untouched ----------------------------------------------


def test_version_is_hint_free(monkeypatch, capsys) -> None:
    """`stash --version` still exits 0 with the version on stdout, no hint."""
    code, out, err = _run_cli(monkeypatch, capsys, ["--version"])

    assert code == EXIT_SUCCESS
    assert out.startswith("stash ")
    assert "Hint:" not in err


def test_bare_invocation_help_is_hint_free(monkeypatch, capsys) -> None:
    """`stash` with no args still prints help on stdout, exit 0, no hint."""
    code, out, err = _run_cli(monkeypatch, capsys, [])

    assert code == EXIT_SUCCESS
    assert "COMMAND [ARGS]" in out
    assert "Hint:" not in err


# --- The path derivation the hints build on ------------------------------------


def test_derive_command_path_examples() -> None:
    """The documented prefix-descent examples (group, leaf command, unknown)."""
    assert main._derive_command_path(["skills", "add", "x.md"]) == ["skills", "add"]
    assert main._derive_command_path(["browse", "--sort"]) == ["browse"]
    assert main._derive_command_path(["skil", "list"]) == []
    assert main._derive_command_path(["--json", "skills", "lst"]) == ["skills"]
