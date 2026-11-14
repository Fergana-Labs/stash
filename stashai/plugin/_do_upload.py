"""Detached child process that uploads a transcript file.

Invoked by transcript_upload.spawn_transcript_upload(). Runs outside the
hook timeout so large files don't block the agent.

argv: script.py <transcript_path> <session_id> <agent_name> <cwd> <base_url> <api_key> <data_dir>
      [--skip-subagents] [--delay=<seconds>]
"""

import sys
import time
from pathlib import Path

from stashai.plugin.stash_client import StashClient


def main() -> None:
    (
        _, transcript_path, session_id, agent_name, cwd,
        base_url, api_key, data_dir,
    ) = sys.argv[:8]
    flags = sys.argv[8:]
    skip_subagents = "--skip-subagents" in flags
    for flag in flags:
        if flag.startswith("--delay="):
            time.sleep(float(flag.split("=", 1)[1]))

    path = Path(transcript_path)
    with StashClient(base_url=base_url, api_key=api_key, data_dir=data_dir) as client:
        client.upload_transcript(
            session_id=session_id,
            transcript_path=path,
            agent_name=agent_name,
            cwd=cwd,
        )

        subagents_dir = path.parent / path.stem / "subagents"
        if not skip_subagents and subagents_dir.is_dir():
            for sa_jsonl in subagents_dir.glob("agent-*.jsonl"):
                try:
                    client.upload_transcript(
                        session_id=sa_jsonl.stem,
                        transcript_path=sa_jsonl,
                        agent_name="claude-subagent",
                        cwd=cwd,
                    )
                except Exception:
                    pass


if __name__ == "__main__":
    main()
