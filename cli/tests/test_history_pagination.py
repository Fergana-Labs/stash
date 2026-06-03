"""Tests for history pagination plumbing in the CLI."""

from cli import main as cli_main
from cli.client import CartridgeClient


class RecordingClient(CartridgeClient):
    def __init__(self) -> None:
        self.calls = []

    def _list(self, path: str, key: str, **params):
        self.calls.append((path, key, params))
        return []


def test_all_events_client_sends_cursor_params() -> None:
    client = RecordingClient()

    client.all_events(
        agent_name="agent",
        event_type="note",
        limit=7,
        before="2026-01-02T00:00:00Z",
        after="2026-01-01T00:00:00Z",
        order="asc",
    )

    assert client.calls == [
        (
            "/api/v1/me/session-events",
            "events",
            {
                "limit": 7,
                "order": "asc",
                "agent_name": "agent",
                "event_type": "note",
                "after": "2026-01-01T00:00:00Z",
                "before": "2026-01-02T00:00:00Z",
            },
        )
    ]


def test_hist_query_all_forwards_cursor_params(monkeypatch) -> None:
    captured = {}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def all_events(self, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(cli_main, "_client", lambda: FakeClient())
    monkeypatch.setattr(cli_main, "output_json", lambda data: None)

    cli_main.hist_query(
        workspace_id=None,
        agent_name="agent",
        event_type="note",
        limit=7,
        before="2026-01-02T00:00:00Z",
        after="2026-01-01T00:00:00Z",
        order="asc",
        all_=True,
        as_json=True,
    )

    assert captured == {
        "agent_name": "agent",
        "event_type": "note",
        "limit": 7,
        "before": "2026-01-02T00:00:00Z",
        "after": "2026-01-01T00:00:00Z",
        "order": "asc",
    }
