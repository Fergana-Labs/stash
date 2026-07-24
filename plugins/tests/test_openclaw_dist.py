"""Assert that the committed `plugins/openclaw-plugin/dist/index.js` is a
fresh build of `index.ts`.

Openclaw refuses TypeScript entries for installed plugin packages, so the
compiled output is committed and shipped inside the stashai assets
(`test_assets_in_sync.py` covers the assets copy). This rebuilds with the
pinned esbuild from the package.json `build` script into a temp dir and
diffs bytes, so a source edit without a rebuild reds CI. Requires node/npm.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "plugins" / "openclaw-plugin"


def test_committed_dist_matches_rebuild(tmp_path: Path):
    shutil.copy(PLUGIN_DIR / "index.ts", tmp_path)
    shutil.copy(PLUGIN_DIR / "package.json", tmp_path)

    subprocess.run(
        ["npm", "run", "build"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        timeout=120,
    )

    rebuilt = (tmp_path / "dist" / "index.js").read_bytes()
    committed = (PLUGIN_DIR / "dist" / "index.js").read_bytes()
    assert rebuilt == committed, (
        "plugins/openclaw-plugin/dist/index.js is stale. Re-run `npm run build` "
        "in plugins/openclaw-plugin and copy dist/ into "
        "stashai/plugin/assets/openclaw/."
    )
