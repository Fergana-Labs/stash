"""The session-start drift check: cached plugin scripts vs the marketplace clone.

A cache that silently stops refreshing runs ever-staler hook scripts (the
Jun–Jul '26 upload outage). The check must speak up on a version mismatch and
stay silent when it cannot know or there is nothing to say.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "claude-plugin" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("cache_drift", SCRIPTS / "cache_drift.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(plugin_dir: Path, version: str) -> None:
    manifest_dir = plugin_dir / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text(json.dumps({"name": "stash", "version": version}))


def _layout(tmp_path: Path, cached: str, source: str | None) -> Path:
    """Build the ~/.claude/plugins/{cache,marketplaces} shape and return the
    cache root (what CLAUDE_PLUGIN_ROOT points at)."""
    cache_root = tmp_path / "plugins" / "cache" / "stash-plugins" / "stash" / cached
    _write_manifest(cache_root, cached)
    if source is not None:
        _write_manifest(
            tmp_path / "plugins" / "marketplaces" / "stash-plugins" / "plugins" / "claude-plugin",
            source,
        )
    return cache_root


def test_a_stale_cache_is_reported_with_both_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_layout(tmp_path, "0.1.85", "0.1.279")))
    warning = _load().plugin_cache_drift_warning()
    assert warning is not None
    assert "0.1.85" in warning
    assert "0.1.279" in warning


def test_matching_versions_stay_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_layout(tmp_path, "0.1.279", "0.1.279")))
    assert _load().plugin_cache_drift_warning() is None


def test_no_marketplace_clone_stays_silent(tmp_path, monkeypatch):
    # Installed without a marketplace checkout: there is nothing to compare against.
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_layout(tmp_path, "0.1.279", None)))
    assert _load().plugin_cache_drift_warning() is None


def test_a_dev_checkout_outside_the_cache_stays_silent(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "repo" / "plugins" / "claude-plugin"
    _write_manifest(plugin_dir, "0.1.279")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_dir))
    assert _load().plugin_cache_drift_warning() is None


def test_unset_plugin_root_stays_silent(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert _load().plugin_cache_drift_warning() is None
