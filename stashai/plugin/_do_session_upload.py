"""Detached background process: upload session artifacts.

Invoked by session_upload.spawn_session_upload(). Runs outside the hook
timeout so large uploads don't block the agent.

argv: script.py <session_row_id> <transcript_path> <cwd> <workspace_id>
                <session_id> <agent_name> <base_url> <api_key> <data_dir>

env: SESSION_FILES_TOUCHED = JSON list of file paths from the session
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from stashai.plugin.stash_client import StashClient

SKIP_PATTERNS = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "credentials.json",
    ".npmrc",
    ".pypirc",
}
SKIP_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".jks"}
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB per file


def _should_skip(file_path: str) -> bool:
    name = Path(file_path).name
    if name in SKIP_PATTERNS:
        return True
    if any(name.endswith(ext) for ext in SKIP_EXTENSIONS):
        return True
    return False


def _collect_git_files(cwd: str) -> list[str]:
    """Get files modified or created during the session via git."""
    files = []
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if result.returncode == 0:
            files.extend(result.stdout.strip().splitlines())
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if result.returncode == 0:
            files.extend(result.stdout.strip().splitlines())
    except Exception:
        pass
    return files


def _resolve_paths(files_touched: list[str], cwd: str) -> list[str]:
    """Combine tool-tracked files with git-discovered files, deduplicate."""
    all_paths = set()

    for fp in files_touched:
        p = Path(fp)
        if p.is_absolute():
            all_paths.add(str(p))
        else:
            all_paths.add(str(Path(cwd) / fp))

    git_files = _collect_git_files(cwd)
    for gf in git_files:
        p = Path(gf)
        if p.is_absolute():
            all_paths.add(str(p))
        else:
            all_paths.add(str(Path(cwd) / gf))

    return sorted(all_paths)


def main() -> None:
    _, session_row_id, _, cwd, workspace_id, _, _, base_url, api_key, data_dir = sys.argv
    files_touched = json.loads(os.environ.get("SESSION_FILES_TOUCHED", "[]"))

    with StashClient(base_url=base_url, api_key=api_key, data_dir=data_dir) as client:
        all_paths = _resolve_paths(files_touched, cwd)
        for fp in all_paths:
            if _should_skip(fp):
                continue
            p = Path(fp)
            if not p.is_file():
                continue
            if p.stat().st_size > MAX_FILE_SIZE:
                continue
            try:
                content = p.read_bytes()
                try:
                    display_path = str(p.relative_to(cwd))
                except ValueError:
                    display_path = str(p)
                client.upload_session_artifact(workspace_id, session_row_id, display_path, content)
            except Exception:
                continue


if __name__ == "__main__":
    main()
