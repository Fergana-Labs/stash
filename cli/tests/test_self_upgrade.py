"""Cover the CLI's own upgrade path.

The bug this replaces: freshness lived entirely in agent-plugin hooks, every
failure was silent, and an install ran 30 releases behind for two weeks while
its hooks fired thousands of times a day. So the properties worth pinning are
the ones that failed then — that a stale install actually acts, that it
upgrades *the copy that is running*, and that when it can't, it says so.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from stashai import self_upgrade


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path: Path):
    """Point the attempt stamp at a temp dir and re-enable after any test that
    disables. Nothing here may touch the developer's real ~/.stash."""
    monkeypatch.setattr(self_upgrade, "_STAMP_PATH", tmp_path / "upgrade_attempt.json")
    monkeypatch.setattr(self_upgrade, "_enabled", True)
    monkeypatch.setattr(self_upgrade, "_warned_stamp_unwritable", False)


@pytest.fixture
def spawned(monkeypatch) -> list[list[str]]:
    """Record every process the upgrade would start."""
    calls: list[list[str]] = []
    monkeypatch.setattr(self_upgrade.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    return calls


def _as_release(monkeypatch, current: str) -> None:
    monkeypatch.setattr(self_upgrade, "current_version", lambda: current)
    monkeypatch.setattr(self_upgrade, "is_editable", lambda: False)


def test_stale_install_upgrades_itself(monkeypatch, spawned, capsys):
    """The whole point: nobody had to run anything for this to happen."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: "/opt/homebrew/bin/uv")

    self_upgrade.note_latest("0.1.364")

    assert spawned == [["/opt/homebrew/bin/uv", "tool", "install", "--quiet", "stashai@latest"]]
    # The user is told which version their command actually ran on, because it
    # is not the one they are about to get.
    assert "0.1.334 → 0.1.364" in capsys.readouterr().err


def test_current_install_does_nothing(monkeypatch, spawned):
    _as_release(monkeypatch, "0.1.364")
    self_upgrade.note_latest("0.1.364")
    assert spawned == []


def test_missing_header_does_nothing(monkeypatch, spawned):
    """Self-hosted and older backends send no header; that is not a signal to
    upgrade toward an unknown release."""
    _as_release(monkeypatch, "0.1.334")
    self_upgrade.note_latest("")
    assert spawned == []


def test_pip_install_is_upgraded_by_its_own_interpreter(monkeypatch, spawned):
    """Sam's failure mode: uv dutifully upgraded a copy that was not the copy
    on PATH, so the version never moved. The install that is running is the
    install that gets upgraded."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: False)
    monkeypatch.setattr(self_upgrade, "_has_pip", lambda: True)
    monkeypatch.setattr(self_upgrade, "_is_externally_managed", lambda: False)
    monkeypatch.setattr(self_upgrade.sys, "executable", "/pyenv/versions/3.12/bin/python")

    self_upgrade.note_latest("0.1.364")

    assert spawned == [
        [
            "/pyenv/versions/3.12/bin/python",
            "-m",
            "pip",
            "install",
            "--quiet",
            "--upgrade",
            "stashai",
        ]
    ]


def test_editable_checkout_is_never_touched(monkeypatch, spawned, capsys):
    """Upgrading a developer's `pip install -e .` would overwrite the code they
    are working on. Tell them, change nothing."""
    monkeypatch.setattr(self_upgrade, "current_version", lambda: "0.1.334")
    monkeypatch.setattr(self_upgrade, "is_editable", lambda: True)

    self_upgrade.note_latest("0.1.364")

    assert spawned == []
    assert "checkout" in capsys.readouterr().err


def test_missing_uv_is_reported_not_swallowed(monkeypatch, spawned, capsys):
    """The old path returned silently when uv was absent, which is how an
    install could sit stale for weeks with nothing on screen ever saying so."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: None)

    self_upgrade.note_latest("0.1.364")

    assert spawned == []
    err = capsys.readouterr().err
    assert "no working upgrader" in err
    assert "joinstash.ai/install" in err


def test_one_attempt_per_hour_per_release(monkeypatch, spawned):
    """A CLI makes many requests per command. Without the stamp, a machine that
    cannot upgrade would spawn an installer on every single response."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: "/usr/local/bin/uv")

    self_upgrade.note_latest("0.1.364")
    self_upgrade.note_latest("0.1.364")
    self_upgrade.note_latest("0.1.364")

    assert len(spawned) == 1


def test_a_newer_release_retries_immediately(monkeypatch, spawned):
    """The throttle bounds failure, so it must not delay a release that just
    shipped."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: "/usr/local/bin/uv")

    self_upgrade.note_latest("0.1.364")
    self_upgrade.note_latest("0.1.365")

    assert len(spawned) == 2


def test_stale_stamp_expires(monkeypatch, spawned):
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: "/usr/local/bin/uv")
    self_upgrade._STAMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    self_upgrade._STAMP_PATH.write_text(
        json.dumps({"version": "0.1.364", "at": time.time() - self_upgrade._THROTTLE_SECONDS - 1})
    )

    self_upgrade.note_latest("0.1.364")

    assert len(spawned) == 1


def test_a_rolling_deploy_does_not_reset_the_throttle(monkeypatch, spawned):
    """During a zero-downtime deploy, old and new backend instances alternate
    headers for minutes. Each flip must read as 'already attempted', not as a
    fresh release, or every stale client storms for the whole window."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: "/usr/local/bin/uv")

    self_upgrade.note_latest("0.1.365")
    self_upgrade.note_latest("0.1.364")
    self_upgrade.note_latest("0.1.365")

    assert len(spawned) == 1


def test_an_unwritable_stamp_dir_never_crashes_the_request(monkeypatch, spawned, capsys, tmp_path):
    """note_latest rides on every API response; a ~/.stash we cannot write to
    (root-owned install, full disk) must not turn successful requests into
    crashes. No stamp means no throttle, so it must also not attempt."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: "/usr/local/bin/uv")
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    monkeypatch.setattr(self_upgrade, "_STAMP_PATH", blocker / "stamp.json")

    self_upgrade.note_latest("0.1.364")
    self_upgrade.note_latest("0.1.364")

    assert spawned == []
    # Said once, not once per response.
    assert capsys.readouterr().err.count("not writable") == 1


def test_a_corrupt_stamp_reads_as_never_attempted(monkeypatch, spawned):
    """A stamp holding valid-but-wrong JSON (external corruption) must not
    crash the request path; never-attempted is the state we want to act on."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: "/usr/local/bin/uv")
    self_upgrade._STAMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    self_upgrade._STAMP_PATH.write_text("null")

    self_upgrade.note_latest("0.1.364")

    assert len(spawned) == 1


def test_a_python_without_pip_is_reported_not_swallowed(monkeypatch, spawned, capsys):
    """uv venvs ship without pip; `python -m pip` there dies unseen in the
    detached child. Say the install can't upgrade instead of claiming it is."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: False)
    monkeypatch.setattr(self_upgrade, "_has_pip", lambda: False)

    self_upgrade.note_latest("0.1.364")

    assert spawned == []
    assert "no working upgrader" in capsys.readouterr().err


def test_pep668_pythons_get_the_flags_they_require(monkeypatch, spawned):
    """An externally-managed python (Debian's, the Fly Sprites we provision)
    refuses a plain `pip install` — into DEVNULL, in a detached child, forever.
    The same flags our sprite setup installs with make it land."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: False)
    monkeypatch.setattr(self_upgrade, "_has_pip", lambda: True)
    monkeypatch.setattr(self_upgrade, "_is_externally_managed", lambda: True)

    self_upgrade.note_latest("0.1.364")

    assert spawned[0][-2:] == ["--user", "--break-system-packages"]


def test_disable_stops_long_lived_processes_from_upgrading(monkeypatch, spawned):
    """The session watcher outlives the session it watches; swapping the
    package under it is how you get an ImportError hours later."""
    _as_release(monkeypatch, "0.1.334")
    monkeypatch.setattr(self_upgrade, "_is_uv_tool", lambda: True)
    monkeypatch.setattr(self_upgrade, "_find_uv", lambda: "/usr/local/bin/uv")

    self_upgrade.disable()
    self_upgrade.note_latest("0.1.364")

    assert spawned == []


def test_uv_environments_are_recognised_by_their_receipt(monkeypatch, tmp_path: Path):
    """Recognising uv by the shape of sys.prefix (.../uv/tools/<name>) passes on
    a default install and fails whenever UV_TOOL_DIR is set — which sends a uv
    install down the pip branch, where a uv environment has no pip and the
    upgrade dies unseen in a detached process. Caught end-to-end; pinned here."""
    env = tmp_path / "somewhere" / "custom-tool-dir" / "stashai"
    env.mkdir(parents=True)
    monkeypatch.setattr(self_upgrade.sys, "prefix", str(env))
    assert self_upgrade._is_uv_tool() is False

    (env / "uv-receipt.toml").write_text("")
    assert self_upgrade._is_uv_tool() is True


@pytest.mark.parametrize(
    ("have", "want", "older"),
    [
        ("0.1.334", "0.1.364", True),
        ("0.1.364", "0.1.364", False),
        ("0.1.365", "0.1.364", False),
        ("0.2.0", "0.1.999", False),
        # A locally built wheel carries a non-numeric trailer. It compares on
        # its release numbers rather than raising inside a request.
        ("0.1.334.dev0", "0.1.364", True),
    ],
)
def test_version_comparison(have: str, want: str, older: bool):
    assert self_upgrade._is_older(have, want) is older
