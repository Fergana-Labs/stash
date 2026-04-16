"""Session stats: running counter written by stream_tool_use, read at session_end.

Replaces test_transcript_stats. The old path read Claude's JSONL transcript at
session_end; the new path amortizes counting across per-tool hooks.
"""

from __future__ import annotations

from stashai.plugin.event import HookEvent
from stashai.plugin.hooks import stream_session_end, stream_tool_use
from stashai.plugin.stash_client import StashClient
from stashai.plugin.state import load_state, record_tool_use, reset_stats


class _FakeClient(StashClient):
    def __init__(self):
        super().__init__(base_url="http://x", api_key="k")
        self.calls = []

    def _post(self, path, **kwargs):
        self.calls.append(kwargs.get("json", {}))
        return {}


def test_record_tool_use_increments_counts(tmp_path):
    record_tool_use(tmp_path, "edit", "a.py")
    record_tool_use(tmp_path, "edit", "a.py")  # dedup file
    record_tool_use(tmp_path, "bash", None)
    record_tool_use(tmp_path, "write", "b.py")

    state = load_state(tmp_path)
    stats = state["stats"]
    assert stats["tool_count"] == 4
    assert sorted(stats["tools_used"]) == ["bash", "edit", "write"]
    assert sorted(stats["files_changed"]) == ["a.py", "b.py"]


def test_read_only_tools_do_not_count_files(tmp_path):
    record_tool_use(tmp_path, "read", "a.py")
    record_tool_use(tmp_path, "grep", None)

    stats = load_state(tmp_path)["stats"]
    assert stats["tool_count"] == 2
    assert stats["files_changed"] == []


def test_reset_stats_clears(tmp_path):
    record_tool_use(tmp_path, "edit", "a.py")
    reset_stats(tmp_path)

    stats = load_state(tmp_path)["stats"]
    assert stats == {"tool_count": 0, "tools_used": [], "files_changed": []}


def test_stream_tool_use_writes_counter(tmp_path):
    cfg = {"workspace_id": "ws", "agent_name": "h", "client": "claude_code"}
    state = {"session_id": "s1"}
    c = _FakeClient()

    stream_tool_use(c, cfg, state, HookEvent(
        kind="tool_use", tool_name="edit",
        tool_input={"file_path": "x.py", "old_string": "a", "new_string": "b"},
    ), tmp_path)
    stream_tool_use(c, cfg, state, HookEvent(
        kind="tool_use", tool_name="bash",
        tool_input={"command": "ls"},
    ), tmp_path)

    stats = load_state(tmp_path)["stats"]
    assert stats["tool_count"] == 2
    assert sorted(stats["tools_used"]) == ["bash", "edit"]
    assert stats["files_changed"] == ["x.py"]


def test_stream_session_end_reads_counter(tmp_path):
    cfg = {"workspace_id": "ws", "agent_name": "h", "client": "claude_code"}
    state = {
        "session_id": "s1",
        "stats": {"tool_count": 7, "tools_used": ["edit", "bash"], "files_changed": ["a.py", "b.py"]},
    }
    c = _FakeClient()

    stream_session_end(c, cfg, state, HookEvent(kind="session_end", cwd="/tmp"))

    body = c.calls[-1]
    assert body["event_type"] == "session_end"
    assert body["content"] == "Session ended. 7 tool uses. 2 files changed."
    assert body["metadata"]["tool_count"] == 7
    assert body["metadata"]["files_changed"] == ["a.py", "b.py"]
    assert body["metadata"]["tools_used"] == ["edit", "bash"]
    assert "stats_truncated" not in body["metadata"]


def test_stream_session_end_with_no_prior_tool_use(tmp_path):
    cfg = {"workspace_id": "ws", "agent_name": "h", "client": "claude_code"}
    state = {"session_id": "s1"}
    c = _FakeClient()

    stream_session_end(c, cfg, state, HookEvent(kind="session_end"))

    body = c.calls[-1]
    assert body["content"] == "Session ended."
    assert body["metadata"]["tool_count"] == 0


def test_record_tool_use_ignores_empty_name(tmp_path):
    record_tool_use(tmp_path, "", "a.py")
    # No state.json should have been created.
    assert not (tmp_path / "state.json").exists()
