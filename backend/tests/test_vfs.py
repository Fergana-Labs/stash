"""The VFS shell, served over HTTP.

The point of the endpoint is that an agent with no shell — a Vercel function, an
MCP client — gets the same filesystem the `stash vfs` CLI command gives an agent
that does. These tests pin the two properties that make that safe to hand a
partner: reads run as the calling credential, and the caller's cloud computer is
not part of the tree.
"""

import asyncio
import threading
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import source_service, vfs_service

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


async def test_resolve_maps_a_vfs_path_to_its_app_route(client: AsyncClient):
    """Chat citations deep-link through /resolve: a VFS path comes back with
    the app route of the object behind it."""
    api_key, _ = await _register(client)
    page_id = await _make_page(client, api_key, "Runbook", "# Deploy")

    resp = await client.get(
        "/api/v1/me/vfs/resolve",
        params={"path": "/files/Runbook.md"},
        headers=_auth(api_key),
    )

    assert resp.status_code == 200
    assert resp.json() == {"path": "/files/Runbook.md", "app_url": f"/p/{page_id}"}


async def test_resolve_unknown_path_is_404(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await client.get(
        "/api/v1/me/vfs/resolve",
        params={"path": "/files/nope.md"},
        headers=_auth(api_key),
    )

    assert resp.status_code == 404


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


async def test_scan_budget_makes_grep_partial_and_loud(client: AsyncClient, monkeypatch):
    """An org-wide grep that outruns the read budget must return whatever it
    found so far with an explicit truncation warning — not abort with 413
    (Heavi's agent lost entire per-VIN sweeps to that), and never a clean
    no-match exit that reads as 'searched everything, found nothing'."""
    monkeypatch.setattr("backend.services.vfs_service.MAX_DOCUMENT_READS", 1)
    api_key, _ = await _register(client)
    await _make_page(client, api_key, "One", "alpha")
    await _make_page(client, api_key, "Two", "beta")

    resp = await _vfs(client, api_key, "grep -ri 'alpha' /files")

    assert resp.status_code == 200
    body = resp.json()
    assert "of 2 files" in body["stderr"]
    assert "partial" in body["stderr"]


async def test_document_read_budget_still_aborts_direct_reads(client: AsyncClient, monkeypatch):
    """Outside a grep sweep there are no partial results to salvage: a `cat`
    over more documents than the budget allows must abort the command."""
    monkeypatch.setattr("backend.services.vfs_service.MAX_DOCUMENT_READS", 1)
    api_key, _ = await _register(client)
    await _make_page(client, api_key, "One", "alpha")
    await _make_page(client, api_key, "Two", "beta")

    resp = await _vfs(client, api_key, "cat '/files/One.md' '/files/Two.md'")

    assert resp.status_code == 413


async def test_concurrency_cap_rejects_an_overlapping_request(client: AsyncClient, monkeypatch):
    """A burst must reject excess work before it builds another VFS model."""
    monkeypatch.setattr("backend.services.vfs_service.MAX_CONCURRENT_SCRIPTS", 1)
    started = threading.Event()
    release = threading.Event()

    def run_script(*_args):
        started.set()
        release.wait()
        return {"stdout": "", "stderr": "", "exit_code": 0, "cwd": "/"}

    monkeypatch.setattr("backend.services.vfs_service._run_script", run_script)
    api_key, _ = await _register(client)
    first = asyncio.create_task(_vfs(client, api_key, "ls /"))

    try:
        assert await asyncio.to_thread(started.wait, 1)
        second = await _vfs(client, api_key, "ls /")

        assert second.status_code == 429
        assert second.headers["retry-after"] == "2"
    finally:
        release.set()

    assert (await first).status_code == 200


async def test_concurrency_slot_is_released_after_failure(client: AsyncClient, monkeypatch):
    """A crashed command must not permanently reduce the process capacity."""
    monkeypatch.setattr("backend.services.vfs_service.MAX_CONCURRENT_SCRIPTS", 1)
    calls = 0

    def run_script(*_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("script crashed")
        return {"stdout": "", "stderr": "", "exit_code": 0, "cwd": "/"}

    monkeypatch.setattr("backend.services.vfs_service._run_script", run_script)
    api_key, _ = await _register(client)

    first = await _vfs(client, api_key, "ls /")

    assert first.status_code == 500
    assert (await _vfs(client, api_key, "ls /")).status_code == 200


async def test_wall_clock_budget_aborts_the_command(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("backend.services.vfs_service.MAX_SCRIPT_SECONDS", 0)
    api_key, _ = await _register(client)

    resp = await _vfs(client, api_key, "ls /")

    assert resp.status_code == 413
    assert "longer than" in resp.json()["detail"]


async def test_wall_clock_budget_cancels_a_slow_nested_request(monkeypatch):
    """A stalled content route must not hold a VFS slot past the deadline."""
    monkeypatch.setattr("backend.services.vfs_service.MAX_SCRIPT_SECONDS", 0.05)

    class SlowHttp:
        async def request(self, *_args, **_kwargs):
            await asyncio.sleep(10)

    client = vfs_service.InProcessVfsClient(SlowHttp(), asyncio.get_running_loop())

    with pytest.raises(vfs_service.VfsBudgetExceeded, match="longer than"):
        await asyncio.to_thread(client._request, "GET", "/slow")


async def test_machine_fs_404s_without_provisioned_computer(client: AsyncClient, monkeypatch):
    """Browsing must never conjure a VM: a user who never ran a cloud agent
    gets a 404 from the machine fs, not a freshly provisioned sprite."""
    from backend.config import settings

    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    api_key, _ = await _register(client)

    resp = await client.get("/api/v1/me/machine/fs", headers=_auth(api_key))

    assert resp.status_code == 404


async def test_overview_reports_machine_provisioned_state(client: AsyncClient, monkeypatch, pool):
    """The CLI VFS decides whether to mount /computer from this flag alone, so
    it must flip exactly when a ready sprite row exists — no machine API call."""
    from backend.config import settings

    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    api_key, owner_id = await _register(client)

    before = await client.get("/api/v1/me/overview", headers=_auth(api_key))
    assert before.json()["machine"] == {"provisioned": False}

    await pool.execute(
        "INSERT INTO user_sprites (user_id, sprite_name, status) VALUES ($1, $2, 'ready')",
        owner_id,
        "sprite-test",
    )
    after = await client.get("/api/v1/me/overview", headers=_auth(api_key))
    assert after.json()["machine"] == {"provisioned": True}
