"""upload_transcript must survive transient network errors.

History imports run thousands of sequential uploads; a single dropped
connection used to crash the whole onboarding flow (see SSLV3 bad-record-mac
incident). A blip should be retried, and only a persistent failure should
surface to the caller.
"""

from __future__ import annotations

import httpx
import pytest

from cli import client as client_module
from cli.client import StashClient


class _FakeResponse:
    def json(self):
        return {"imported": 1}


def _make_client(monkeypatch, outcomes):
    """Build a StashClient whose _request pops from `outcomes` per call.

    Each outcome is either an exception to raise or a response to return.
    """
    c = StashClient("https://example.test", api_key="k")
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append(path)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(c, "_request", fake_request)
    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)
    return c, calls


def test_upload_transcript_retries_transient_transport_error(monkeypatch, tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("{}\n")
    c, calls = _make_client(monkeypatch, [httpx.ReadError("blip"), _FakeResponse()])

    result = c.upload_transcript(
        workspace_id="ws",
        session_id="s1",
        transcript_path=transcript,
        agent_name="claude",
    )

    assert result == {"imported": 1}
    assert len(calls) == 2


def test_upload_transcript_raises_after_persistent_transport_error(monkeypatch, tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("{}\n")
    c, calls = _make_client(monkeypatch, [httpx.ReadError("down")] * 3)

    with pytest.raises(httpx.ReadError):
        c.upload_transcript(
            workspace_id="ws",
            session_id="s1",
            transcript_path=transcript,
            agent_name="claude",
        )

    assert len(calls) == 3
