import json
from uuid import uuid4

import pytest

from stashai.local_history import CodexHistory, pack_page, validate_request


def transcript(home, *, text="Please improve this website", extra=(), archived=False):
    sid = str(uuid4())
    root = home / ".codex" / ("archived_sessions" if archived else "sessions")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"rollout-{sid}.jsonl"
    rows = [
        {
            "type": "session_meta",
            "payload": {"id": sid, "cwd": "/projects/website", "timestamp": "2026-10-15T12:00:00Z"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "PRIVATE_SYSTEM_SETUP"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "PRIVATE_REASONING"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "write_file",
                "arguments": '{"html":"<h1>Website</h1>"}',
            },
        },
        {
            "type": "response_item",
            "payload": {"type": "function_call_output", "output": "Wrote index.html"},
        },
        *extra,
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return sid, path


def test_search_and_read_unrecorded_sessions_without_importing(tmp_path):
    sid, path = transcript(tmp_path)
    original = path.read_bytes()
    history = CodexHistory(tmp_path)
    found = history.run("search", {"query": "website", "agent": "codex"})
    assert found["results"][0]["id"] == sid
    assert found["results"][0]["match_offset"] == 0
    page = history.run("read", {"id": sid, "limit": 2})
    assert [e["role"] for e in page["events"]] == ["user", "assistant"]
    assert page["has_more"] and page["total"] == 3 and page["next_offset"] == 2
    tail = history.run("read", {"id": sid, "offset": 2})
    assert tail["events"][0]["content"] == "Wrote index.html"
    assert not tail["has_more"]
    assert "PRIVATE" not in json.dumps(page)
    assert path.read_bytes() == original
    assert not list(tmp_path.rglob("*.sqlite"))


def test_archived_sessions_and_symlink_escape(tmp_path):
    sid, _ = transcript(tmp_path, archived=True)
    outside = tmp_path / "outside.jsonl"
    outside.write_text(json.dumps({"type": "session_meta", "payload": {"id": "outside"}}) + "\n")
    root = tmp_path / ".codex" / "sessions"
    root.mkdir()
    (root / "escape.jsonl").symlink_to(outside)
    history = CodexHistory(tmp_path)
    results = history.run("search", {})["results"]
    assert [r["id"] for r in results] == [sid]
    for id in (str(outside), "../../outside.jsonl", "outside"):
        with pytest.raises(ValueError):
            history.run("read", {"id": id})


def test_page_budget_and_explicit_clipping():
    page = pack_page({"id": "large"}, [{"role": "assistant", "content": "x" * 10000}] * 50, 0, 40)
    assert len(json.dumps(page)) < 10000
    assert page["content_truncated"] and page["has_more"]
    assert page["total"] == 50 and page["next_offset"] == len(page["events"])
    unicode_page = pack_page({"id": "large"}, [{"role": "user", "content": "字" * 10000}], 0, 1)
    assert unicode_page["next_offset"] == 1 and unicode_page["content_truncated"]
    assert len(json.dumps(unicode_page)) < 10000


def test_resumed_history_search_and_read_include_the_earlier_prefix(tmp_path):
    from plugins.tests.test_codex_transcript import FORK, boundary, page

    original = page(tmp_path / ".codex", "original", ["Earlier website feedback"])
    page(
        tmp_path / ".codex",
        "resumed",
        ["New work"],
        start=2,
        base=boundary(original, 2),
        thread=FORK,
    )
    history = CodexHistory(tmp_path)
    found = history.run("search", {"query": "Earlier"})["results"]
    assert any(r["id"] == FORK and not r["partial_history"] for r in found)
    result = history.run("read", {"id": FORK})
    assert [e["content"] for e in result["events"]] == ["Earlier website feedback", "New work"]
    assert not result["source"]["partial_history"]


def test_search_continuation_does_not_skip_the_rest_of_a_long_session(tmp_path, monkeypatch):
    from stashai import local_history

    sid, _ = transcript(
        tmp_path,
        text="Nothing here",
        extra=[
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "the searchtarget appears later",
                },
            }
        ],
    )
    history = CodexHistory(tmp_path)
    history._discover()
    ticks = iter([0, 0, 9, 10])
    monkeypatch.setattr(local_history.time, "monotonic", lambda: next(ticks))
    first = history.run("search", {"query": "searchtarget"})
    assert not first["results"] and first["has_more"]
    assert first["next_offset"] == 0 and first["next_event_offset"] == 1
    monkeypatch.setattr(local_history.time, "monotonic", lambda: 0)
    second = history.run(
        "search",
        {
            "query": "searchtarget",
            "offset": first["next_offset"],
            "event_offset": first["next_event_offset"],
        },
    )
    assert second["results"][0]["id"] == sid
    assert second["results"][0]["match_offset"] == 3


@pytest.mark.parametrize(
    "operation,args",
    [
        ("shell", {"command": "cat /etc/passwd"}),
        ("search", {"path": "/etc"}),
        ("search", {"query": "x" * 201}),
        ("read", {"id": "session", "offset": -1}),
        ("read", {"id": "session", "limit": 1000}),
        ("read", {"id": "session", "limit": True}),
    ],
)
def test_requests_cannot_choose_paths_commands_or_unbounded_reads(operation, args):
    with pytest.raises(ValueError):
        validate_request(operation, args)
