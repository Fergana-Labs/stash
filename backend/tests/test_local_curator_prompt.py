"""The local-curator prompt endpoint: Stash Desktop fetches this before every
headless run, so it must be authenticated (it's per-user surface area, and
later per-org) and must always serve a usable prompt — an empty prompt would
silently no-op every install's curation."""

from httpx import AsyncClient

from .test_permissions import _auth, _register


async def test_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/me/local-curator-prompt")
    assert resp.status_code == 401


async def test_serves_the_curation_prompt(client: AsyncClient):
    api_key, _ = await _register(client)
    resp = await client.get("/api/v1/me/local-curator-prompt", headers=_auth(api_key))
    assert resp.status_code == 200
    prompt = resp.json()["prompt"]
    # The prompt drives an unattended agent: it must ground the run in the
    # stash CLI and end with the upload step, or runs produce nothing.
    assert "stash" in prompt
    assert "stash upload" in prompt
