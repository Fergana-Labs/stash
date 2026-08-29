from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli import import_history, main


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


def test_import_limit_uploads_only_the_most_recent_conversations(monkeypatch):
    imported = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    conversations = [f"conversation-{index}" for index in range(8)]
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "key"})
    monkeypatch.setattr(main.telemetry, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "load_enabled_agents", lambda: ["codex"])
    monkeypatch.setattr(main, "_conversations_to_import", lambda agents: conversations)
    monkeypatch.setattr(main, "_client", lambda: FakeClient())
    monkeypatch.setattr(main, "_write_import_status", lambda **kwargs: None)
    monkeypatch.setattr(main, "_report_import_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        import_history,
        "upload_conversation",
        lambda client, conversation: imported.append(conversation),
    )

    main.import_history_cmd(status=False, limit=5)

    assert set(imported) == set(conversations[:5])


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Start with my 5 most recent sessions", (5, 5)),
        ("Import all 12 sessions", (12, None)),
        ("Don't import past sessions", None),
    ],
)
def test_setup_offers_a_five_session_start(monkeypatch, answer, expected):
    calls = []
    conversations = [f"conversation-{index}" for index in range(12)]
    monkeypatch.setattr(main, "_conversations_to_import", lambda agents: conversations)
    monkeypatch.setattr(
        import_history,
        "summarize_discovery",
        lambda found: {"codex": {"count": len(found), "total_size_bytes": 1024}},
    )
    monkeypatch.setattr(main.questionary, "select", lambda *args, **kwargs: _Answer(answer))
    monkeypatch.setattr(
        main,
        "_spawn_history_import",
        lambda count, *, limit=None: calls.append((count, limit)),
    )

    main._onboarding_import_history(["codex"])

    assert calls == ([] if expected is None else [expected])


class _Answer:
    def __init__(self, value):
        self.value = value

    def ask(self):
        return self.value
