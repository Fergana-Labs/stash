"""Assert that `stashai/plugin/assets/<agent>/` is a byte-identical copy of
`plugins/<agent>-plugin/`.

`stash install` reads from the shipped stashai assets so users don't need the
repo. `plugins/<agent>-plugin/` is the canonical source contributors edit.
Drift between the two means `stash install` would hand out stale hook files.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "plugins"
DST_DIR = REPO_ROOT / "stashai" / "plugin" / "assets"

AGENTS = ("cursor", "codex", "opencode")
IGNORE_NAMES = {"__pycache__"}
IGNORE_SUFFIXES = {".pyc"}


def _iter_tracked_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_NAMES for part in path.relative_to(root).parts):
            continue
        if path.suffix in IGNORE_SUFFIXES:
            continue
        yield path.relative_to(root), path


def test_every_agent_has_shipped_assets():
    for agent in AGENTS:
        assert (DST_DIR / agent).is_dir(), (
            f"Missing shipped assets for {agent!r}: "
            f"expected {DST_DIR / agent} to exist"
        )


def test_assets_match_plugin_sources_byte_for_byte():
    for agent in AGENTS:
        src_root = SRC_DIR / f"{agent}-plugin"
        dst_root = DST_DIR / agent

        src_map = dict(_iter_tracked_files(src_root))
        dst_map = dict(_iter_tracked_files(dst_root))

        assert set(src_map) == set(dst_map), (
            f"{agent}: file set drift between {src_root} and {dst_root}. "
            f"Only in source: {sorted(set(src_map) - set(dst_map))}; "
            f"only in assets: {sorted(set(dst_map) - set(src_map))}"
        )

        for rel in src_map:
            src_bytes = src_map[rel].read_bytes()
            dst_bytes = dst_map[rel].read_bytes()
            assert src_bytes == dst_bytes, (
                f"{agent}: {rel} differs between {src_root} and {dst_root}. "
                f"Re-run the vendor copy when editing plugin sources."
            )
