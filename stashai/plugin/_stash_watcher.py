"""Background watcher: waits for the Claude Code process to exit,
then uploads artifacts and generates the summary for the pre-created stash.

The stash is created eagerly at session start so the URL is known immediately.
This watcher fills in the content after the session ends.

argv: script.py <claude_pid> <session_id> <workspace_id> <agent_name>
                <base_url> <api_key> <cwd> <data_dir> <stash_id>
"""

import json
import os
import sys
import time
from pathlib import Path


def _wait_for_exit(pid: int, timeout: int = 7200) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(1)


def _find_transcript(session_id: str) -> str:
    transcript_dir = Path.home() / ".claude" / "projects"
    if not transcript_dir.is_dir():
        return ""
    for d in transcript_dir.iterdir():
        if not d.is_dir():
            continue
        candidate = d / f"{session_id}.jsonl"
        if candidate.is_file():
            return str(candidate)
    return ""


def main() -> None:
    (_, claude_pid_str, session_id, workspace_id, agent_name,
     base_url, api_key, cwd, data_dir, stash_id) = sys.argv

    claude_pid = int(claude_pid_str)
    _wait_for_exit(claude_pid)

    if not stash_id:
        return

    stats_path = Path(data_dir) / "stats.json"
    files_touched: list[str] = []
    if stats_path.is_file():
        try:
            stats = json.loads(stats_path.read_text())
            files_touched = stats.get("files_touched", stats.get("files_changed", []))
        except Exception:
            pass

    transcript_path = _find_transcript(session_id)

    from stashai.plugin.stash_upload import spawn_stash_upload

    if transcript_path:
        spawn_stash_upload(
            stash_id=stash_id,
            transcript_path=transcript_path,
            cwd=cwd,
            files_touched=files_touched,
            workspace_id=workspace_id,
            agent_name=agent_name,
            base_url=base_url,
            api_key=api_key,
        )


if __name__ == "__main__":
    main()
