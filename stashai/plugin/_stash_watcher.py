"""Background watcher: waits for the Claude Code process to exit, then
spawns artifact upload + AI summary generation for the stash.

The stash is created eagerly at session start so the URL is known
immediately. Session content flows in live via hooks.push_event — this
watcher no longer needs to upload the transcript itself.

argv: script.py <claude_pid> <session_id> <workspace_id> <agent_name>
                <base_url> <api_key> <cwd> <data_dir> <stash_id>
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

    if not stash_id:
        return

    transcript_path = ""

    # Wait for Claude Code to exit. Events stream live via hooks.push_event;
    # we only need to know when the session is done so we can fire off
    # artifact upload + AI summary generation.
    while _is_alive(claude_pid):
        if not transcript_path:
            transcript_path = _find_transcript(session_id)
        time.sleep(1)

    if not transcript_path:
        transcript_path = _find_transcript(session_id)
    if not transcript_path:
        return

    # Upload artifacts and generate summary in a separate process
    stats_path = Path(data_dir) / "stats.json"
    files_touched: list[str] = []
    if stats_path.is_file():
        try:
            stats = json.loads(stats_path.read_text())
            files_touched = stats.get("files_touched", stats.get("files_changed", []))
        except Exception:
            pass

    from stashai.plugin.stash_upload import spawn_stash_upload

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
