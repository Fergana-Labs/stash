"""Detached child process that uploads a transcript file.

Invoked by transcript_upload.spawn_transcript_upload(). Runs outside the
hook timeout so large files don't block the agent.

argv: script.py <transcript_path> <session_id> <workspace_id> <agent_name> <cwd> <base_url> <api_key>
"""

import sys
from pathlib import Path

from stashai.plugin.stash_client import StashClient


def main() -> None:
    _, transcript_path, session_id, workspace_id, agent_name, cwd, base_url, api_key = sys.argv

    path = Path(transcript_path)
    with StashClient(base_url=base_url, api_key=api_key) as client:
        client.upload_transcript(
            workspace_id=workspace_id,
            session_id=session_id,
            transcript_path=path,
            agent_name=agent_name,
            cwd=cwd,
        )

        subagents_dir = path.parent / path.stem / "subagents"
        if subagents_dir.is_dir():
            for sa_jsonl in subagents_dir.glob("agent-*.jsonl"):
                try:
                    client.upload_transcript(
                        workspace_id=workspace_id,
                        session_id=sa_jsonl.stem,
                        transcript_path=sa_jsonl,
                        agent_name="claude-subagent",
                        cwd=cwd,
                    )
                except Exception:
                    pass


if __name__ == "__main__":
    main()
