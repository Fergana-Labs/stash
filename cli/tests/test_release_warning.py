"""The CLI tells the user when it is behind the current release.

It does not upgrade itself. The agent plugins already run an upgrade at session
start; what was missing is any signal when that upgrade is not working, which
is how an install sat weeks behind while its hooks fired thousands of times a
day. These tests pin the signal: it appears when the install is stale, stays
quiet otherwise, and says something the user can act on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from stashai import release


@pytest.fixture(autouse=True)
def unwarned(monkeypatch):
    """The warning fires once per process, so every test starts fresh."""
    monkeypatch.setattr(release, "_warned", False)
    monkeypatch.setattr(release, "is_editable", lambda: False)
    monkeypatch.setattr(release, "current_version", lambda: "0.1.334")


def test_a_stale_install_says_so(capsys):
    release.note_latest("0.1.365")

    warning = capsys.readouterr().err
    assert "0.1.334 is out of date" in warning
    assert "0.1.365" in warning
    assert "stash upgrade" in warning


def test_a_current_install_says_nothing(capsys):
    release.note_latest("0.1.334")

    assert capsys.readouterr().err == ""


def test_a_newer_install_says_nothing(capsys):
    """Someone running a local build ahead of prod is not stale."""
    release.note_latest("0.1.300")

    assert capsys.readouterr().err == ""


def test_a_backend_without_the_header_says_nothing(capsys):
    """Self-hosters run their own backend; absence means 'no opinion', not
    'upgrade to nothing'."""
    release.note_latest("")

    assert capsys.readouterr().err == ""


def test_it_warns_once_per_process(capsys):
    """One command can make a dozen requests. The user needs to read this once,
    not once per HTTP call."""
    for _ in range(5):
        release.note_latest("0.1.365")

    assert capsys.readouterr().err.count("out of date") == 1


def test_an_editable_checkout_is_told_to_pull(monkeypatch, capsys):
    """`stash upgrade` would replace a developer's working tree with a release,
    so the warning points at git instead."""
    monkeypatch.setattr(release, "is_editable", lambda: True)

    release.note_latest("0.1.365")

    warning = capsys.readouterr().err
    assert "git pull" in warning
    assert "stash upgrade" not in warning


@pytest.mark.parametrize(
    ("have", "want", "older"),
    [
        ("0.1.334", "0.1.365", True),
        ("0.1.365", "0.1.365", False),
        ("0.1.365", "0.1.334", False),
        ("0.1.9", "0.1.10", True),
        ("0.2.0", "0.1.999", False),
        ("0.1.365.dev0", "0.1.365", False),
    ],
)
def test_version_comparison(have: str, want: str, older: bool):
    """Dotted numbers compared as integers, not strings: '0.1.9' is older than
    '0.1.10' even though it sorts after it."""
    assert release._is_older(have, want) is older


def test_a_pip_install_is_upgraded_by_its_own_interpreter(monkeypatch):
    """What `stash upgrade` runs on a pyenv install. Handing this to uv would
    upgrade uv's copy, which is not the one the shell resolves."""
    monkeypatch.setattr(release, "_is_uv_tool", lambda: False)
    monkeypatch.setattr(release, "_has_pip", lambda: True)
    monkeypatch.setattr(release, "_is_externally_managed", lambda: False)

    assert release.upgrade_command() == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--upgrade",
        "stashai",
    ]


def test_a_pep668_python_gets_the_flags_it_requires(monkeypatch):
    """Debian's python and our own Fly Sprites refuse a plain `pip install`."""
    monkeypatch.setattr(release, "_is_uv_tool", lambda: False)
    monkeypatch.setattr(release, "_has_pip", lambda: True)
    monkeypatch.setattr(release, "_is_externally_managed", lambda: True)

    command = release.upgrade_command()

    assert command[-2:] == ["--user", "--break-system-packages"]


def test_a_python_without_pip_has_no_upgrader(monkeypatch):
    """uv venvs ship without pip, so `python -m pip` there fails on a missing
    module. `stash upgrade` must say so rather than run it."""
    monkeypatch.setattr(release, "_is_uv_tool", lambda: False)
    monkeypatch.setattr(release, "_has_pip", lambda: False)

    assert release.upgrade_command() is None


def test_uv_environments_are_recognised_by_their_receipt(monkeypatch, tmp_path: Path):
    """Recognising uv by the shape of sys.prefix breaks the moment UV_TOOL_DIR
    is set, sending uv installs down the pip branch — where a uv environment
    has no pip at all."""
    monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path / "somewhere-else"))
    (tmp_path / "uv-receipt.toml").write_text("")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(release, "_find_uv", lambda: "/usr/local/bin/uv")

    assert release.upgrade_command() == [
        "/usr/local/bin/uv",
        "tool",
        "install",
        "--quiet",
        "stashai@latest",
    ]


def test_a_uv_install_with_no_uv_has_no_upgrader(monkeypatch, tmp_path: Path):
    """uv removed after the fact. `stash upgrade` reports it instead of
    pretending; the user is told to re-run the installer."""
    (tmp_path / "uv-receipt.toml").write_text("")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(release, "_find_uv", lambda: None)

    assert release.upgrade_command() is None
