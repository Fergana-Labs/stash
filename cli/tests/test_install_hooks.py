"""Tests for `_merge_json_hooks` — the idempotent hooks.json merger used by
`stash install` / `stash connect` to wire agent hook files.

Covers the multi-root stale-entry case: a user who has run `stash install`
from several different PLUGIN_ROOTs (old dev checkouts, prior pipx versions)
should end up with a single stash-owned entry per event after the next install,
regardless of which root they install from.
"""

from __future__ import annotations

import json
from pathlib import Path

from cli.main import _merge_json_hooks

CURSOR_TEMPLATE = json.dumps(
    {
        "version": 1,
        "hooks": {
            "sessionStart": [
                {
                    "command": "bash ${PLUGIN_ROOT}/scripts/_run.sh on_session_start",
                    "timeout": 5,
                }
            ],
        },
    }
)


def _stash_entry(plugin_root: str) -> dict:
    return {
        "command": f"bash {plugin_root}/scripts/_run.sh on_session_start",
        "timeout": 5,
    }


def _write_hooks(dest: Path, entries: list[dict]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"version": 1, "hooks": {"sessionStart": entries}}))


def test_merge_sweeps_stale_entries_from_other_roots(tmp_path: Path) -> None:
    # Simulate a user who installed from two different dev checkouts plus pipx,
    # plus a user-added entry that must be preserved.
    dest = tmp_path / "cursor" / "hooks.json"
    octopus_root = "/fake/projects/octopus-cli/stashai/plugin/assets/cursor"
    disco_root = "/fake/projects/stash-discoverability-2/stashai/plugin/assets/cursor"
    pipx_root = tmp_path / "pipx/stashai/plugin/assets/cursor"
    user_entry = {"command": "echo user-hook", "timeout": 1}

    _write_hooks(
        dest,
        [
            _stash_entry(octopus_root),
            _stash_entry(disco_root),
            user_entry,
        ],
    )

    status = _merge_json_hooks(dest, CURSOR_TEMPLATE, pipx_root)

    assert status == "installed"
    result = json.loads(dest.read_text())
    entries = result["hooks"]["sessionStart"]

    # User entry preserved, all stash entries replaced by the single pipx one.
    assert user_entry in entries
    stash_entries = [e for e in entries if "stashai/plugin/assets/cursor" in e["command"]]
    assert len(stash_entries) == 1
    assert str(pipx_root) in stash_entries[0]["command"]


def test_merge_is_idempotent_from_same_root(tmp_path: Path) -> None:
    dest = tmp_path / "cursor" / "hooks.json"
    pipx_root = tmp_path / "pipx/stashai/plugin/assets/cursor"

    first = _merge_json_hooks(dest, CURSOR_TEMPLATE, pipx_root)
    second = _merge_json_hooks(dest, CURSOR_TEMPLATE, pipx_root)

    assert first == "installed"
    assert second == "skipped"


def test_merge_preserves_user_entries(tmp_path: Path) -> None:
    dest = tmp_path / "cursor" / "hooks.json"
    pipx_root = tmp_path / "pipx/stashai/plugin/assets/cursor"
    user_entry = {"command": "echo my-own-hook", "timeout": 2}

    _write_hooks(dest, [user_entry])
    _merge_json_hooks(dest, CURSOR_TEMPLATE, pipx_root)

    entries = json.loads(dest.read_text())["hooks"]["sessionStart"]
    assert user_entry in entries
