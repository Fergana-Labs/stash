"""The CLI streaming toggle and the plugin's streaming gate must agree on the
on-disk format of `stopped_streaming`. They live in separate packages, so a
silent format drift (e.g. the writer emitting a list the reader treats as a
boolean) disables all streaming with no error. This test pins the contract by
writing with the CLI and reading with the plugin against one config file.
"""

from __future__ import annotations

import json

from cli import config as cli_config
from stashai.plugin import scope as scope_mod


def _wire(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"api_key": "k"}))
    monkeypatch.setattr(cli_config, "USER_CONFIG_FILE", cfg)
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    return cfg


def test_stop_then_plugin_sees_streaming_off(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    cli_config.stop_streaming()
    assert cli_config.streaming_stopped()
    assert not scope_mod.streaming_enabled()


def test_start_then_plugin_sees_streaming_on(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    cli_config.stop_streaming()
    cli_config.start_streaming()
    assert not cli_config.streaming_stopped()
    assert scope_mod.streaming_enabled()


def test_stopped_streaming_is_written_as_a_bool(tmp_path, monkeypatch):
    """The plugin reads the value as a boolean; the writer must persist a JSON
    bool, not a list/string the reader would misinterpret as truthy."""
    cfg = _wire(tmp_path, monkeypatch)
    cli_config.stop_streaming()
    assert json.loads(cfg.read_text())["stopped_streaming"] is True
    cli_config.start_streaming()
    assert json.loads(cfg.read_text())["stopped_streaming"] is False
