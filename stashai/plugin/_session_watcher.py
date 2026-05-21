"""Background watcher: waits for the Claude Code process to exit, then
spawns session artifact upload.

The session row is created eagerly at session start so the URL is known
immediately. Session content flows in live via hooks.push_event — this
watcher no longer needs to upload the transcript itself.

argv: script.py <agent_pid> <session_id> <workspace_id> <agent_name>
                <base_url> <api_key> <cwd> <data_dir> <session_row_id>
                [transcript_path]
"""

import json
import os
import sys
import time
from pathlib import Path


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _find_transcript(session_id: str, transcript_path: str = "") -> str:
    if transcript_path:
        candidate = Path(transcript_path)
        if candidate.is_file():
            return str(candidate)

    transcript_dir = Path.home() / ".claude" / "projects"
    if not transcript_dir.is_dir():
        return transcript_path
    for d in transcript_dir.iterdir():
        if not d.is_dir():
            continue
        candidate = d / f"{session_id}.jsonl"
        if candidate.is_file():
            return str(candidate)
    return transcript_path


def _state_transcript_path(data_dir: str) -> str:
    path = Path(data_dir) / "state.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text())
    except Exception:
        return ""
    value = data.get("transcript_path", "")
    return value if isinstance(value, str) else ""


def main() -> None:
    (
        _,
        agent_pid_str,
        session_id,
        workspace_id,
        agent_name,
        base_url,
        api_key,
        cwd,
        data_dir,
        session_row_id,
        *rest,
    ) = sys.argv

    agent_pid = int(agent_pid_str)
    initial_transcript_path = rest[0] if rest else ""

    if not session_row_id:
        return

    transcript_path = ""

    seed_path = initial_transcript_path or _state_transcript_path(data_dir)

    # Wait for the agent to exit. Events stream live via hooks.push_event; this
    # watcher only needs to fire artifact upload.
    while _is_alive(agent_pid):
        if not transcript_path or not Path(transcript_path).is_file():
            transcript_path = _find_transcript(session_id, seed_path)
        time.sleep(1)

    if not transcript_path or not Path(transcript_path).is_file():
        transcript_path = _find_transcript(session_id, seed_path)

    # Upload artifacts in a separate process.
    stats_path = Path(data_dir) / "state.json"
    files_touched: list[str] = []
    if stats_path.is_file():
        try:
            state = json.loads(stats_path.read_text())
            stats = state.get("stats", {})
            files_touched = stats.get("files_touched", stats.get("files_changed", []))
        except Exception:
            pass

    from stashai.plugin.session_upload import spawn_session_upload

    spawn_session_upload(
        session_row_id=session_row_id,
        transcript_path=transcript_path,
        cwd=cwd,
        files_touched=files_touched,
        workspace_id=workspace_id,
        session_id=session_id,
        agent_name=agent_name,
        base_url=base_url,
        api_key=api_key,
        data_dir=Path(data_dir),
    )


if __name__ == "__main__":
    main()
