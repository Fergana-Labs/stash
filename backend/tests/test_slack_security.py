from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.integrations.slack import indexer


class _SlackErrorResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "ok": False,
            "error": "token=secret-token customer transcript",
        }


class _SlackErrorClient:
    async def get(self, url, params):
        return _SlackErrorResponse()


def _source() -> dict:
    return {
        "id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "owner_user_id": str(uuid4()),
        "source_type": "slack",
        "settings": {"allowed_channel_ids": ["C_SECRET"]},
    }


def _capture_info(monkeypatch):
    captured_logs: list[tuple[str, tuple, dict]] = []

    def capture(message, *args, **kwargs):
        captured_logs.append((message, args, kwargs))

    monkeypatch.setattr(indexer.logger, "info", capture)
    return captured_logs


async def _fake_get_valid_token(user_id, provider):
    assert provider == "slack"
    return "slack-token"


async def _noop_purge(source):
    return 0


async def _fake_slack_get_with_sensitive_channel(client, url, params):
    if url == indexer.CONVERSATIONS_LIST_URL:
        return {"channels": [{"id": "C_SECRET", "name": "webflow-acquisition"}]}
    raise RuntimeError("token=secret-token customer transcript")


@pytest.mark.asyncio
async def test_slack_api_errors_do_not_include_provider_response():
    with pytest.raises(RuntimeError) as exc_info:
        await indexer._slack_get(
            _SlackErrorClient(),
            indexer.CONVERSATIONS_HISTORY_URL,
            {"channel": "C_SECRET"},
        )

    message = str(exc_info.value)
    assert message == "Slack API returned ok=false"
    assert "secret-token" not in message
    assert "customer transcript" not in message


@pytest.mark.asyncio
async def test_slack_backfill_skip_logs_only_metadata(monkeypatch):
    captured_logs = _capture_info(monkeypatch)
    source = _source()
    monkeypatch.setattr(indexer, "get_valid_token", _fake_get_valid_token)
    monkeypatch.setattr(indexer, "_slack_get", _fake_slack_get_with_sensitive_channel)
    monkeypatch.setattr(indexer.source_service, "purge_disallowed_copied_documents", _noop_purge)

    await indexer.index_slack(source)

    assert (
        "slack: skipping unreadable channel source=%s exception_type=%s",
        (UUID(source["id"]), "RuntimeError"),
        {},
    ) in captured_logs
    assert "webflow-acquisition" not in str(captured_logs)
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_slack_history_skip_logs_only_metadata(monkeypatch):
    captured_logs = _capture_info(monkeypatch)
    source = _source()
    monkeypatch.setattr(indexer, "get_valid_token", _fake_get_valid_token)
    monkeypatch.setattr(indexer, "_slack_get", _fake_slack_get_with_sensitive_channel)

    result = await indexer.fetch_history(
        source,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        until=None,
    )

    assert result["fetched"] == 0
    assert (
        "slack history: skipping unreadable channel source=%s exception_type=%s",
        (UUID(source["id"]), "RuntimeError"),
        {},
    ) in captured_logs
    assert "webflow-acquisition" not in str(captured_logs)
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
