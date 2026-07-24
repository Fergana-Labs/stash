#!/usr/bin/env python3
"""Warn when the cached plugin scripts drift from the marketplace clone.

Claude Code copies a plugin into ~/.claude/plugins/cache/<marketplace>/<name>/…
and refreshes that copy only when the marketplace registers a version bump. If
that refresh breaks, the cache runs ever-staler scripts and nothing says so:
hooks keep exiting 0 while the scripts drift incompatible with the library
they pin (a machine spent Jun 12–Jul 10 '26 uploading nothing this way). The
marketplace clone lives on the same disk, so the cheapest honest check is
comparing the two manifests at session start.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

MANIFEST = Path(".claude-plugin") / "plugin.json"
# Where this plugin lives inside the marketplace repo (the stash monorepo).
# The module ships with that plugin, so the path is a fact about itself.
SOURCE_SUBDIR = Path("plugins") / "claude-plugin"


def _version(manifest: Path) -> str | None:
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) and version else None


def plugin_cache_drift_warning() -> str | None:
    """Warning text when the cache and marketplace manifests disagree, else None."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return None
    cache_root = Path(root).resolve()
    parts = cache_root.parts
    # A local dev checkout doesn't run from a marketplace cache; nothing to compare.
    if "cache" not in parts:
        return None
    idx = parts.index("cache")
    if len(parts) <= idx + 1:
        return None
    marketplace = parts[idx + 1]
    plugins_dir = Path(*parts[:idx])
    cached = _version(cache_root / MANIFEST)
    source = _version(plugins_dir / "marketplaces" / marketplace / SOURCE_SUBDIR / MANIFEST)
    if not cached or not source or cached == source:
        return None
    return (
        f"Stash plugin scripts are stale: this session runs cached v{cached} but "
        f"the '{marketplace}' marketplace has v{source}. Hooks may be running old "
        "code — update the stash plugin from /plugin in Claude Code."
    )
