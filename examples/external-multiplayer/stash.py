"""The whole Stash integration for an external agent: two calls.

Write a turn with your own id for the user; read back with the same id.
That is the entire External Multiplayer contract — everything else (per-user
notepads, the anonymized cross-user wiki, isolation) is Stash's job.
"""

from datetime import datetime, timedelta, timezone

import httpx


class Stash:
    def __init__(self, api_key: str, base_url: str):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )

    def read(self, user: str, script: str) -> str:
        """Run a read against this user's view of the stash. They see the
        shared wiki at /memory, their own notepad and files under /files, and
        only their own transcripts under /sessions."""
        resp = self._http.post("/api/v1/me/vfs", json={"script": script, "user_id": user})
        resp.raise_for_status()
        return resp.json()["stdout"]

    def record(
        self,
        user: str,
        user_name: str,
        session: str,
        events: list[tuple],
        max_event_chars: int = 20_000,
    ) -> dict:
        """Append turns to this user's session. First sight of a user id
        creates the user.

        Each event is (event_type, content) or (event_type, content, datetime)
        — pass the datetime when uploading later than the conversation
        happened, e.g. from a queue worker replaying yesterday's turns.
        Otherwise events are stamped at upload time, 1ms apart in list order:
        Stash sorts a transcript by created_at, and a batch stamped on one
        shared instant comes back in id order, putting answers above questions.

        Returns {"recorded", "skipped_empty", "clipped"} — nothing is dropped
        or shortened silently. Empty content is skipped (Stash rejects it);
        oversized content is clipped to max_event_chars (0 disables).
        """
        base = datetime.now(timezone.utc)
        report = {"recorded": 0, "skipped_empty": 0, "clipped": 0}
        wire = []
        for index, (kind, text, *when) in enumerate(events):
            text = text.strip()
            if not text:
                report["skipped_empty"] += 1
                continue
            if max_event_chars and len(text) > max_event_chars:
                report["clipped"] += 1
                text = f"{text[:max_event_chars]}\n[truncated]"
            stamp = when[0] if when else base + timedelta(milliseconds=index)
            wire.append(
                {
                    "agent_name": "parts-desk",
                    "event_type": kind,
                    "content": text,
                    "session_id": session,
                    "user_id": user,
                    "user_name": user_name,
                    "created_at": stamp.isoformat(),
                }
            )
        report["recorded"] = len(wire)
        # Chunked: a replayed conversation can outgrow one request body.
        for start in range(0, len(wire), 200):
            self._http.post(
                "/api/v1/me/sessions/events/batch",
                json={"events": wire[start : start + 200]},
            ).raise_for_status()
        return report
