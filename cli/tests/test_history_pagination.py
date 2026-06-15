"""Tests for history pagination plumbing in the CLI."""

from cli.client import StashClient


class RecordingClient(StashClient):
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
