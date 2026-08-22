"""Lock the fail-loud invariant on every plugin's hook scripts.

Each plugin source tree (`plugins/<agent>-plugin/scripts/`) and its shipped
assets (`stashai/plugin/assets/<agent>/scripts/`) must not contain a bare
`except Exception:`/`except BaseException:` or an unnamed `except:` that would
swallow a Stash API failure (upload, session-create, tool-use, session-end).
A swallow lets telemetry vanish without a trace; these must fail loud to the
agent's hook runner instead.

Two legitimate parse/IO guards are allowed to keep a default, but only under a
narrow, specific exception type — never a bare catch-all:
  - cursor adapt.py `_parse_tool_output` -> `except json.JSONDecodeError`
  - claude config.py `get_stdin_data` / `_read_json` -> `except (json.JSONDecodeError, OSError)`
hermes and pi have NO such parse guards — every Stash call in their on_* hooks
is fail-loud, so no narrow guard is allowed or needed there.

This test also asserts the STAS-019 silent-default (`if not cwd: return False`)
is absent from every config.py, so a missing working dir fails loud instead of
silently falling back.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "plugins"
DST_DIR = REPO_ROOT / "stashai" / "plugin" / "assets"

AGENTS = ("claude", "codex", "cursor", "gemini", "openclaw", "opencode", "hermes", "pi")

# Agents whose hook scripts are also mirrored into `stashai/plugin/assets/`.
# claude/gemini/openclaw are delivered outside the shipped-asset tree, so only
# the canonical source is checked for them.
ASSET_AGENTS = ("codex", "cursor", "opencode", "hermes", "pi")

BARE_CATCHALL = re.compile(r"^\s*except (Exception|BaseException):")
UNNAMED_CATCHALL = re.compile(r"^\s*except:")

# STAS-019's silent-default: `if not cwd:` directly falling through to
# `return False` swallows a missing working dir instead of failing loud. We
# match the immediate fallback only (the exact pattern STAS-019 banned) so the
# pi is_fusion_managed walk — which legitimately returns False once a real,
# non-empty cwd is narrowed — is not falsely flagged.
SILENT_DEFAULT = re.compile(r"if not cwd\s*:\s*return False")


def _script_files(root: Path) -> list[Path]:
    scripts = root / "scripts"
    if not scripts.is_dir():
        return []
    return sorted(p for p in scripts.glob("*.py") if "__pycache__" not in p.parts)


def _check_tree(agent: str, root: Path) -> None:
    assert (root / "scripts").is_dir(), f"{agent}: expected {root / 'scripts'} to exist"
    for path in _script_files(root):
        lines = path.read_text().splitlines()
        for idx, line in enumerate(lines, start=1):
            assert not BARE_CATCHALL.search(line), (
                f"{agent}: {path.relative_to(REPO_ROOT)}:{idx} has a bare "
                f"{line.strip()!r} catch-all that would swallow an error. "
                "Stash API failures must fail loud, not vanish silently."
            )
            assert not UNNAMED_CATCHALL.search(line), (
                f"{agent}: {path.relative_to(REPO_ROOT)}:{idx} has an unnamed "
                f"`except:` that catches everything. Use a narrow, specific "
                "exception type or fail loud."
            )


@pytest.mark.parametrize("agent", AGENTS)
def test_no_swallow_source_and_assets(agent: str) -> None:
    """Every hook script in the source tree and its shipped assets must fail
    loud — no bare catch-all may swallow a Stash API error."""
    _check_tree(agent, SRC_DIR / f"{agent}-plugin")
    if agent in ASSET_AGENTS:
        _check_tree(agent, DST_DIR / agent)


def test_config_no_silent_default() -> None:
    """None of the plugin config.py files may carry STAS-019's
    `if not cwd: return False` silent-default, which makes a missing working
    dir silently fall back instead of failing loud."""
    for agent in AGENTS:
        cfgs = [SRC_DIR / f"{agent}-plugin" / "scripts" / "config.py"]
        if agent in ASSET_AGENTS:
            cfgs.append(DST_DIR / agent / "scripts" / "config.py")
        for cfg in cfgs:
            assert cfg.is_file(), f"expected {cfg.relative_to(REPO_ROOT)} to exist"
            text = cfg.read_text()
            assert SILENT_DEFAULT.search(text) is None, (
                f"{cfg.relative_to(REPO_ROOT)} carries the "
                f"`if not cwd: return False` silent-default. Fail loud "
                "with ValueError instead."
            )
