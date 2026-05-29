import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_claude_marketplace_version_matches_plugin_manifest():
    plugin_manifest = json.loads(
        (REPO_ROOT / "plugins/claude-plugin/.claude-plugin/plugin.json").read_text()
    )
    marketplace = json.loads((REPO_ROOT / ".claude-plugin/marketplace.json").read_text())

    assert marketplace["plugins"][0]["version"] == plugin_manifest["version"]
