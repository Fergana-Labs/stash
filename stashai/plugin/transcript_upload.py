"""Background transcript upload for agents without a SessionEnd hook.

Codex fires Stop on every turn but has no session-end lifecycle event.
This module spawns a detached Python process that uploads the transcript
file, with a per-session cooldown so we don't POST on every single turn.

The backend stores each upload as a new row keyed by session_id and
returns the latest on read, so repeated uploads are safe — they just
replace the previous snapshot.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

UPLOAD_COOLDOWN_SECONDS = 60


def _last_upload_path(data_dir: Path) -> Path:
    return data_dir / "last_transcript_upload"


def _cooldown_active(data_dir: Path) -> bool:
    p = _last_upload_path(data_dir)
    if not p.exists():
        return False
    try:
        return (time.time() - float(p.read_text().strip())) < UPLOAD_COOLDOWN_SECONDS
    except Exception:
        return False


def _record_upload(data_dir: Path) -> None:
    p = _last_upload_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(time.time()))


def spawn_transcript_upload(
    data_dir: Path,
    transcript_path: str,
    session_id: str,
    workspace_id: str,
    tag_name: str,
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
    if _cooldown_active(data_dir):
        return False

    _record_upload(data_dir)

    script = Path(__file__).parent / "_do_upload.py"
    env = os.environ.copy()

    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                str(path), session_id, workspace_id, tag_name, cwd, base_url, api_key,
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
