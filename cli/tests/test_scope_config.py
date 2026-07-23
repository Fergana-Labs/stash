"""Legacy `scope` config values must never reach the wire. Pre-2026-07 CLIs
stored a mode string ("repo") under the key that now holds a workspace UUID
sent as X-Stash-Scope; the backend hard-400s non-UUIDs, so an unmigrated
config would break every request after self-update — with plugin hooks
swallowing the failures silently."""

from __future__ import annotations

import json
from pathlib import Path

from cli import config as cli_config
from stashai.plugin import stash_client


def _write_config(tmp_path: Path, monkeypatch, body: dict) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    cfg_file = tmp_path / ".stash" / "config.json"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(json.dumps(body))
    monkeypatch.setattr(cli_config, "USER_CONFIG_FILE", cfg_file)
    return cfg_file


def test_legacy_mode_string_is_migrated_out_of_the_file(monkeypatch, tmp_path):
    cfg_file = _write_config(
        tmp_path, monkeypatch, {"base_url": "https://x", "api_key": "k", "scope": "repo"}
    )

    cfg = cli_config.load_config()

    assert "scope" not in cfg or not cfg.get("scope")
    assert "scope" not in json.loads(cfg_file.read_text())


def test_uuid_scope_survives_load(monkeypatch, tmp_path):
    scope = "1c9f8a52-0000-4000-8000-000000000000"
    cfg_file = _write_config(
        tmp_path, monkeypatch, {"base_url": "https://x", "api_key": "k", "scope": scope}
    )

    cfg = cli_config.load_config()

    assert cfg["scope"] == scope
    assert json.loads(cfg_file.read_text())["scope"] == scope


def test_plugin_client_never_sends_a_non_uuid_scope(monkeypatch, tmp_path):
    _write_config(tmp_path, monkeypatch, {"api_key": "k", "scope": "repo"})

    assert stash_client._configured_scope() == ""


def test_plugin_client_sends_uuid_scope(monkeypatch, tmp_path):
    scope = "1c9f8a52-0000-4000-8000-000000000000"
    _write_config(tmp_path, monkeypatch, {"api_key": "k", "scope": scope})

    assert stash_client._configured_scope() == scope
