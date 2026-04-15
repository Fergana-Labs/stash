"""Transcript stats: tail-bounded read so big sessions don't blow the hook timeout.

Asserts the small-file path returns full counts, and the large-file path
returns tail-only counts with `truncated=True`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(SHARED))

import hooks  # noqa: E402


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def test_small_transcript_full_read(tmp_path):
    path = tmp_path / "small.jsonl"
    _write_jsonl(path, [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "a.py"}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        {"type": "tool_use", "name": "Write", "input": {"file_path": "b.py"}},
        {"type": "user", "content": "ignored"},
    ])
    stats = hooks.count_transcript_stats(str(path))
    assert stats["tool_count"] == 3
    assert sorted(stats["files_changed"]) == ["a.py", "b.py"]
    assert sorted(stats["tools_used"]) == ["Bash", "Edit", "Write"]
    assert stats["truncated"] is False


def test_huge_transcript_tail_read(tmp_path, monkeypatch):
    """Force the tail path with a tiny cap so we don't have to write 5MB."""
    monkeypatch.setattr(hooks, "_TRANSCRIPT_TAIL_BYTES", 256)
    path = tmp_path / "big.jsonl"
    # Each padded line is ~150 bytes; write enough that the file exceeds 256B.
    entries = []
    for i in range(50):
        entries.append({
            "type": "tool_use",
            "name": "Edit",
            "input": {"file_path": f"file{i}.py"},
            "_pad": "x" * 100,
        })
    _write_jsonl(path, entries)

    stats = hooks.count_transcript_stats(str(path))
    assert stats["truncated"] is True
    # Tail captures only the last few entries — fewer than total 50.
    assert 0 < stats["tool_count"] < 50
    # Whatever survived parses cleanly without raising.
    assert all(fp.startswith("file") and fp.endswith(".py") for fp in stats["files_changed"])


def test_missing_transcript_returns_zeros():
    stats = hooks.count_transcript_stats("")
    assert stats == {"tool_count": 0, "files_changed": [], "tools_used": [], "truncated": False}


def test_nonexistent_transcript_returns_zeros(tmp_path):
    stats = hooks.count_transcript_stats(str(tmp_path / "nope.jsonl"))
    assert stats["tool_count"] == 0
    assert stats["files_changed"] == []
    assert stats["tools_used"] == []
    assert stats["truncated"] is False


def test_malformed_lines_skipped(tmp_path):
    path = tmp_path / "messy.jsonl"
    path.write_text(
        json.dumps({"type": "tool_use", "name": "Edit", "input": {"file_path": "a.py"}}) + "\n"
        "this-is-not-json\n"
        + json.dumps({"type": "tool_use", "name": "Bash", "input": {}}) + "\n"
    )
    stats = hooks.count_transcript_stats(str(path))
    assert stats["tool_count"] == 2
    assert stats["files_changed"] == ["a.py"]
