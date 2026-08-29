from __future__ import annotations

import gzip

import pytest

from stashai.plugin.stash_client import StashClient
from stashai.redaction import REDACTED, redact_data, redact_text


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
        "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "github_pat_abcdefghijklmnopqrstuvwxyz123456",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "xoxb-" + "1234567890-abcdefghijklmnop",
        "AKIAABCDEFGHIJKLMNOP",
        "AIzaabcdefghijklmnopqrstuvwxyz12345678",
    ],
)
def test_common_provider_tokens_are_redacted(secret: str) -> None:
    assert redact_text(f"The token is {secret}") == f"The token is {REDACTED}"


def test_structured_and_multiline_credentials_are_redacted() -> None:
    private_key = "-----BEGIN PRIVATE KEY-----\nsecret material\n-----END PRIVATE KEY-----"
    data = {
        "command": "OPENAI_API_KEY=ordinary-secret-value python app.py",
        "headers": ["Authorization: Bearer ordinary.bearer.token.value"],
        "database": "postgres://alice:database-password@example.com/app",
        "key": private_key,
    }

    redacted = redact_data(data)

    assert "ordinary-secret-value" not in str(redacted)
    assert "ordinary.bearer.token.value" not in str(redacted)
    assert "database-password" not in str(redacted)
    assert "secret material" not in str(redacted)


def test_redaction_is_idempotent_for_retried_uploads() -> None:
    once = redact_text("OPENAI_API_KEY=ordinary-secret-value")
    assert redact_text(once) == once


def test_live_events_are_redacted_before_the_http_boundary(monkeypatch) -> None:
    client = StashClient("https://example.test", api_key="stash-key")
    sent = {}
    monkeypatch.setattr(client, "_post", lambda path, json: sent.update(json) or {"ok": True})
    monkeypatch.setattr(client, "_drain_queue", lambda: True)

    client.push_event(
        agent_name="codex",
        event_type="user_message",
        content="Use sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        session_id="session-1",
        metadata={"command": "API_KEY=ordinary-secret-value"},
    )

    assert sent["content"] == f"Use {REDACTED}"
    assert sent["metadata"]["command"] == f"API_KEY={REDACTED}"


def test_transcripts_are_redacted_before_compression_and_upload(monkeypatch, tmp_path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text('{"message":"API_KEY=ordinary-secret-value"}\n')
    client = StashClient("https://example.test", api_key="stash-key")
    uploaded = {}

    class Response:
        is_success = True

        @staticmethod
        def json():
            return {"imported": 1}

    def request(method, path, **kwargs):
        uploaded.update(kwargs)
        return Response()

    monkeypatch.setattr(client._http, "request", request)

    client.upload_transcript("session-1", transcript, "codex")

    compressed = uploaded["files"]["file"][1]
    assert gzip.decompress(compressed).decode() == f'{{"message":"API_KEY={REDACTED}"}}\n'
