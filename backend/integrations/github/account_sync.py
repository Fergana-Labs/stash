"""GitHub all-repos mode.

When `user_integrations.sync_all` is set on a github connection, every repo
the account can see (own, collaborations, org repos) gets a github_repo
source. The hourly reconcile task re-runs `sync_all_repos` for flagged
accounts so repos the user gains access to later join automatically.
`create_source` is idempotent, so re-running is always safe.
"""

from __future__ import annotations

from uuid import UUID

import httpx

from ...database import get_pool
from ...services import source_service
from ..storage import get_valid_token

USER_REPOS_URL = "https://api.github.com/user/repos"
REPOS_PAGE_SIZE = 100


async def _fetch_repos_page(client: httpx.AsyncClient, page: int) -> list[dict]:
    resp = await client.get(
        USER_REPOS_URL,
        params={
            "per_page": REPOS_PAGE_SIZE,
            "page": page,
            "sort": "updated",
            "affiliation": "owner,collaborator,organization_member",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def list_visible_repos(access_token: str) -> list[dict]:
    """Every repo the token can see, across all pages."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }
    repos: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        page = 1
        while True:
            batch = await _fetch_repos_page(client, page)
            repos.extend(batch)
            if len(batch) < REPOS_PAGE_SIZE:
                return repos
            page += 1


async def sync_all_repos(user_id: UUID) -> dict:
    """Register a github_repo source for every visible repo the user doesn't
    have yet. Each new source's first sync runs immediately via the scheduler."""
    token = await get_valid_token(user_id, "github")
    repos = await list_visible_repos(token)
    rows = await get_pool().fetch(
        "SELECT external_ref FROM user_sources "
        "WHERE owner_user_id = $1 AND source_type = 'github_repo'",
        user_id,
    )
    existing = {row["external_ref"] for row in rows}
    created = 0
    for repo in repos:
        ref = repo["full_name"]
        if ref in existing:
            continue
        await source_service.create_source(
            owner_user_id=user_id,
            source_type="github_repo",
            external_ref=ref,
            display_name=ref,
        )
        created += 1
    return {"total": len(repos), "created": created}
