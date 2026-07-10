"""`_enable_marketplace_autoupdate` — the settings write that keeps the Claude
Code plugin from fossilizing.

Third-party marketplaces default to auto-update OFF, so without this flag an
installed plugin stays at its install-day version forever (a machine ran
June's hook scripts for a month this way). The write must be additive — a
user's existing settings survive untouched — and must refuse to touch a file
it cannot parse.
"""

from __future__ import annotations

import json
from pathlib import Path

from cli.main import _enable_marketplace_autoupdate


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def test_flag_is_added_to_the_existing_marketplace_entry(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "model": "opus",
                "extraKnownMarketplaces": {
                    "stash-plugins": {"source": {"source": "github", "repo": "Fergana-Labs/stash"}}
                },
            }
        )
    )

    assert _enable_marketplace_autoupdate(settings) is True

    data = _read(settings)
    assert data["extraKnownMarketplaces"]["stash-plugins"]["autoUpdate"] is True
    # Everything the user already had survives.
    assert data["model"] == "opus"
    assert data["extraKnownMarketplaces"]["stash-plugins"]["source"]["repo"] == (
        "Fergana-Labs/stash"
    )


def test_missing_settings_file_is_created_with_the_entry(tmp_path):
    settings = tmp_path / "nested" / "settings.json"

    assert _enable_marketplace_autoupdate(settings) is True

    entry = _read(settings)["extraKnownMarketplaces"]["stash-plugins"]
    assert entry["autoUpdate"] is True
    assert entry["source"] == {"source": "github", "repo": "Fergana-Labs/stash"}


def test_already_enabled_is_a_no_op(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "extraKnownMarketplaces": {
                    "stash-plugins": {
                        "source": {"source": "github", "repo": "Fergana-Labs/stash"},
                        "autoUpdate": True,
                    }
                }
            }
        )
    )
    before = settings.read_text()

    assert _enable_marketplace_autoupdate(settings) is True
    assert settings.read_text() == before


def test_unparseable_settings_are_left_alone(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{not json")

    assert _enable_marketplace_autoupdate(settings) is False
    # The broken file is preserved for the user to fix, not clobbered.
    assert settings.read_text() == "{not json"
