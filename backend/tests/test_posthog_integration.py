from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest

from backend.integrations.posthog import indexer, oauth

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _async(value):
    async def result(*args, **kwargs):
        return value

    return result


def test_posthog_paths_group_objects_and_keep_duplicate_names_distinct():
    first = indexer._object_path("insights", {"id": 12, "name": "Activation / weekly"})
    second = indexer._object_path("insights", {"id": 13, "name": "Activation / weekly"})
    assert first == "insights/Activation - weekly (12)"
    assert first != second


@pytest.mark.asyncio
async def test_connect_builds_read_only_pkce_authorize_url(monkeypatch):
    monkeypatch.setattr(oauth.settings, "INTEGRATIONS_ENCRYPTION_KEY", TEST_FERNET_KEY)
    monkeypatch.setattr(oauth.settings, "PUBLIC_URL", "https://app.example.com")
    monkeypatch.setattr(
        oauth,
        "_discover",
        _async(
            {
                "authorization_endpoint": "https://oauth.posthog.com/oauth/authorize/",
                "registration_endpoint": "https://oauth.posthog.com/oauth/register/",
            }
        ),
    )
    monkeypatch.setattr(oauth, "_register_client", _async({"client_id": "client_abc"}))

    url = await oauth.start_authorization(UUID(int=1), "/onboarding")
    params = {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}

    assert params["resource"] == "https://mcp.posthog.com"
    assert params["code_challenge_method"] == "S256"
    assert "dashboard:read" in params["scope"]
    assert "dashboard:write" not in params["scope"]
    assert oauth._decode_state(params["state"])["r"] == "/onboarding"


@pytest.mark.asyncio
async def test_posthog_indexer_uses_each_mcp_collection(monkeypatch):
    captured: list[dict] = []
    responses = {
        "dashboards-get-all": {"results": [{"id": 1, "name": "Company KPI"}]},
        "insights-list": {"results": [{"id": 2, "name": "Activation"}]},
        "feature-flag-get-all": {"results": [{"id": 3, "key": "new-nav"}]},
        "experiment-list": {"results": [{"id": 4, "name": "Onboarding"}]},
    }

    @asynccontextmanager
    async def fake_session(token):
        assert token == "access_token"
        yield object()

    async def fake_call_tool(session, name, arguments):
        assert arguments == {"limit": 100, "offset": 0}
        return responses[name]

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(indexer, "get_valid_token", _async("access_token"))
    monkeypatch.setattr(indexer, "posthog_session", fake_session)
    monkeypatch.setattr(indexer, "call_tool", fake_call_tool)
    monkeypatch.setattr(indexer.source_service, "upsert_index_row", capture_upsert)
    monkeypatch.setattr(indexer.source_service, "remove_missing_documents", _async(None))

    await indexer.index_posthog(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "owner_user_id": "00000000-0000-0000-0000-000000000002",
        }
    )

    assert [row["external_ref"] for row in captured] == [
        "dashboards:1",
        "insights:2",
        "feature_flags:3",
        "experiments:4",
    ]
    assert captured[2]["path"] == "feature_flags/new-nav (3)"
