"""Provider edge cases must not turn normal repositories into perpetual incidents."""

from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest

from backend.integrations.github import indexer
from backend.services import source_service
from backend.tasks import sources

from .test_sources import _register

HTTP_CLIENT = httpx.AsyncClient


def mock_github(monkeypatch, handler):
    monkeypatch.setattr(
        indexer.httpx,
        "AsyncClient",
        lambda **kwargs: HTTP_CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
async def test_renamed_repository_follows_redirect_for_head_and_tree(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.startswith("/repos/old/name/"):
            return httpx.Response(
                301,
                headers={
                    "location": str(request.url).replace("/repos/old/name/", "/repositories/42/")
                },
            )
        assert request.headers["Authorization"] == "Bearer token"
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[{"sha": "abc"}])
        return httpx.Response(200, json={"truncated": False, "tree": []})

    mock_github(monkeypatch, handler)
    headers = {"Authorization": "Bearer token"}
    assert await indexer._github_head_sha("https://github.com/old/name", headers) == "abc"
    assert await indexer._github_snapshot_tree("https://github.com/old/name", headers, "abc") == {
        "truncated": False,
        "tree": [],
    }
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_empty_repository_records_success_and_preserves_archive(client, pool, monkeypatch):
    _, owner = await _register(client)
    source = await source_service.create_source(
        owner_user_id=owner,
        source_type="github_repo",
        external_ref="test/empty",
        display_name="Empty",
    )
    sid = UUID(source["id"])
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=sid,
        owner_user_id=owner,
        path="README.md",
        name="README.md",
        content="existing archive",
    )
    mock_github(
        monkeypatch, lambda _: httpx.Response(409, json={"message": "Git Repository is empty."})
    )
    monkeypatch.setattr(indexer, "get_valid_token", AsyncMock(return_value="token"))
    crawl = AsyncMock()
    monkeypatch.setattr(indexer, "_crawl_archive", crawl)
    assert await sources._sync_source(sid) == {"status": "done"}
    assert await pool.fetchval(
        "SELECT last_synced_at IS NOT NULL FROM user_sources WHERE id=$1", sid
    )
    assert (await source_service.read_document(source, "README.md"))[
        "content"
    ] == "existing archive"
    crawl.assert_not_awaited()
    # A first commit on a later tick must become visible to change detection.
    mock_github(monkeypatch, lambda _: httpx.Response(200, json=[{"sha": "first-commit"}]))
    assert await indexer._github_head_sha("https://github.com/test/empty", {}) == "first-commit"


@pytest.mark.asyncio
async def test_other_conflicts_still_fail(monkeypatch):
    mock_github(monkeypatch, lambda _: httpx.Response(409, json={"message": "Unexpected conflict"}))
    with pytest.raises(httpx.HTTPStatusError):
        await indexer._github_head_sha("https://github.com/test/conflict", {})


@pytest.mark.asyncio
async def test_unavailable_repository_is_actionable(monkeypatch):
    mock_github(monkeypatch, lambda _: httpx.Response(404, json={"message": "private details"}))
    with pytest.raises(source_service.SourceSetupRequired, match="Check its URL") as exc:
        await indexer._github_head_sha("https://github.com/test/gone", {})
    assert "private details" not in str(exc.value)
