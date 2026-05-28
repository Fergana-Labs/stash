from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cli import import_history


def _write_codex_session(
    sessions_dir: Path,
    *,
    session_id: str,
    cwd: Path,
    repository_url: str,
) -> None:
    path = sessions_dir / "2026" / "05" / "28" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {
                    "id": session_id,
                    "cwd": str(cwd),
                    "timestamp": "2026-05-28T12:00:00Z",
                    "git": {
                        "repository_url": repository_url,
                        "branch": "feature",
                        "commit_hash": "abc123",
                    },
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                },
            }
        )
        + "\n"
    )


def test_discovers_codex_sessions_from_other_worktrees_of_same_repo(monkeypatch, tmp_path):
    repo = tmp_path / "stash"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:Fergana-Labs/stash.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    sessions_dir = tmp_path / ".codex" / "sessions"
    worktree = tmp_path / "worktrees" / "feature"
    other_repo = tmp_path / "unrelated-worktree"
    _write_codex_session(
        sessions_dir,
        session_id="same-repo",
        cwd=worktree,
        repository_url="https://github.com/Fergana-Labs/stash.git",
    )
    _write_codex_session(
        sessions_dir,
        session_id="other-repo",
        cwd=other_repo,
        repository_url="https://github.com/Fergana-Labs/other.git",
    )
    monkeypatch.setattr(import_history, "CODEX_SESSIONS_DIR", sessions_dir)

    conversations = import_history.discover_conversations(["codex"], repo_dir=repo)

    assert [conversation.session_id for conversation in conversations] == ["same-repo"]
    assert conversations[0].cwd == str(worktree)
    assert conversations[0].timestamp == datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
