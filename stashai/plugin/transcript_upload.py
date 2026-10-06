"""Background transcript upload for agents without a SessionEnd hook.

Codex fires Stop on every turn but has no session-end lifecycle event.
This module spawns a detached Python process that uploads the transcript
file, with a per-session cooldown so we don't POST on every single turn.

The backend appends new trace steps and preserves existing review IDs, so
duplicate snapshots are safe to resend.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

from stashai.plugin.upload_status import record_upload_failure

UPLOAD_COOLDOWN_SECONDS = 60


def _last_upload_path(data_dir: Path, session_id: str) -> Path:
    key = hashlib.sha256(session_id.encode()).hexdigest()
    return data_dir / "transcript_uploads" / key


def _cooldown_active(data_dir: Path, session_id: str) -> bool:
    p = _last_upload_path(data_dir, session_id)
    if not p.exists():
        return False
    try:
        return (time.time() - float(p.read_text().strip())) < UPLOAD_COOLDOWN_SECONDS
    except Exception:
        return False


def _record_upload(data_dir: Path, session_id: str) -> None:
    p = _last_upload_path(data_dir, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(time.time()))


def spawn_transcript_upload(
    data_dir: Path,
    transcript_path: str,
    session_id: str,
    agent_name: str,
    cwd: str,
    base_url: str,
    api_key: str,
) -> bool:
    """Spawn a detached process to upload the transcript. Returns True on spawn."""
    if not transcript_path or not session_id.strip():
        return False
    path = Path(transcript_path)
    if not path.is_file():
        return False
    if _cooldown_active(data_dir, session_id):
        return False

    _record_upload(data_dir, session_id)

    script = Path(__file__).parent / "_do_upload.py"
    env = os.environ.copy()

    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                str(path), session_id, agent_name, cwd, base_url, api_key,
                str(data_dir),
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception as e:
        record_upload_failure(data_dir, "transcript_spawn", e)
        return False

    return True
