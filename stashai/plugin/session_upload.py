"""Spawn detached background processes for session artifact upload."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from stashai.plugin.upload_status import record_upload_failure


def spawn_session_watcher(
    agent_pid: int,
    session_id: str,
    workspace_id: str,
    agent_name: str,
    base_url: str,
    api_key: str,
    cwd: str,
    data_dir: Path,
    session_row_id: str,
    transcript_path: str = "",
) -> bool:
    """Watch an agent process and finalize session artifacts after it exits."""
    script = Path(__file__).parent / "_session_watcher.py"
    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                str(agent_pid), session_id, workspace_id, agent_name,
                base_url, api_key, cwd, str(data_dir), session_row_id, transcript_path,
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


def spawn_session_upload(
    session_row_id: str,
    transcript_path: str,
    cwd: str,
    files_touched: list[str],
    workspace_id: str,
    session_id: str,
    agent_name: str,
    base_url: str,
    api_key: str,
    data_dir: Path | None = None,
) -> bool:
    script = Path(__file__).parent / "_do_session_upload.py"
    env = os.environ.copy()
    env["SESSION_FILES_TOUCHED"] = json.dumps(files_touched)
    upload_status_dir = str(data_dir or "")

    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                session_row_id, transcript_path, cwd, workspace_id, session_id,
                agent_name, base_url, api_key, upload_status_dir,
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception as e:
        record_upload_failure(data_dir, "artifact_spawn", e)
        return False
    return True
