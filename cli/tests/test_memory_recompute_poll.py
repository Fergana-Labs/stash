"""`stash memory --recompute` polls the curator instead of trusting the 202.

The web service enqueues and answers 202 before the worker executes — the two
can disagree (env drift, worker down), so the CLI watches the agent row for
what actually happened: picked up + error = this run failed; picked up clean =
running; never picked up = queued warning.
"""

from __future__ import annotations

from cli import main as cli_main
from cli.main import _poll_recompute_outcome


class _FakeClient:
    def __init__(self, states: list[dict | None]):
        self._states = states
        self.calls = 0

    def get_curator(self) -> dict | None:
        state = self._states[min(self.calls, len(self._states) - 1)]
        self.calls += 1
        return state


BEFORE = {"last_run_at": "t0", "last_run_error": None}


def _no_sleep(monkeypatch):
    monkeypatch.setattr(cli_main.time, "sleep", lambda _s: None)


def test_run_crash_is_reported(monkeypatch):
    _no_sleep(monkeypatch)
    client = _FakeClient(
        [
            {"last_run_at": "t0", "last_run_error": None},  # not picked up yet
            {"last_run_at": "t1", "last_run_error": "No such file: claude"},
        ]
    )
    outcome, error = _poll_recompute_outcome(client, BEFORE)
    assert outcome == "failed"
    assert "claude" in error


def test_clean_pickup_reports_running(monkeypatch):
    _no_sleep(monkeypatch)
    client = _FakeClient([{"last_run_at": "t1", "last_run_error": None}])
    assert _poll_recompute_outcome(client, BEFORE) == ("running", None)


def test_never_picked_up_reports_queued(monkeypatch):
    _no_sleep(monkeypatch)
    client = _FakeClient([{"last_run_at": "t0", "last_run_error": None}])
    outcome, error = _poll_recompute_outcome(client, BEFORE, attempts=3)
    assert outcome == "queued"
    assert error is None
    assert client.calls == 3


def test_stale_error_from_previous_run_is_not_reported(monkeypatch):
    """mark_run clears last_run_error at pickup, so an old failure visible
    before the run starts must not read as a new one."""
    _no_sleep(monkeypatch)
    before = {"last_run_at": "t0", "last_run_error": "old failure"}
    client = _FakeClient([{"last_run_at": "t1", "last_run_error": None}])
    assert _poll_recompute_outcome(client, before) == ("running", None)
