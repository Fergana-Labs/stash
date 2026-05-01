"""Detached child process that uploads a transcript file.

Invoked by transcript_upload.spawn_transcript_upload(). Runs outside the
hook timeout so large files don't block the agent.

argv: script.py <transcript_path> <session_id> <workspace_id> <tag_name> <cwd> <base_url> <api_key>
"""

import sys
from pathlib import Path

from stashai.plugin.stash_client import StashClient


def main() -> None:
    _, transcript_path, session_id, workspace_id, tag_name, cwd, base_url, api_key = sys.argv

    with StashClient(base_url=base_url, api_key=api_key) as client:
        client.upload_transcript(
            workspace_id=workspace_id,
            session_id=session_id,
            transcript_path=Path(transcript_path),
            tag_name=tag_name,
            cwd=cwd,
        )


if __name__ == "__main__":
    main()
