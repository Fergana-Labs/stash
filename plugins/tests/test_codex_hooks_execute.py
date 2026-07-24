"""Execute every codex hook script end-to-end against its fixture.

`stash hook run codex <event>` runs these exact files via runpy, so this test
covers the same lines the dispatcher runs — an arity or import regression in
any script (like the historical `uploads_enabled(cfg, event)` TypeError that
broke every Codex session start) fails loudly here instead of in the field.
"""

from __future__ import annotations

import io
import json
import runpy
import sys
from pathlib import Path

import pytest

PLUGINS_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "codex"
SCRIPTS_DIR = PLUGINS_DIR / "codex-plugin" / "scripts"

_EVENT_FIXTURES = {
    "on_session_start": "session_start",
    "on_prompt": "prompt",
    "on_tool_use": "tool_use",
    "on_stop": "stop",
}


@pytest.mark.parametrize("event", sorted(_EVENT_FIXTURES))
def test_codex_hook_script_executes(event, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("STASH_CODEX_DATA", str(tmp_path / "codex-data"))
    fixture = (FIXTURES / f"{_EVENT_FIXTURES[event]}.json").read_text()
    monkeypatch.setattr(sys, "stdin", io.StringIO(fixture))
    monkeypatch.syspath_prepend(str(SCRIPTS_DIR))

    # The scripts import flat sibling modules (`adapt`, `config`); drop any
    # cached copy so each run binds this plugin's modules and this test's env.
    for mod in ("adapt", "config"):
        sys.modules.pop(mod, None)
    try:
        runpy.run_path(str(SCRIPTS_DIR / f"{event}.py"), run_name="__main__")
    finally:
        for mod in ("adapt", "config"):
            sys.modules.pop(mod, None)


def test_hooks_json_template_shape() -> None:
    """Codex rejects the whole hooks file when it sees unknown top-level keys,
    and trusts hooks by command hash — commands must be machine-independent."""
    data = json.loads((PLUGINS_DIR / "codex-plugin" / "hooks.json").read_text())
    assert set(data.keys()) == {"hooks"}
    for entries in data["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert hook["command"].startswith("stash hook run codex ")
