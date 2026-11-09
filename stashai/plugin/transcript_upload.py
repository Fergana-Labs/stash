"""Background transcript upload after each turn.

Codex fires Stop on every turn but has no session-end lifecycle event, and
Claude Code sessions can stay open for days, so both upload from Stop. This
module spawns a detached Python process that uploads the transcript file,
at most once per cooldown per session. A turn that ends inside the cooldown
schedules one delayed upload for when it ends, so the last turn is never
left out.

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


def _last_upload_at(data_dir: Path, session_id: str) -> float | None:
    """When the last upload ran, or when a delayed one will run (a future time)."""
    p = _last_upload_path(data_dir, session_id)
    try:
        return float(p.read_text().strip())
    except Exception:
        return None


def _record_upload(data_dir: Path, session_id: str, at: float) -> None:
    p = _last_upload_path(data_dir, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(at))


def spawn_transcript_upload(
    data_dir: Path,
    transcript_path: str,
    session_id: str,
    agent_name: str,
    cwd: str,
    base_url: str,
    api_key: str,
    include_subagents: bool = True,
) -> bool:
    """Spawn a detached process to upload the transcript. Returns True on spawn.

    Pass include_subagents=False while the session is live: the backend keeps
    only the first upload of a subagent's transcript, so uploading one that is
    still running would freeze it half-finished.
    """
    if not transcript_path or not session_id.strip():
        return False
    path = Path(transcript_path)
    if not path.is_file():
        return False
    # Upload now if the last upload is more than a cooldown old. Otherwise
    # schedule one delayed upload for when the cooldown ends, so the latest
    # turn still goes up. Turns before that delayed upload runs need nothing:
    # it reads the transcript when it runs.
    now = time.time()
    last = _last_upload_at(data_dir, session_id)
    delay = 0.0
    if last is not None:
        if last > now:
            return False
        delay = max(0.0, last + UPLOAD_COOLDOWN_SECONDS - now)

    _record_upload(data_dir, session_id, now + delay)

    script = Path(__file__).parent / "_do_upload.py"
    env = os.environ.copy()

    try:
        subprocess.Popen(
            [
                sys.executable, str(script),
                str(path), session_id, agent_name, cwd, base_url, api_key,
                str(data_dir),
                *([] if include_subagents else ["--skip-subagents"]),
                *([f"--delay={delay:.0f}"] if delay else []),
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
