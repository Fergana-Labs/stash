"""Detached background process: upload stash artifacts + generate summary.

Invoked by stash_upload.spawn_stash_upload(). Runs outside the hook
timeout so large uploads and LLM calls don't block the agent.

argv: script.py <stash_id> <transcript_path> <cwd> <workspace_id>
                <session_id> <agent_name> <base_url> <api_key>

env: STASH_FILES_TOUCHED = JSON list of file paths from the session
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


def _read_transcript_text(transcript_path: Path) -> str | None:
    if not transcript_path.is_file():
        return None
    raw = transcript_path.read_bytes()
    # Decompress if gzipped
    if raw[:2] == b"\x1f\x8b":
        import gzip

        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _history_text(client: StashClient, workspace_id: str, session_id: str) -> str | None:
    if not session_id.strip():
        return None
    try:
        events = client.query_events(
            workspace_id=workspace_id,
            session_id=session_id,
            limit=200,
            order="asc",
        )
    except Exception:
        return None
    if not events:
        return None

    lines = []
    for event in events:
        event_type = event.get("event_type", "")
        tool = event.get("tool_name") or ""
        content = event.get("content") or ""
        created_at = event.get("created_at") or ""
        label = event_type if not tool else f"{event_type}:{tool}"
        lines.append(f"[{created_at}] {label}\n{content}")
    return "\n\n---\n\n".join(lines)


def _generate_summary(source_text: str, source_label: str) -> str | None:
    """Call Haiku to summarize the session transcript or streamed events."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    # Truncate to ~150K chars to stay within Haiku's context
    max_chars = 150_000
    if len(source_text) > max_chars:
        source_text = source_text[:max_chars] + f"\n\n[... {source_label} truncated ...]"

    try:
        import httpx

        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 2048,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Summarize this coding session {source_label}. Include:\n"
                            "1. What the session accomplished (1-2 sentences)\n"
                            "2. Key files modified or created\n"
                            "3. Important decisions made\n"
                            "4. Any unfinished work or known issues\n\n"
                            "Keep the summary concise and useful for someone picking up "
                            "where this session left off.\n\n"
                            f"SESSION {source_label.upper()}:\n{source_text}"
                        ),
                    }
                ],
            },
            timeout=120.0,
        )
        if resp.is_success:
            data = resp.json()
            return data["content"][0]["text"]
    except Exception:
        pass
    return None


def main() -> None:
    _, stash_id, transcript_path, cwd, workspace_id, session_id, agent_name, base_url, api_key = (
        sys.argv
    )
    files_touched = json.loads(os.environ.get("STASH_FILES_TOUCHED", "[]"))

    with StashClient(base_url=base_url, api_key=api_key) as client:
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
                client.upload_stash_artifact(stash_id, display_path, content)
            except Exception:
                continue

        client.update_stash(stash_id, status="summarizing")
        tp = Path(transcript_path) if transcript_path else None
        source_text = _read_transcript_text(tp) if tp and tp.is_file() else None
        source_label = "transcript"
        if not source_text:
            source_text = _history_text(client, workspace_id, session_id)
            source_label = "history events"

        summary = _generate_summary(source_text, source_label) if source_text else None

        if summary:
            client.update_stash(stash_id, summary=summary, status="ready")
        else:
            client.update_stash(stash_id, status="failed")


if __name__ == "__main__":
    main()
