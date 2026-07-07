"""Local event queue inside StashClient.

When push_event raises (network blip, backend cold start, slow GC), the
event body is appended to <data_dir>/event_queue.jsonl. The next successful
push drains a batch of the backlog so the queue clears during normal traffic.
"""

from __future__ import annotations

import json

import pytest

from stashai.plugin.stash_client import QUEUE_FILENAME, StashClient
from stashai.plugin.upload_status import read_upload_status


class _Recorder:
    """Stand-in for httpx.Client.request — programmable success/failure."""

    def __init__(self, fail_first_n: int = 0):
        self.calls: list[dict] = []
        self.fail_first_n = fail_first_n
        # path → HTTP status to answer with (instead of 200).
        self.status_by_path: dict[str, int] = {}

    def request(self, method, path, **kwargs):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "json": kwargs.get("json"),
                "headers": kwargs.get("headers"),
            }
        )
        if len(self.calls) <= self.fail_first_n:
            raise RuntimeError("simulated network failure")
        status = self.status_by_path.get(path, 200)

        class _Resp:
            status_code = status
            is_success = status < 400
            text = "simulated error"

            def json(self_inner):
                return {"ok": True} if status < 400 else {"detail": "simulated error"}

        return _Resp()


def _make_client(tmp_path, fail_first_n=0):
    client = StashClient(base_url="https://example.test", api_key="k", data_dir=tmp_path)
    client._http = _Recorder(fail_first_n=fail_first_n)
    return client


def _queue_lines(tmp_path):
    qp = tmp_path / QUEUE_FILENAME
    if not qp.exists():
        return []
    return [json.loads(line) for line in qp.read_text().splitlines() if line]


def test_failed_push_enqueues(tmp_path):
    client = _make_client(tmp_path, fail_first_n=1)
    with pytest.raises(Exception):
        client.push_event(
            agent_name="a",
            event_type="tool_use",
            content="x",
            session_id="s1",
        )
    queued = _queue_lines(tmp_path)
    assert len(queued) == 1
    assert queued[0]["path"] == "/api/v1/me/sessions/events"
    assert queued[0]["body"]["event_type"] == "tool_use"
    assert queued[0]["body"]["content"] == "x"
    status = read_upload_status(tmp_path)
    assert status["health"] == "failing"
    assert status["queued_events"] == 1
    assert status["consecutive_failures"] == 1
    assert status["last_failure_operation"] == "event"
    assert "simulated network failure" in status["last_error"]


def test_successful_push_drains_backlog(tmp_path):
    """Two failures, then a success — the success should both POST itself
    AND flush the two queued failures."""
    client = _make_client(tmp_path, fail_first_n=2)
    for i in range(2):
        with pytest.raises(Exception):
            client.push_event(agent_name="a", event_type="t", content=f"e{i}", session_id="s1")
    assert len(_queue_lines(tmp_path)) == 2

    # Third push: succeeds + drains backlog.
    client.push_event(agent_name="a", event_type="t", content="e2", session_id="s1")

    # Queue should be empty after drain.
    assert _queue_lines(tmp_path) == []
    # 2 failed attempts + 1 successful + 2 drained backlog = 5 total POSTs recorded.
    assert len(client._http.calls) == 5
    status = read_upload_status(tmp_path)
    assert status["health"] == "ok"
    assert status["queued_events"] == 0
    assert status["consecutive_failures"] == 0
    assert status["last_success_operation"] == "event"


def test_drain_stops_on_first_failure(tmp_path):
    """If backend is still down during drain, leftover entries stay queued."""
    client = _make_client(tmp_path, fail_first_n=1)
    with pytest.raises(Exception):
        client.push_event(agent_name="a", event_type="t", content="e0", session_id="s1")
    assert len(_queue_lines(tmp_path)) == 1

    # Force the recorder to fail the next 5 POSTs (live push + drain attempts).
    client._http.fail_first_n = len(client._http.calls) + 5
    with pytest.raises(Exception):
        client.push_event(agent_name="a", event_type="t", content="e1", session_id="s1")

    # Both events should still be queued (live push failed; drain never ran).
    queued = _queue_lines(tmp_path)
    assert len(queued) == 2
    assert {q["body"]["content"] for q in queued} == {"e0", "e1"}


