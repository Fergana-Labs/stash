"""The whole Stash integration for an external agent: two calls.

Write a turn with the customer's org id; read back with the same org id. That
is the entire External Multiplayer contract — everything else (per-org
notepads, the anonymized cross-org wiki, isolation) is Stash's job.
"""

import httpx


class Stash:
    def __init__(self, api_key: str, base_url: str):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )

    def read(self, org: str, script: str) -> str:
        """Run a read against this customer's view of the stash. They see the
        shared wiki at /memory, their own notepad and files under /files, and
        only their own transcripts under /sessions."""
        resp = self._http.post("/api/v1/me/vfs", json={"script": script, "org_id": org})
        resp.raise_for_status()
        return resp.json()["stdout"]

    def record(self, org: str, org_name: str, session: str, events: list[tuple[str, str]]) -> None:
        """Append turns to this customer's session. First sight of an org id
        creates the org."""
        self._http.post(
            "/api/v1/me/sessions/events/batch",
            json={
                "events": [
                    {
                        "agent_name": "travel-planner",
                        "event_type": kind,
                        "content": text,
                        "session_id": session,
                        "org_id": org,
                        "org_name": org_name,
                    }
                    for kind, text in events
                ]
            },
        ).raise_for_status()
