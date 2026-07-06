"""All-repos mode for the GitHub integration.

PUT /integrations/github/repo-access with {"all_repos": true} must register a
github_repo source for every repo the account can see, the hourly reconcile
must pick up repos granted later, and switching back to select mode must stop
auto-registration without deleting the sources already created.

GitHub itself is faked at the account_sync seam (token + repo listing);
everything downstream runs against the real services and DB.
"""

import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.integrations.github import account_sync
from backend.tasks import sources as sources_tasks


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": f"ghall_{uuid.uuid4().hex[:8]}", "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _connect_github(pool, user_id: UUID) -> None:
    await pool.execute(
        "INSERT INTO user_integrations "
        "(user_id, provider, access_token_encrypted, account_key) VALUES ($1, 'github', $2, 'default')",
        user_id,
        b"\x00",
    )


@pytest.fixture
def fake_github(monkeypatch):
    """Fake the GitHub seam: a mutable repo list and a token that always works."""
    repos = [{"full_name": "acme/api"}, {"full_name": "acme/web"}]

    async def fake_token(user_id, provider):
        return "tok"

    async def fake_list(access_token):
        return list(repos)

    monkeypatch.setattr(account_sync, "get_valid_token", fake_token)
    monkeypatch.setattr(account_sync, "list_visible_repos", fake_list)
    return repos


async def _source_refs(pool, user_id: UUID) -> set[str]:
    rows = await pool.fetch(
        "SELECT external_ref FROM user_sources "
        "WHERE owner_user_id = $1 AND source_type = 'github_repo'",
        user_id,
    )
    return {row["external_ref"] for row in rows}


@pytest.mark.asyncio
async def test_enable_registers_every_visible_repo(client, pool, fake_github):
    api_key, user_id = await _register(client)
    await _connect_github(pool, user_id)

    resp = await client.put(
        "/api/v1/integrations/github/repo-access",
        json={"all_repos": True},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json() == {"all_repos": True, "total": 2, "created": 2}
    assert await _source_refs(pool, user_id) == {"acme/api", "acme/web"}

    status = await client.get("/api/v1/integrations/github/repo-access", headers=_auth(api_key))
    assert status.json()["all_repos"] is True


@pytest.mark.asyncio
async def test_enable_is_idempotent(client, pool, fake_github):
    api_key, user_id = await _register(client)
    await _connect_github(pool, user_id)

    first = await client.put(
        "/api/v1/integrations/github/repo-access",
        json={"all_repos": True},
        headers=_auth(api_key),
    )
    assert first.json()["created"] == 2
    second = await client.put(
        "/api/v1/integrations/github/repo-access",
        json={"all_repos": True},
        headers=_auth(api_key),
    )
    assert second.json() == {"all_repos": True, "total": 2, "created": 0}
    assert await _source_refs(pool, user_id) == {"acme/api", "acme/web"}


@pytest.mark.asyncio
async def test_reconcile_picks_up_later_granted_repos(client, pool, fake_github):
    api_key, user_id = await _register(client)
    await _connect_github(pool, user_id)
    await client.put(
        "/api/v1/integrations/github/repo-access",
        json={"all_repos": True},
        headers=_auth(api_key),
    )

    fake_github.append({"full_name": "acme/new-service"})
    reconciled = await sources_tasks._reconcile_github_sync_all()

    assert reconciled == 1
    assert await _source_refs(pool, user_id) == {"acme/api", "acme/web", "acme/new-service"}


@pytest.mark.asyncio
async def test_disable_stops_auto_registration_but_keeps_sources(client, pool, fake_github):
    api_key, user_id = await _register(client)
    await _connect_github(pool, user_id)
    await client.put(
        "/api/v1/integrations/github/repo-access",
        json={"all_repos": True},
        headers=_auth(api_key),
    )

    off = await client.put(
        "/api/v1/integrations/github/repo-access",
        json={"all_repos": False},
        headers=_auth(api_key),
    )
    assert off.json()["all_repos"] is False

    fake_github.append({"full_name": "acme/new-service"})
    reconciled = await sources_tasks._reconcile_github_sync_all()

    assert reconciled == 0
    assert await _source_refs(pool, user_id) == {"acme/api", "acme/web"}


@pytest.mark.asyncio
async def test_put_requires_a_github_connection(client, fake_github):
    api_key, _ = await _register(client)
    resp = await client.put(
        "/api/v1/integrations/github/repo-access",
        json={"all_repos": True},
        headers=_auth(api_key),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_visible_repos_walks_every_page(monkeypatch):
    pages_requested = []

    async def fake_page(http_client, page):
        pages_requested.append(page)
        if page == 1:
            return [{"full_name": f"acme/repo-{i}"} for i in range(account_sync.REPOS_PAGE_SIZE)]
        return [{"full_name": "acme/tail"}]

    monkeypatch.setattr(account_sync, "_fetch_repos_page", fake_page)
    repos = await account_sync.list_visible_repos("tok")

    assert pages_requested == [1, 2]
    assert len(repos) == account_sync.REPOS_PAGE_SIZE + 1