def test_drain_drops_permanently_rejected_entries(tmp_path):
    """Entries the backend rejects with a non-retryable 4xx (dead route,
    bad body) can never send — they must be dropped so they don't wedge
    the queue in front of good entries forever."""
    client = _make_client(tmp_path)
    qp = tmp_path / QUEUE_FILENAME
    dead = {"path": "/api/v1/workspaces/w1/memory/events", "body": {"content": "old"}, "ts": 1.0}
    good = {"path": "/api/v1/me/sessions/events", "body": {"content": "new"}, "ts": 2.0}
    qp.write_text(json.dumps(dead) + "\n" + json.dumps(good) + "\n")
    client._http.status_by_path["/api/v1/workspaces/w1/memory/events"] = 404

    client.push_event(agent_name="a", event_type="t", content="live", session_id="s1")

    # Dead entry dropped, good entry sent, queue empty.
    assert _queue_lines(tmp_path) == []
    sent_paths = [c["path"] for c in client._http.calls]
    assert sent_paths.count("/api/v1/me/sessions/events") == 2  # live push + drained entry
    status = read_upload_status(tmp_path)
    assert status["queued_events"] == 0


def test_drain_keeps_entries_on_auth_failure(tmp_path):
    """401 heals with a re-signin, so entries stay queued instead of
    being dropped."""
    client = _make_client(tmp_path)
    qp = tmp_path / QUEUE_FILENAME
    entry = {"path": "/api/v1/me/sessions/events", "body": {"content": "e0"}, "ts": 1.0}
    qp.write_text(json.dumps(entry) + "\n")
    client._http.status_by_path["/api/v1/me/sessions/events"] = 401

    with pytest.raises(Exception):
        client.push_event(agent_name="a", event_type="t", content="live", session_id="s1")

    # Live push failed (401) and got enqueued; the original entry survives.
    queued = _queue_lines(tmp_path)
    assert {q["body"]["content"] for q in queued} == {"e0", "live"}


def test_live_push_success_recorded_despite_stuck_backlog(tmp_path):
    """A landed live event is a success even when the backlog can't drain
    (health still reports failing while anything is queued)."""
    client = _make_client(tmp_path)
    qp = tmp_path / QUEUE_FILENAME
    stuck = {"path": "/api/v1/me/sessions/stuck", "body": {"content": "e0"}, "ts": 1.0}
    qp.write_text(json.dumps(stuck) + "\n")
    client._http.status_by_path["/api/v1/me/sessions/stuck"] = 500

    client.push_event(agent_name="a", event_type="t", content="live", session_id="s1")

    status = read_upload_status(tmp_path)
    assert status["last_success_operation"] == "event"
    assert status["queued_events"] == 1
    assert status["health"] == "failing"


def test_drain_drops_corrupt_lines(tmp_path):
    """A line that isn't valid queue JSON can never send — drop it."""
    client = _make_client(tmp_path)
    qp = tmp_path / QUEUE_FILENAME
    good = {"path": "/api/v1/me/sessions/events", "body": {"content": "e0"}, "ts": 1.0}
    qp.write_text("not-json\n" + json.dumps(good) + "\n")

    client.push_event(agent_name="a", event_type="t", content="live", session_id="s1")

    assert _queue_lines(tmp_path) == []


def test_no_data_dir_no_queue(tmp_path):
    """When data_dir is unset, push failure just raises — no queue file written."""
    client = StashClient(base_url="https://example.test", api_key="k")
    client._http = _Recorder(fail_first_n=1)
    with pytest.raises(Exception):
        client.push_event(agent_name="a", event_type="t", content="x", session_id="s1")
    assert not (tmp_path / QUEUE_FILENAME).exists()
