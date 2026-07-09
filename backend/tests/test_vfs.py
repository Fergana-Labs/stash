"""The VFS shell, served over HTTP.

The point of the endpoint is that an agent with no shell — a Vercel function, an
MCP client — gets the same filesystem the `stash vfs` CLI command gives an agent
that does. These tests pin the two properties that make that safe to hand a
partner: reads run as the calling credential, and the caller's cloud computer is
not part of the tree.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import source_service

from .conftest import unique_name

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("vfs"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _vfs(client: AsyncClient, api_key: str, script: str, cwd: str = "/"):
    return await client.post(
        "/api/v1/me/vfs",
        json={"script": script, "cwd": cwd},
        headers=_auth(api_key),
    )


async def _make_page(client: AsyncClient, api_key: str, name: str, content: str) -> str:
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": name, "content": content},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _make_source_doc(owner_id: UUID, path: str, name: str, content: str) -> None:
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref=f"acme/{unique_name('repo')}",
        display_name="Specs",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        owner_user_id=owner_id,
        path=path,
        name=name,
        content=content,
    )


async def test_ls_root_lists_the_mounts(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "ls /")

    assert resp.status_code == 200
    body = resp.json()
    assert body["exit_code"] == 0
    listed = body["stdout"].split()
    assert {"files", "sessions", "skills", "tables"} <= set(listed)


async def test_computer_is_not_mounted_server_side(client: AsyncClient):
    """A key handed to a partner's production agent must not reach through the
    API into a real machine's disk. /computer exists only in the CLI's mount."""
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "ls /")

    assert "computer" not in resp.json()["stdout"].split()


async def test_cat_reads_a_page_body(client: AsyncClient):
    """Page bodies load through a lazy loader that re-enters the app. If the
    nested request loses the caller's credential, this is where it shows up."""
    api_key, _ = await _register(client)
    await _make_page(client, api_key, "Runbook", "# Deploy\nrun the migration first")

    resp = await _vfs(client, api_key, "cat '/files/Runbook.md'")

    assert resp.status_code == 200
    assert "run the migration first" in resp.json()["stdout"]


async def test_grep_searches_connected_source_documents(client: AsyncClient):
    api_key, owner_id = await _register(client)
    await _make_source_doc(owner_id, "specs/auth.md", "auth.md", "tokens rotate hourly")

    resp = await _vfs(client, api_key, "grep -ri 'rotate hourly' /sources")

    assert resp.status_code == 200
    assert "auth.md" in resp.json()["stdout"]


async def test_reads_are_scoped_to_the_calling_credential(client: AsyncClient):
    """The whole authorization argument for this endpoint: it re-enters the app's
    own routes, so one user's key cannot see another user's page."""
    owner_key, _ = await _register(client)
    await _make_page(client, owner_key, "Secrets", "the launch date is may fourth")

    other_key, _ = await _register(client)
    resp = await _vfs(client, other_key, "grep -ri 'launch date' /files")

    assert resp.status_code == 200
    assert "may fourth" not in resp.json()["stdout"]
    assert "Secrets" not in resp.json()["stdout"]


async def test_grep_with_no_match_exits_nonzero_without_failing_the_request(
    client: AsyncClient,
):
    """A shell result, not a transport error. Callers must be able to tell the
    difference between `grep` finding nothing and the endpoint breaking."""
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "grep -ri 'nothing matches this' /files")

    assert resp.status_code == 200
    assert resp.json()["exit_code"] != 0


async def test_writes_are_rejected(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "echo hi > /files/x.md")

    assert resp.status_code == 200
    assert resp.json()["exit_code"] != 0


async def test_unknown_cwd_is_a_client_error(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "ls", cwd="/nope")

    assert resp.status_code == 400


async def test_document_read_budget_aborts_the_command(client: AsyncClient, monkeypatch):
    """An unscoped `grep -r /` would walk every document in every source. The
    ceiling must abort the command, not degrade into a per-file warning that the
    caller reads as 'no matches'."""
    monkeypatch.setattr("backend.services.vfs_service.MAX_DOCUMENT_READS", 1)
    api_key, _ = await _register(client)
    await _make_page(client, api_key, "One", "alpha")
    await _make_page(client, api_key, "Two", "beta")

    resp = await _vfs(client, api_key, "grep -ri 'alpha' /files")

    assert resp.status_code == 413
