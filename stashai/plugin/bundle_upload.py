"""Spawn a detached background process to upload bundle artifacts and generate summary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def spawn_bundle_upload(
    bundle_id: str,
    transcript_path: str,
    cwd: str,
    files_touched: list[str],
    workspace_id: str,
    agent_name: str,
    base_url: str,
    api_key: str,
) -> bool:
    script = Path(__file__).parent / "_do_bundle.py"
    env = os.environ.copy()
    env["BUNDLE_FILES_TOUCHED"] = json.dumps(files_touched)

    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                bundle_id, transcript_path, cwd, workspace_id,
                agent_name, base_url, api_key,
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        return False
    return True
