from uuid import UUID

import httpx
import pytest

from backend.integrations.posthog import indexer
from backend.integrations.posthog.provider import normalize_host


def test_posthog_host_requires_a_bare_https_origin():
    assert normalize_host(" https://eu.posthog.com/ ") == "https://eu.posthog.com"
    with pytest.raises(ValueError):
        normalize_host("http://posthog.internal")
    with pytest.raises(ValueError):
        normalize_host("https://posthog.example.com/api")
    with pytest.raises(ValueError):
        normalize_host("https://127.0.0.1")


def test_posthog_paths_group_objects_and_keep_duplicate_names_distinct():
    first = indexer._object_path("insights", {"id": 12, "name": "Activation / weekly"})
    second = indexer._object_path("insights", {"id": 13, "name": "Activation / weekly"})
    assert first == "insights/Activation - weekly (12)"
    assert first != second


@pytest.mark.asyncio
async def test_posthog_indexer_indexes_each_product_collection(monkeypatch):
    captured: list[dict] = []
    removed: list[list[str]] = []
    responses = {
        "dashboards": {"id": 1, "name": "Company KPI", "created_at": "2026-07-01T00:00:00Z"},
        "insights": {"id": 2, "name": "Activation", "updated_at": "2026-07-02T00:00:00Z"},
        "feature_flags": {"id": 3, "key": "new-nav", "updated_at": "2026-07-03T00:00:00Z"},
        "experiments": {"id": 4, "name": "Better onboarding", "updated_at": "2026-07-04T00:00:00Z"},
    }

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, path, params=None):
            kind = path.rstrip("/").rsplit("/", 1)[-1]
            return FakeResponse({"results": [responses[kind]]})

    async def fake_client(owner_user_id):
        assert owner_user_id == UUID("00000000-0000-0000-0000-000000000002")
        return FakeClient(), {"project_id": "42"}

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    async def capture_remove(table, source_id, paths):
        assert table == "posthog_index"
        removed.append(paths)

    monkeypatch.setattr(indexer, "_client", fake_client)
    monkeypatch.setattr(indexer.source_service, "upsert_index_row", capture_upsert)
    monkeypatch.setattr(indexer.source_service, "remove_missing_documents", capture_remove)

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
    assert removed == [[row["path"] for row in captured]]


@pytest.mark.asyncio
async def test_posthog_provider_validates_project_before_storing_credentials(monkeypatch):
    from backend.integrations.posthog import provider

    request = httpx.Request("GET", "https://us.posthog.com/api/projects/42/")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": 42, "name": "Acme Product"}

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["headers"] == {"Authorization": "Bearer phx_secret"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            assert url == str(request.url)
            return FakeResponse()

    monkeypatch.setattr(provider.httpx, "AsyncClient", FakeClient)
    token, account = await provider.PostHogIntegration().connect_with_credentials(
        {
            "instance_url": "https://us.posthog.com",
            "project_id": "42",
            "personal_api_key": "phx_secret",
        }
    )
    assert account.display_name == "Acme Product"
    assert provider.decode_credentials(token.access_token)["project_id"] == "42"
