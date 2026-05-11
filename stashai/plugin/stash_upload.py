"""Spawn a detached background process to upload stash artifacts and generate summary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def spawn_stash_watcher(
    agent_pid: int,
    session_id: str,
    workspace_id: str,
    agent_name: str,
    base_url: str,
    api_key: str,
    cwd: str,
    data_dir: Path,
    stash_id: str,
    transcript_path: str = "",
) -> bool:
    """Watch an agent process and finalize its stash after it exits."""
    script = Path(__file__).parent / "_stash_watcher.py"
    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                str(agent_pid), session_id, workspace_id, agent_name,
                base_url, api_key, cwd, str(data_dir), stash_id, transcript_path,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        return False
    return True


def spawn_stash_upload(
    stash_id: str,
    transcript_path: str,
    cwd: str,
    files_touched: list[str],
    workspace_id: str,
    session_id: str,
    agent_name: str,
    base_url: str,
    api_key: str,
) -> bool:
    script = Path(__file__).parent / "_do_stash.py"
    env = os.environ.copy()
    env["STASH_FILES_TOUCHED"] = json.dumps(files_touched)

    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                stash_id, transcript_path, cwd, workspace_id, session_id,
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
