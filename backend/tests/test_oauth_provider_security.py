import pytest

from backend.integrations.asana import provider as asana_provider
from backend.integrations.jira import provider as jira_provider


class _FakeResponse:
    status_code = 400
    text = "invalid_grant token=secret-token customer transcript"


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, *args, **kwargs):
        return _FakeResponse()


@pytest.mark.asyncio
async def test_asana_token_errors_do_not_include_provider_response(monkeypatch):
    monkeypatch.setattr(asana_provider.httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(RuntimeError) as exc_info:
        await asana_provider.AsanaIntegration()._token_request({"grant_type": "refresh_token"})

    message = str(exc_info.value)
    assert message == "Asana token endpoint returned status_code=400"
    assert "secret-token" not in message
    assert "customer transcript" not in message
    assert "invalid_grant" not in message


@pytest.mark.asyncio
async def test_jira_token_errors_do_not_include_provider_response(monkeypatch):
    monkeypatch.setattr(jira_provider.httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(RuntimeError) as exc_info:
        await jira_provider.JiraIntegration()._token_request({"grant_type": "refresh_token"})

    message = str(exc_info.value)
    assert message == "Atlassian token endpoint returned status_code=400"
    assert "secret-token" not in message
    assert "customer transcript" not in message
    assert "invalid_grant" not in message
