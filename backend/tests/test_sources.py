"""Phase 1 sources foundation: registry, index store, and source-aware tools.

Covers the user-scoping invariant (a connected source is visible only to its
owner), idempotent re-sync of the per-integration tables, lazy reads for the
index-only source (drive), and the agent tools that span native (files,
sessions) + connected sources.
"""

import hashlib
import hmac
import io
import json
import time
import zipfile
from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import agent_runtime, source_service

from .conftest import unique_name


async def _register(client: AsyncClient, prefix: str = "src") -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(prefix), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _create_workspace(client: AsyncClient, api_key: str) -> UUID:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": unique_name("src_ws")},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


def _tool_json(result: dict):
    return json.loads(result["content"][0]["text"])


def _external_ref_for_source_type(source_type: str) -> str:
    refs = {
        "github_repo": "acme/widgets",
        "google_drive": "drive-root",
        "notion": "notion-root",
        "slack": "T123",
        "granola": "granola",
        "jira_project": "cloud-1:PROJ_1",
        "asana_project": "asana-project-1",
        "gong_calls": "gong-source",
        "snowflake": "account/database/schema",
    }
    return refs[source_type]


def _settings_for_source_type(source_type: str) -> dict:
    if source_type == "slack":
        return {"allowed_channel_ids": ["C123"]}
    if source_type == "gong_calls":
        return {"allowed_workspace_ids": ["GONG_WS"]}
    return {}


async def _insert_representative_source_document(
    *,
    workspace_id: UUID,
    source: dict,
) -> None:
    table = source_service.SOURCE_TABLE.get(source["source_type"])
    if table is None:
        return

    source_id = UUID(source["id"])
    if table not in source_service.CONTENT_TABLES:
        await source_service.upsert_index_row(
            table=table,
            source_id=source_id,
            workspace_id=workspace_id,
            path="record-1",
            name="Record 1",
            external_ref="provider-record-1",
        )
        return

    extra = {}
    if table == "slack_messages":
        extra = {"channel_id": "C123", "channel_name": "eng", "ts": "1720000000.000100"}
    elif table == "gong_documents":
        extra = {"gong_workspace_id": "GONG_WS"}

    await source_service.upsert_content_document(
        table=table,
        source_id=source_id,
        workspace_id=workspace_id,
        path="record-1",
        name="Record 1",
        content="confidential customer content",
        external_ref="provider-record-1",
        extra=extra,
    )


# --- registry endpoints -----------------------------------------------------


@pytest.mark.asyncio
async def test_add_list_remove_source(client: AsyncClient):
    api_key, _ = await _register(client)
    ws = await _create_workspace(client, api_key)

    add = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "source_type": "github_repo",
            "external_ref": "acme/widgets",
            "display_name": "acme/widgets",
        },
        headers=_auth(api_key),
    )
    assert add.status_code == 200
    source_id = add.json()["id"]

    listing = await client.get(f"/api/v1/workspaces/{ws}/sources", headers=_auth(api_key))
    assert listing.status_code == 200
    sources = listing.json()["sources"]
    handles = {s["source"] for s in sources}
    # Native sources are always present; the connected source shows by id.
    assert source_service.NATIVE_FILES in handles
    assert source_service.NATIVE_SESSIONS in handles
    assert source_id in handles

    removed = await client.delete(
        f"/api/v1/workspaces/{ws}/sources/{source_id}", headers=_auth(api_key)
    )
    assert removed.status_code == 200
    after = await client.get(f"/api/v1/workspaces/{ws}/sources", headers=_auth(api_key))
    assert source_id not in {s["source"] for s in after.json()["sources"]}


@pytest.mark.asyncio
async def test_viewer_cannot_mutate_sources(client: AsyncClient, pool, monkeypatch):
    owner_key, _owner_id = await _register(client, "src_owner")
    viewer_key, viewer_id = await _register(client, "src_viewer")
    ws = await _create_workspace(client, owner_key)
    viewer_headers = _auth(viewer_key)

    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'viewer')",
        ws,
        viewer_id,
    )

    add = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "source_type": "github_repo",
            "external_ref": "acme/viewer",
            "display_name": "Viewer source",
        },
        headers=viewer_headers,
    )
    assert add.status_code == 403
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM workspace_sources WHERE workspace_id = $1 AND owner_user_id = $2",
            ws,
            viewer_id,
        )
        == 0
    )

    source = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=viewer_id,
        source_type="slack",
        external_ref="T_VIEWER",
        display_name="Viewer Slack",
        settings={"allowed_channel_ids": ["C_VIEWER"]},
    )
    source_id = source["id"]

    sent_tasks: list[dict] = []

    def fake_send_task(*args, **kwargs):
        sent_tasks.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("backend.routers.sources.celery.send_task", fake_send_task)

    history = await client.post(
        f"/api/v1/workspaces/{ws}/sources/{source_id}/history",
        json={"since": "2026-01-01"},
        headers=viewer_headers,
    )
    assert history.status_code == 403

    sync = await client.post(
        f"/api/v1/workspaces/{ws}/sources/{source_id}/sync",
        headers=viewer_headers,
    )
    assert sync.status_code == 403
    assert sent_tasks == []
    assert await pool.fetchval("SELECT COUNT(*) FROM task_records WHERE workspace_id = $1", ws) == 0

    deleted = await client.delete(
        f"/api/v1/workspaces/{ws}/sources/{source_id}",
        headers=viewer_headers,
    )
    assert deleted.status_code == 403
    assert await source_service.get_owned_source(UUID(source_id), viewer_id) is not None


@pytest.mark.asyncio
async def test_disconnect_provider_removes_sources_and_copied_documents(
    client: AsyncClient,
    monkeypatch,
    _db_pool,
):
    from backend.integrations import router as integrations_router

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    slack = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T123",
        display_name="Acme Slack",
        settings={"allowed_channel_ids": ["C123"]},
    )
    github = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/widgets",
        display_name="acme/widgets",
    )
    slack_id = UUID(slack["id"])
    github_id = UUID(github["id"])
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=slack_id,
        workspace_id=ws,
        path="C123/1720000000.000100",
        name="launch-discussion",
        content="confidential launch plan",
    )

    async def fake_revoke_stored(user_id, provider):
        assert user_id == owner_id
        assert provider == "slack"

    monkeypatch.setattr(integrations_router.storage, "revoke_stored", fake_revoke_stored)

    resp = await client.post("/api/v1/integrations/slack/disconnect", headers=_auth(api_key))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "removed_sources": 1}

    assert await source_service.get_owned_source(slack_id, owner_id) is None
    assert await source_service.get_owned_source(github_id, owner_id) is not None
    copied_rows = await _db_pool.fetchval(
        "SELECT count(*) FROM slack_messages WHERE source_id = $1",
        slack_id,
    )
    assert copied_rows == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "source_type"),
    [
        (provider, source_type)
        for provider, source_types in source_service.PROVIDER_SOURCE_TYPES.items()
        for source_type in source_types
    ],
)
async def test_provider_cleanup_removes_source_and_retained_rows(
    client: AsyncClient,
    _db_pool,
    provider: str,
    source_type: str,
):
    api_key, owner_id = await _register(client, "src_cleanup")
    ws = await _create_workspace(client, api_key)
    source = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type=source_type,
        external_ref=_external_ref_for_source_type(source_type),
        display_name=f"{source_type} source",
        settings=_settings_for_source_type(source_type),
    )
    source_id = UUID(source["id"])
    await _insert_representative_source_document(workspace_id=ws, source=source)

    removed_sources = await source_service.delete_sources_for_provider(owner_id, provider)

    assert removed_sources == 1
    assert await source_service.get_owned_source(source_id, owner_id) is None
    table = source_service.SOURCE_TABLE.get(source_type)
    if table is not None:
        assert (
            await _db_pool.fetchval(f"SELECT COUNT(*) FROM {table} WHERE source_id = $1", source_id)
            == 0
        )


@pytest.mark.asyncio
async def test_workspace_leave_removes_member_sources_and_copied_documents(
    client: AsyncClient,
    pool,
):
    owner_key, _owner_id = await _register(client, "src_leave_owner")
    member_key, member_id = await _register(client, "src_leave_member")
    ws = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Source offboarding"},
            headers=_auth(owner_key),
        )
    ).json()
    joined = await client.post(
        f"/api/v1/workspaces/join/{ws['invite_code']}",
        headers=_auth(member_key),
    )
    assert joined.status_code == 200

    source = await source_service.create_source(
        workspace_id=UUID(ws["id"]),
        owner_user_id=member_id,
        source_type="slack",
        external_ref="TWEBFLOW",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["CWEBFLOW"]},
    )
    source_id = UUID(source["id"])
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        workspace_id=UUID(ws["id"]),
        path="CWEBFLOW/1720000000.000100",
        name="confidential-launch",
        content="Webflow confidential launch plan",
    )

    left = await client.post(
        f"/api/v1/workspaces/{ws['id']}/leave",
        headers=_auth(member_key),
    )

    assert left.status_code == 204
    assert await source_service.get_owned_source(source_id, member_id) is None
    assert (
        await pool.fetchval("SELECT COUNT(*) FROM slack_messages WHERE source_id = $1", source_id)
        == 0
    )


@pytest.mark.asyncio
async def test_source_sync_requires_current_workspace_membership(client: AsyncClient, pool):
    owner_key, owner_id = await _register(client, "src_sync_owner")
    ws = await _create_workspace(client, owner_key)
    source = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="TWEBFLOW",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["CWEBFLOW"]},
    )
    source_id = UUID(source["id"])

    await pool.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        ws,
        owner_id,
    )

    due_ids = {UUID(source["id"]) for source in await source_service.due_sources(limit=20)}

    assert source_id not in due_ids
    assert await source_service.get_source_for_sync(source_id) is None


@pytest.mark.asyncio
async def test_unknown_source_type_rejected(client: AsyncClient):
    api_key, _ = await _register(client)
    ws = await _create_workspace(client, api_key)
    resp = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"source_type": "dropbox", "external_ref": "x", "display_name": "x"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_jira_source_rejects_unsafe_external_ref(client: AsyncClient):
    api_key, _ = await _register(client)
    ws = await _create_workspace(client, api_key)
    resp = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "source_type": "jira_project",
            "external_ref": 'cloud-1:PROJ" OR project IS NOT EMPTY',
            "display_name": "unsafe",
        },
        headers=_auth(api_key),
    )
    assert resp.status_code == 400
    assert "Jira projectKey" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_add_slack_source_stores_channel_allowlist(client: AsyncClient, monkeypatch):
    from backend.routers import sources as sources_router

    api_key, _ = await _register(client)
    ws = await _create_workspace(client, api_key)

    async def fake_get_valid_token(user_id, provider):
        assert provider == "slack"
        return "slack-token"

    class FakeSlackProvider:
        async def team_info(self, token):
            assert token == "slack-token"
            return {"team_id": "T123", "team_name": "Acme Slack"}

    monkeypatch.setattr(sources_router.integration_storage, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(sources_router, "get_provider", lambda provider: FakeSlackProvider())

    added = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "source_type": "slack",
            "settings": {"allowed_channel_ids": ["C1", " C2 ", "C1"]},
        },
        headers=_auth(api_key),
    )
    assert added.status_code == 200
    assert added.json()["settings"] == {"allowed_channel_ids": ["C1", "C2"]}

    invalid = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"source_type": "slack", "settings": {"allowed_channel_ids": "C1"}},
        headers=_auth(api_key),
    )
    assert invalid.status_code == 400


# --- user-scoping (the access-control invariant) ----------------------------


@pytest.mark.asyncio
async def test_connected_source_is_user_scoped(client: AsyncClient):
    owner_key, owner_id = await _register(client, "owner")
    other_key, other_id = await _register(client, "other")
    ws = await _create_workspace(client, owner_key)

    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T123",
        display_name="Acme Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(src["id"])

    # Owner sees it; the other user does not.
    assert any(
        s["id"] == src["id"] for s in await source_service.list_connected_sources(ws, owner_id)
    )
    assert await source_service.list_connected_sources(ws, other_id) == []
    assert await source_service.get_owned_source(source_id, owner_id) is not None
    assert await source_service.get_owned_source(source_id, other_id) is None


@pytest.mark.asyncio
async def test_connected_source_handles_are_workspace_scoped(
    client: AsyncClient,
    monkeypatch,
):
    owner_key, owner_id = await _register(client, "owner")
    ws_a = await _create_workspace(client, owner_key)
    ws_b = await _create_workspace(client, owner_key)
    src = await source_service.create_source(
        workspace_id=ws_a,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = src["id"]
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(source_id),
        workspace_id=ws_a,
        path="eng/1",
        name="#eng",
        kind="message",
        content="workspace A roadmap",
        external_ref="C1:1",
        extra={"channel_id": "C1", "channel_name": "eng", "ts": "1"},
    )

    same_workspace = await client.get(
        f"/api/v1/workspaces/{ws_a}/sources/{source_id}/doc",
        params={"ref": "eng/1"},
        headers=_auth(owner_key),
    )
    sent_tasks: list[dict] = []

    def fake_send_task(*args, **kwargs):
        sent_tasks.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("backend.routers.sources.celery.send_task", fake_send_task)
    cross_workspace_doc = await client.get(
        f"/api/v1/workspaces/{ws_b}/sources/{source_id}/doc",
        params={"ref": "eng/1"},
        headers=_auth(owner_key),
    )
    cross_workspace_entries = await client.get(
        f"/api/v1/workspaces/{ws_b}/sources/{source_id}/entries",
        headers=_auth(owner_key),
    )
    cross_workspace_status = await client.get(
        f"/api/v1/workspaces/{ws_b}/sources/{source_id}/status",
        headers=_auth(owner_key),
    )
    cross_workspace_sync = await client.post(
        f"/api/v1/workspaces/{ws_b}/sources/{source_id}/sync",
        headers=_auth(owner_key),
    )
    cross_workspace_delete = await client.delete(
        f"/api/v1/workspaces/{ws_b}/sources/{source_id}",
        headers=_auth(owner_key),
    )

    assert same_workspace.status_code == 200
    assert same_workspace.json()["content"] == "workspace A roadmap"
    assert cross_workspace_doc.status_code == 404
    assert cross_workspace_entries.status_code == 404
    assert cross_workspace_status.status_code == 404
    assert cross_workspace_sync.status_code == 404
    assert cross_workspace_delete.status_code == 404
    assert sent_tasks == []
    assert await source_service.get_owned_source(UUID(source_id), owner_id) is not None


@pytest.mark.asyncio
async def test_search_documents_owner_scoped(client: AsyncClient):
    owner_key, owner_id = await _register(client, "owner")
    _, other_id = await _register(client, "other")
    ws = await _create_workspace(client, owner_key)

    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="#eng/1.ts",
        name="msg",
        kind="message",
        content="the postgres migration is blocked on review",
        extra={"channel_id": "C1", "channel_name": "eng", "ts": "1"},
    )

    owner_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_id, query="postgres migration"
    )
    assert len(owner_hits) == 1
    other_hits = await source_service.search_documents(
        workspace_id=ws, user_id=other_id, query="postgres migration"
    )
    assert other_hits == []


# --- copied-content idempotent re-sync --------------------------------------


@pytest.mark.asyncio
async def test_upsert_idempotency_and_missing_copied_content_delete(
    client: AsyncClient,
    pool,
):
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/widgets",
        display_name="acme/widgets",
    )
    sid = UUID(src["id"])

    def _upsert(path: str, name: str, content: str):
        return source_service.upsert_content_document(
            table="github_documents",
            source_id=sid,
            workspace_id=ws,
            path=path,
            name=name,
            content=content,
        )

    assert await _upsert("README.md", "README.md", "v1") == "inserted"
    # Same content → no work, no re-embed.
    assert await _upsert("README.md", "README.md", "v1") == "unchanged"
    # Changed content → updated.
    assert await _upsert("README.md", "README.md", "v2") == "updated"
    await _upsert("docs/old.md", "old.md", "stale")

    removed = await source_service.remove_missing_documents("github_documents", sid, ["README.md"])
    assert removed == 1
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM github_documents WHERE source_id = $1 AND path = 'docs/old.md'",
            sid,
        )
        == 0
    )
    live = await source_service.list_documents(src)
    assert {d["path"] for d in live} == {"README.md"}


@pytest.mark.asyncio
async def test_missing_index_only_rows_are_soft_deleted(client: AsyncClient, pool):
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="google_drive",
        external_ref="drive-root",
        display_name="Drive",
    )
    sid = UUID(src["id"])
    await source_service.upsert_index_row(
        table="drive_index",
        source_id=sid,
        workspace_id=ws,
        path="old-doc",
        name="Old Doc",
        external_ref="provider-doc",
    )

    removed = await source_service.remove_missing_documents("drive_index", sid, [])

    assert removed == 1
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM drive_index WHERE source_id = $1 AND path = 'old-doc'",
            sid,
        )
        == 1
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM drive_index "
            "WHERE source_id = $1 AND path = 'old-doc' AND deleted_at IS NOT NULL",
            sid,
        )
        == 1
    )
    assert await source_service.list_documents(src) == []


# --- source-aware agent tools -----------------------------------------------


@pytest.mark.asyncio
async def test_source_tools_span_native_and_connected(client: AsyncClient):
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)

    # A native page.
    page = await client.post(
        f"/api/v1/workspaces/{ws}/pages/new",
        json={"name": "Runbook", "content": "# Deploy steps\nrun the migration first"},
        headers=_auth(api_key),
    )
    assert page.status_code == 201

    # A connected source with one document (github copies content, so list/
    # read/search all resolve from the stored body).
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/specs",
        display_name="Specs",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="specs/auth.md",
        name="auth.md",
        content="auth spec: rotate tokens hourly",
    )

    wtoken = agent_runtime._workspace_ctx.set(ws)
    utoken = agent_runtime._user_ctx.set(owner_id)
    try:
        sources = _tool_json(await agent_runtime._list_sources.handler({}))
        handles = {s["source"] for s in sources}
        assert {source_service.NATIVE_FILES, source_service.NATIVE_SESSIONS, src["id"]} <= handles

        # Navigate the connected source like a file system.
        listing = _tool_json(await agent_runtime._list_source.handler({"source": src["id"]}))
        assert any(d["path"] == "specs/auth.md" for d in listing)
        doc = _tool_json(
            await agent_runtime._read_source.handler({"source": src["id"], "ref": "specs/auth.md"})
        )
        assert "rotate tokens hourly" in doc["content"]

        # Navigate native files.
        files_listing = _tool_json(
            await agent_runtime._list_source.handler({"source": source_service.NATIVE_FILES})
        )
        assert any(d["name"] == "Runbook" for d in files_listing)

        # Unscoped search spans native pages + the connected source.
        hits = _tool_json(await agent_runtime._search.handler({"query": "migration"}))
        assert any(h["source"] == source_service.NATIVE_FILES for h in hits)
        scoped = _tool_json(
            await agent_runtime._search.handler({"query": "rotate tokens", "source": src["id"]})
        )
        assert any(h["ref"] == "specs/auth.md" for h in scoped)
    finally:
        agent_runtime._user_ctx.reset(utoken)
        agent_runtime._workspace_ctx.reset(wtoken)


# --- github indexer + sync pipeline -----------------------------------------


def _make_repo_zip(files: dict[str, bytes]) -> bytes:
    """A GitHub-style zipball: every entry under a common `owner-repo-sha/` top."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for rel, content in files.items():
            zf.writestr(f"acme-widgets-deadbeef/{rel}", content)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_github_indexer_crawls_text_files_and_resyncs(client, monkeypatch):
    from backend.integrations.github import indexer
    from backend.tasks import sources as sources_task

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/widgets",
        display_name="acme/widgets",
    )

    zip_v1 = _make_repo_zip(
        {
            "README.md": b"# Widgets\nrun the migration",
            "src/app.py": b"print('hello')",
            "logo.png": b"\x89PNG\x00\x01\x02\x03\xff\xfe",  # binary → skipped
            ".git/config": b"[core]",  # dotdir → skipped
        }
    )

    async def fake_download(url, headers, dest):
        Path(dest).write_bytes(zip_v1)
        return len(zip_v1)

    monkeypatch.setattr(indexer, "_download_archive", fake_download)

    result = await sources_task._sync_source(UUID(src["id"]))
    assert result["status"] == "done"

    docs = await source_service.list_documents(src)
    paths = {d["path"] for d in docs}
    assert paths == {"README.md", "src/app.py"}  # binary + .git skipped

    readme = await source_service.read_document(src, "README.md")
    assert "run the migration" in readme["content"]

    # Re-sync with src/app.py removed → it should be soft-deleted.
    zip_v2 = _make_repo_zip({"README.md": b"# Widgets\nrun the migration"})

    async def fake_download_v2(url, headers, dest):
        Path(dest).write_bytes(zip_v2)
        return len(zip_v2)

    monkeypatch.setattr(indexer, "_download_archive", fake_download_v2)
    await sources_task._sync_source(UUID(src["id"]))
    paths_after = {d["path"] for d in await source_service.list_documents(src)}
    assert paths_after == {"README.md"}


@pytest.mark.asyncio
async def test_sync_source_unknown_type_is_noop(client: AsyncClient, monkeypatch):
    from backend.tasks import sources as sources_task

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/x",
        display_name="x",
    )
    # With no indexer registered for the type, sync is a clean no-op, not a crash.
    monkeypatch.setattr(sources_task, "INDEXERS", {})
    result = await sources_task._sync_source(UUID(src["id"]))
    assert result["status"] == "no_indexer"


@pytest.mark.asyncio
async def test_sync_source_status_redacts_provider_exception(client: AsyncClient, monkeypatch):
    from backend.tasks import sources as sources_task

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/private",
        display_name="private",
    )

    async def fail_with_secret(source):
        raise RuntimeError("upstream failed with token=secret-token and customer transcript")

    captured_logs: list[tuple[str, tuple]] = []

    def capture_error(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(sources_task, "INDEXERS", {"github_repo": fail_with_secret})
    monkeypatch.setattr(sources_task.logger, "error", capture_error)

    result = await sources_task._sync_source(UUID(src["id"]))
    assert result["status"] == "failed"
    assert captured_logs == [
        (
            "source sync failed source=%s source_type=%s exception_type=%s",
            (UUID(src["id"]), "github_repo", "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)

    status = await client.get(
        f"/api/v1/workspaces/{ws}/sources/{src['id']}/status",
        headers=_auth(api_key),
    )
    assert status.status_code == 200
    assert status.json()["sync_error"] == sources_task.SYNC_FAILED_MESSAGE


# --- slack webhook + event ingest -------------------------------------------


def _slack_sign(secret: str, body: bytes) -> tuple[str, str]:
    ts = str(int(time.time()))
    digest = hmac.new(
        secret.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    return ts, f"v0={digest}"


@pytest.mark.asyncio
async def test_slack_webhook_url_verification(client: AsyncClient, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "shhh")
    body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    ts, sig = _slack_sign("shhh", body)
    resp = await client.post(
        "/api/v1/integrations/slack/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "abc123"


@pytest.mark.asyncio
async def test_slack_webhook_rejects_bad_signature(client: AsyncClient, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "shhh")
    body = json.dumps({"type": "url_verification", "challenge": "x"}).encode()
    resp = await client.post(
        "/api/v1/integrations/slack/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": str(int(time.time())),
            "X-Slack-Signature": "v0=deadbeef",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_slack_visibility_requires_channel_allowlist(client: AsyncClient):
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    unconfigured = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(unconfigured["id"]),
        workspace_id=ws,
        path="general/1",
        name="#general",
        kind="message",
        content="secret launch plan",
        external_ref="C1:1",
        extra={"channel_id": "C1", "channel_name": "general", "ts": "1"},
    )

    assert await source_service.list_documents(unconfigured) == []
    assert await source_service.read_document(unconfigured, "general/1") is None
    assert await source_service.source_item_count(unconfigured) == 0
    assert (
        await source_service.search_documents(
            workspace_id=ws, user_id=owner_id, query="secret launch"
        )
        == []
    )

    configured = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T2",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(configured["id"]),
        workspace_id=ws,
        path="general/1",
        name="#general",
        kind="message",
        content="allowed roadmap plan",
        external_ref="C1:1",
        extra={"channel_id": "C1", "channel_name": "general", "ts": "1"},
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(configured["id"]),
        workspace_id=ws,
        path="exec/1",
        name="#exec",
        kind="message",
        content="blocked board plan",
        external_ref="C2:1",
        extra={"channel_id": "C2", "channel_name": "exec", "ts": "1"},
    )

    docs = await source_service.list_documents(configured)
    assert [doc["path"] for doc in docs] == ["general/1"]
    assert await source_service.read_document(configured, "exec/1") is None
    assert await source_service.source_item_count(configured) == 1
    allowed_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_id, query="allowed roadmap"
    )
    blocked_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_id, query="blocked board"
    )
    assert len(allowed_hits) == 1
    assert blocked_hits == []


@pytest.mark.asyncio
async def test_gong_visibility_requires_workspace_allowlist(client: AsyncClient):
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    unconfigured = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="gong_calls",
        external_ref="calls",
        display_name="Gong",
    )
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=UUID(unconfigured["id"]),
        workspace_id=ws,
        path="call-1",
        name="Launch Call",
        kind="call",
        content="secret revenue plan",
        external_ref="call-1",
        extra={"gong_workspace_id": "W1"},
    )

    assert await source_service.list_documents(unconfigured) == []
    assert await source_service.read_document(unconfigured, "call-1") is None
    assert await source_service.source_item_count(unconfigured) == 0
    assert (
        await source_service.search_documents(
            workspace_id=ws, user_id=owner_id, query="secret revenue"
        )
        == []
    )

    configured = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="gong_calls",
        external_ref="calls-2",
        display_name="Gong",
        settings={"allowed_workspace_ids": ["W1"]},
    )
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=UUID(configured["id"]),
        workspace_id=ws,
        path="call-1",
        name="Allowed Call",
        kind="call",
        content="allowed revenue plan",
        external_ref="call-1",
        extra={"gong_workspace_id": "W1"},
    )
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=UUID(configured["id"]),
        workspace_id=ws,
        path="call-2",
        name="Blocked Call",
        kind="call",
        content="blocked revenue plan",
        external_ref="call-2",
        extra={"gong_workspace_id": "W2"},
    )

    docs = await source_service.list_documents(configured)
    assert [doc["path"] for doc in docs] == ["call-1"]
    assert await source_service.read_document(configured, "call-2") is None
    assert await source_service.source_item_count(configured) == 1
    allowed_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_id, query="allowed revenue"
    )
    blocked_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_id, query="blocked revenue"
    )
    assert len(allowed_hits) == 1
    assert blocked_hits == []


@pytest.mark.asyncio
async def test_slack_allowlist_update_purges_disallowed_copied_messages(
    client: AsyncClient,
    pool,
):
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    source = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C_OLD", "C_KEEP"]},
    )
    source_id = UUID(source["id"])
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        workspace_id=ws,
        path="old/1",
        name="#old",
        kind="message",
        content="old confidential launch thread",
        external_ref="C_OLD:1",
        extra={"channel_id": "C_OLD", "channel_name": "old", "ts": "1"},
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        workspace_id=ws,
        path="keep/1",
        name="#keep",
        kind="message",
        content="kept confidential launch thread",
        external_ref="C_KEEP:1",
        extra={"channel_id": "C_KEEP", "channel_name": "keep", "ts": "1"},
    )

    updated = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C_KEEP"]},
    )

    assert updated["id"] == source["id"]
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM slack_messages WHERE source_id = $1 AND channel_id = 'C_OLD'",
            source_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM slack_messages WHERE source_id = $1 AND channel_id = 'C_KEEP'",
            source_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_gong_allowlist_update_purges_disallowed_copied_calls(
    client: AsyncClient,
    pool,
):
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    source = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="gong_calls",
        external_ref="calls",
        display_name="Gong",
        settings={"allowed_workspace_ids": ["W_OLD", "W_KEEP"]},
    )
    source_id = UUID(source["id"])
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=source_id,
        workspace_id=ws,
        path="old-call",
        name="Old Call",
        kind="call",
        content="old confidential sales call",
        external_ref="old-call",
        extra={"gong_workspace_id": "W_OLD"},
    )
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=source_id,
        workspace_id=ws,
        path="keep-call",
        name="Keep Call",
        kind="call",
        content="kept confidential sales call",
        external_ref="keep-call",
        extra={"gong_workspace_id": "W_KEEP"},
    )

    updated = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="gong_calls",
        external_ref="calls",
        display_name="Gong",
        settings={"allowed_workspace_ids": ["W_KEEP"]},
    )

    assert updated["id"] == source["id"]
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM gong_documents "
            "WHERE source_id = $1 AND gong_workspace_id = 'W_OLD'",
            source_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM gong_documents "
            "WHERE source_id = $1 AND gong_workspace_id = 'W_KEEP'",
            source_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_slack_indexer_backfills_only_allowed_channels(
    client: AsyncClient,
    monkeypatch,
    pool,
):
    from backend.integrations.slack import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C_ALLOWED"]},
    )
    source_id = UUID(src["id"])
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        workspace_id=ws,
        path="exec/1",
        name="#exec",
        kind="message",
        content="blocked copied board thread",
        external_ref="C_BLOCKED:1",
        extra={"channel_id": "C_BLOCKED", "channel_name": "exec", "ts": "1"},
    )
    requested_history: list[str] = []

    async def fake_get_valid_token(user_id, provider):
        assert provider == "slack"
        return "slack-token"

    async def fake_slack_get(client, url, params):
        if url == indexer.CONVERSATIONS_LIST_URL:
            return {
                "channels": [
                    {"id": "C_ALLOWED", "name": "general"},
                    {"id": "C_BLOCKED", "name": "exec"},
                ]
            }
        requested_history.append(params["channel"])
        return {"messages": [{"type": "message", "ts": "1", "text": "ship safely"}]}

    monkeypatch.setattr(indexer, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(indexer, "_slack_get", fake_slack_get)

    await indexer.index_slack(src)

    assert requested_history == ["C_ALLOWED"]
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM slack_messages WHERE source_id = $1 AND channel_id = 'C_BLOCKED'",
            source_id,
        )
        == 0
    )
    docs = await source_service.list_documents(src)
    assert [doc["path"] for doc in docs] == ["general/1"]


@pytest.mark.asyncio
async def test_slack_event_ingest_fans_out_per_owner(client: AsyncClient):
    from backend.integrations.slack.indexer import ingest_slack_message

    # Two members each connect the same Slack team, but only the source that
    # explicitly allowed the event channel stores the message.
    owner_a_key, owner_a = await _register(client, "a")
    owner_b_key, owner_b = await _register(client, "b")
    ws = await _create_workspace(client, owner_a_key)
    src_a = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_a,
        source_type="slack",
        external_ref="T_SHARED",
        display_name="Acme",
        settings={"allowed_channel_ids": ["C1"]},
    )
    src_b = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_b,
        source_type="slack",
        external_ref="T_SHARED",
        display_name="Acme",
        settings={"allowed_channel_ids": ["C2"]},
    )

    n = await ingest_slack_message(
        "T_SHARED",
        {"type": "message", "channel": "C1", "ts": "1717.0001", "text": "ship the sources PR"},
    )
    assert n == 1

    # Each owner sees only their own source and only if that source allowed the channel.
    a_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_a, query="ship sources"
    )
    assert any(h["source_id"] == src_a["id"] for h in a_hits)
    assert all(h["source_id"] != src_b["id"] for h in a_hits)
    b_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_b, query="ship sources"
    )
    assert b_hits == []


@pytest.mark.asyncio
async def test_slack_event_ingest_requires_active_member_and_enabled_source(
    client: AsyncClient,
    pool,
):
    from backend.integrations.slack.indexer import ingest_slack_message

    active_key, active_owner = await _register(client, "active_slack")
    stale_key, stale_owner = await _register(client, "stale_slack")
    disabled_key, disabled_owner = await _register(client, "disabled_slack")
    active_ws = await _create_workspace(client, active_key)
    stale_ws = await _create_workspace(client, stale_key)
    disabled_ws = await _create_workspace(client, disabled_key)
    active_source = await source_service.create_source(
        workspace_id=active_ws,
        owner_user_id=active_owner,
        source_type="slack",
        external_ref="T_WEBFLOW",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["C_CONFIDENTIAL"]},
    )
    stale_source = await source_service.create_source(
        workspace_id=stale_ws,
        owner_user_id=stale_owner,
        source_type="slack",
        external_ref="T_WEBFLOW",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["C_CONFIDENTIAL"]},
    )
    disabled_source = await source_service.create_source(
        workspace_id=disabled_ws,
        owner_user_id=disabled_owner,
        source_type="slack",
        external_ref="T_WEBFLOW",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["C_CONFIDENTIAL"]},
    )
    await pool.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        stale_ws,
        stale_owner,
    )
    await pool.execute(
        "UPDATE workspace_sources SET sync_enabled = false WHERE id = $1",
        UUID(disabled_source["id"]),
    )

    ingested = await ingest_slack_message(
        "T_WEBFLOW",
        {
            "type": "message",
            "channel": "C_CONFIDENTIAL",
            "ts": "1717.0002",
            "text": "Webflow confidential Slack event",
        },
    )

    counts = {
        "active": await pool.fetchval(
            "SELECT COUNT(*) FROM slack_messages WHERE source_id = $1",
            UUID(active_source["id"]),
        ),
        "stale": await pool.fetchval(
            "SELECT COUNT(*) FROM slack_messages WHERE source_id = $1",
            UUID(stale_source["id"]),
        ),
        "disabled": await pool.fetchval(
            "SELECT COUNT(*) FROM slack_messages WHERE source_id = $1",
            UUID(disabled_source["id"]),
        ),
    }
    assert ingested == 1
    assert counts == {"active": 1, "stale": 0, "disabled": 0}


@pytest.mark.asyncio
async def test_slack_event_ingest_deletes_removed_messages(client: AsyncClient, pool):
    from backend.integrations.slack.indexer import ingest_slack_message

    api_key, owner_id = await _register(client, "slack_delete")
    ws = await _create_workspace(client, api_key)
    source = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T_DELETE",
        display_name="Acme",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(source["id"])
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        workspace_id=ws,
        path="general/1717.0001",
        name="#general",
        kind="message",
        content="delete this confidential Slack message",
        external_ref="C1:1717.0001",
        extra={"channel_id": "C1", "channel_name": "general", "ts": "1717.0001"},
    )

    deleted = await ingest_slack_message(
        "T_DELETE",
        {
            "type": "message",
            "subtype": "message_deleted",
            "channel": "C1",
            "deleted_ts": "1717.0001",
        },
    )

    assert deleted == 1
    assert (
        await pool.fetchval("SELECT COUNT(*) FROM slack_messages WHERE source_id = $1", source_id)
        == 0
    )


@pytest.mark.asyncio
async def test_slack_event_ingest_updates_changed_messages_without_duplicate(
    client: AsyncClient,
    pool,
):
    from backend.integrations.slack.indexer import ingest_slack_message

    api_key, owner_id = await _register(client, "slack_change")
    ws = await _create_workspace(client, api_key)
    source = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T_CHANGE",
        display_name="Acme",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(source["id"])
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        workspace_id=ws,
        path="general/1717.0001",
        name="#general",
        kind="message",
        content="old confidential Slack message",
        external_ref="C1:1717.0001",
        extra={"channel_id": "C1", "channel_name": "general", "ts": "1717.0001"},
    )

    updated = await ingest_slack_message(
        "T_CHANGE",
        {
            "type": "message",
            "subtype": "message_changed",
            "channel": "C1",
            "message": {
                "type": "message",
                "ts": "1717.0001",
                "text": "updated confidential Slack message",
            },
        },
    )

    rows = await pool.fetch(
        "SELECT path, name, content FROM slack_messages WHERE source_id = $1",
        source_id,
    )
    assert updated == 1
    assert len(rows) == 1
    assert rows[0]["path"] == "general/1717.0001"
    assert rows[0]["name"] == "#general"
    assert rows[0]["content"] == "updated confidential Slack message"


# --- index-only sources (drive): lazy read ----------------------------------


@pytest.mark.asyncio
async def test_drive_index_only_reads_lazily(client: AsyncClient, monkeypatch):
    """Google Drive stores an index row only; reading triggers a lazy provider fetch.
    (Notion used to work this way too, but it now copies content for FTS — Drive is
    the sole remaining index-only source.)"""
    from backend.integrations.google import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="google_drive",
        external_ref="root",
        display_name="My Drive",
    )
    # Index row: path + provider id, no body stored.
    await source_service.upsert_index_row(
        table="drive_index",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="Auth",
        name="Auth",
        kind="file",
        external_ref="file-123",
    )

    fetched: list[str] = []

    async def fake_fetch(owner, file_id):
        fetched.append(file_id)
        return "rotate tokens hourly"

    monkeypatch.setattr(indexer, "fetch_drive_content", fake_fetch)

    doc = await source_service.read_document(src, "Auth")
    assert doc["content"] == "rotate tokens hourly"
    assert fetched == ["file-123"]  # lazily fetched the provider file on read


@pytest.mark.asyncio
async def test_notion_is_full_text_searchable(client: AsyncClient):
    """Notion now copies content, so its docs are served from the table and show
    up in full-text search — no lazy provider fetch on read."""
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="notion",
        external_ref="page-root",
        display_name="Specs",
    )
    await source_service.upsert_content_document(
        table="notion_index",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="Auth",
        name="Auth",
        kind="note",
        content="rotate tokens hourly",
        external_ref="page-123",
    )

    # Read serves the stored body directly (no fetch_notion_content anymore).
    doc = await source_service.read_document(src, "Auth")
    assert doc["content"] == "rotate tokens hourly"

    # And it's full-text searchable, scoped to the Notion source.
    hits = await source_service.search_all(ws, owner_id, "rotate tokens", source=src["id"])
    assert any(h["ref"] == "Auth" for h in hits)


@pytest.mark.asyncio
async def test_jira_is_index_only_with_federated_search(client: AsyncClient, monkeypatch):
    """Jira doesn't copy content: search is federated to the provider live, and
    the issue body is fetched lazily on read."""
    from backend.integrations.jira import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="jira_project",
        external_ref="cloud-1:PROJ",
        display_name="PROJ",
    )
    # Index row only — no body stored; external_ref carries cloudId:key for read.
    await source_service.upsert_index_row(
        table="jira_documents",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="PROJ-9",
        name="PROJ-9: login bug",
        kind="issue",
        external_ref="cloud-1:PROJ-9",
    )

    async def fake_search(source, query, limit):
        assert source["id"] == src["id"]
        return [{"ref": "PROJ-9", "name": "PROJ-9: login bug", "snippet": "login is broken"}]

    async def fake_fetch(owner, external_ref):
        assert external_ref == "cloud-1:PROJ-9"
        return "full issue body: login is broken"

    monkeypatch.setattr(indexer, "search_jira", fake_search)
    monkeypatch.setattr(indexer, "fetch_jira_content", fake_fetch)

    # Search is federated (not our FTS — jira_documents holds no content).
    hits = await source_service.search_all(ws, owner_id, "login", source=src["id"])
    assert any(h["ref"] == "PROJ-9" for h in hits)

    # Read lazily fetches the body from the provider.
    doc = await source_service.read_document(src, "PROJ-9")
    assert "login is broken" in doc["content"]


@pytest.mark.asyncio
async def test_federated_search_logs_only_failure_metadata(client: AsyncClient, monkeypatch):
    from backend.integrations.jira import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="jira_project",
        external_ref="cloud-1:PROJ",
        display_name="PROJ",
    )
    captured_logs: list[tuple[str, tuple]] = []

    async def fail_search(source, query, limit):
        raise RuntimeError(f"token=secret-token and customer transcript query={query}")

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(indexer, "search_jira", fail_search)
    monkeypatch.setattr(source_service.logger, "warning", capture_warning)

    hits = await source_service.search_all(ws, owner_id, "customer transcript", source=src["id"])

    assert hits == []
    assert captured_logs == [
        (
            "federated search failed source=%s source_type=%s exception_type=%s",
            (src["id"], "jira_project", "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_lazy_source_read_failure_logs_only_failure_metadata(
    client: AsyncClient, monkeypatch
):
    from backend.integrations.jira import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="jira_project",
        external_ref="cloud-1:PROJ",
        display_name="PROJ",
    )
    await source_service.upsert_index_row(
        table="jira_documents",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="PROJ-9",
        name="PROJ-9: confidential login bug",
        kind="issue",
        external_ref="cloud-1:PROJ-9",
    )
    captured_logs: list[tuple[str, tuple]] = []
    site_url_called = False

    async def fail_fetch(owner, external_ref):
        raise RuntimeError(f"token=secret-token external_ref={external_ref} customer transcript")

    async def site_url(source):
        nonlocal site_url_called
        site_url_called = True
        return None

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(indexer, "fetch_jira_content", fail_fetch)
    monkeypatch.setattr(indexer, "site_url", site_url)
    monkeypatch.setattr(source_service.logger, "warning", capture_warning)

    source_ok, doc = await source_service.source_document(ws, owner_id, src["id"], "PROJ-9")

    assert source_ok is True
    assert doc == {
        "path": "PROJ-9",
        "name": "PROJ-9: confidential login bug",
        "kind": "issue",
        "content": "",
        "error": "source document fetch failed",
    }
    assert site_url_called is False
    assert captured_logs == [
        (
            "source document fetch failed source=%s source_type=%s exception_type=%s",
            (src["id"], "jira_project", "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "cloud-1:PROJ-9" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_jira_deep_link_logs_only_failure_metadata(client: AsyncClient, monkeypatch):
    from backend.integrations.jira import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="jira_project",
        external_ref="cloud-1:PROJ",
        display_name="PROJ",
    )
    await source_service.upsert_index_row(
        table="jira_documents",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="PROJ-9",
        name="PROJ-9: login bug",
        kind="issue",
        external_ref="cloud-1:PROJ-9",
    )
    captured_logs: list[tuple[str, tuple]] = []

    async def fetch_content(owner, external_ref):
        return "full issue body"

    async def fail_site_url(source):
        raise RuntimeError("token=secret-token and customer transcript")

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(indexer, "fetch_jira_content", fetch_content)
    monkeypatch.setattr(indexer, "site_url", fail_site_url)
    monkeypatch.setattr(source_service.logger, "warning", capture_warning)

    source_ok, doc = await source_service.source_document(ws, owner_id, src["id"], "PROJ-9")

    assert source_ok is True
    assert doc is not None
    assert doc["content"] == "full issue body"
    assert doc["url"] is None
    assert captured_logs == [
        (
            "jira site_url lookup failed source=%s exception_type=%s",
            (src["id"], "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_fetch_history_routes_to_provider_and_rejects_unsupported(client, monkeypatch):
    """fetch_history reaches the provider for a copied, time-windowed source
    (Slack), and is rejected for sources that don't support it (GitHub)."""
    from backend.integrations.slack import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    slack = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T123",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    github = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/x",
        display_name="x",
    )

    captured = {}

    async def fake_fetch(source, since, until, limit):
        captured["since"] = since.isoformat()
        captured["limit"] = limit
        return {"fetched": 2, "since": since.isoformat(), "results": [{"ref": "general/1"}]}

    monkeypatch.setattr(indexer, "fetch_history", fake_fetch)

    res = await source_service.fetch_history(
        ws, owner_id, slack["id"], "2026-01-01", until="2026-02-01"
    )
    assert res["fetched"] == 2
    assert captured["since"].startswith("2026-01-01")

    # GitHub copies the full tree — no time-window history fetch.
    bad = await source_service.fetch_history(ws, owner_id, github["id"], "2026-01-01")
    assert "error" in bad


@pytest.mark.asyncio
async def test_fetch_history_provider_failures_are_redacted(client, monkeypatch):
    from backend.integrations.slack import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    slack = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T123",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    captured_logs: list[tuple[str, tuple]] = []

    async def fail_fetch(source, since, until, limit):
        raise RuntimeError("token=secret-token channel=#board customer transcript")

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(indexer, "fetch_history", fail_fetch)
    monkeypatch.setattr(source_service.logger, "warning", capture_warning)

    result = await source_service.fetch_history(
        ws, owner_id, slack["id"], "2026-01-01", until="2026-02-01"
    )

    assert result == {"error": "source history fetch failed"}
    assert captured_logs == [
        (
            "source history fetch failed source=%s source_type=%s exception_type=%s",
            (slack["id"], "slack", "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
    assert "#board" not in str(captured_logs)


@pytest.mark.asyncio
async def test_list_sources_carries_status_and_status_endpoint_counts(client: AsyncClient):
    """The per-integration page needs sync status + item counts: list_sources now
    carries the status fields, and /status reports the indexed-doc count (None for
    queryable sources with no table)."""
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/widgets",
        display_name="acme/widgets",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="README.md",
        name="README.md",
        content="hi",
    )

    listing = await client.get(f"/api/v1/workspaces/{ws}/sources", headers=_auth(api_key))
    connected = next(s for s in listing.json()["sources"] if s["source"] == src["id"])
    assert "sync_status" in connected and "last_synced_at" in connected

    status = await client.get(
        f"/api/v1/workspaces/{ws}/sources/{src['id']}/status", headers=_auth(api_key)
    )
    assert status.status_code == 200
    assert status.json()["item_count"] == 1

    # A queryable source (snowflake) has no document table → count is None.
    sf = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="snowflake",
        external_ref="acct",
        display_name="Snowflake",
    )
    sf_status = await client.get(
        f"/api/v1/workspaces/{ws}/sources/{sf['id']}/status", headers=_auth(api_key)
    )
    assert sf_status.json()["item_count"] is None


@pytest.mark.asyncio
async def test_read_source_rejects_unowned_connected_source(client: AsyncClient):
    owner_key, owner_id = await _register(client, "owner")
    _, other_id = await _register(client, "other")
    ws = await _create_workspace(client, owner_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/secret",
        display_name="secret",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="README.md",
        name="README.md",
        content="top secret",
    )

    # The other member, asking with their own context, cannot read it.
    wtoken = agent_runtime._workspace_ctx.set(ws)
    utoken = agent_runtime._user_ctx.set(other_id)
    try:
        result = _tool_json(
            await agent_runtime._read_source.handler({"source": src["id"], "ref": "README.md"})
        )
        assert result == {"error": "source not found"}
    finally:
        agent_runtime._user_ctx.reset(utoken)
        agent_runtime._workspace_ctx.reset(wtoken)


def test_source_document_url_builds_provider_deep_links():
    """source_document_url derives a canonical provider URL from stored refs, and
    returns None for sources we can't deep-link yet (Slack/Gong/Granola)."""
    # GitHub: source external_ref is owner/repo, path is the file.
    assert (
        source_service.source_document_url("github_repo", "acme/widgets", "src/app.py")
        == "https://github.com/acme/widgets/blob/HEAD/src/app.py"
    )
    # Asana: the path is the task gid.
    assert (
        source_service.source_document_url("asana_project", None, "1209876")
        == "https://app.asana.com/0/0/1209876"
    )
    # Notion: stored `url` in extra wins; otherwise built from the dashless id.
    assert (
        source_service.source_document_url(
            "notion", None, "abc-def", extra={"url": "https://www.notion.so/Page-abcdef"}
        )
        == "https://www.notion.so/Page-abcdef"
    )
    assert (
        source_service.source_document_url("notion", None, "abc-def")
        == "https://www.notion.so/abcdef"
    )
    # Slack has no deep link yet → None.
    assert source_service.source_document_url("slack", "T123", "#eng/1.ts") is None


# --- cartridge snapshot-on-add ----------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_source_into_cartridge_copies_lazy_content(client: AsyncClient, monkeypatch):
    """Adding an index-only (Google Drive) source doc to a cartridge fetches its
    body at add time and copies it in as a page, so the bundle is self-contained."""
    from backend.integrations.google import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)

    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="google_drive",
        external_ref="root",
        display_name="My Drive",
    )
    await source_service.upsert_index_row(
        table="drive_index",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="Auth",
        name="Auth",
        kind="file",
        external_ref="file-abc",
    )

    async def fake_fetch(owner, file_id):
        return f"snapshot body for {file_id}"

    monkeypatch.setattr(indexer, "fetch_drive_content", fake_fetch)

    cartridge = await client.post(
        f"/api/v1/workspaces/{ws}/cartridges",
        json={"title": "Bundle", "public_permission": "read", "items": []},
        headers=_auth(api_key),
    )
    assert cartridge.status_code == 201
    cartridge_id = cartridge.json()["id"]

    snap = await client.post(
        f"/api/v1/workspaces/{ws}/cartridges/{cartridge_id}/snapshot-source",
        json={"source_id": src["id"], "path": "Auth"},
        headers=_auth(api_key),
    )
    assert snap.status_code == 201
    page = snap.json()
    assert page["name"] == "Auth"
    # The body was copied in (a point-in-time snapshot), not left as a live ref.
    assert "snapshot body for file-abc" in page["content_markdown"]

    # And the page is now an item in the cartridge.
    public = await client.get(f"/api/v1/cartridges/{cartridge.json()['slug']}")
    item_ids = {i["object_id"] for i in public.json()["items"]}
    assert page["id"] in item_ids


@pytest.mark.asyncio
async def test_snapshot_source_into_cartridge_requires_same_workspace(client: AsyncClient, pool):
    api_key, owner_id = await _register(client)
    ws_a = await _create_workspace(client, api_key)
    ws_b = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws_a,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(src["id"]),
        workspace_id=ws_a,
        path="eng/1",
        name="#eng",
        kind="message",
        content="workspace A roadmap",
        external_ref="C1:1",
        extra={"channel_id": "C1", "channel_name": "eng", "ts": "1"},
    )
    cartridge = await client.post(
        f"/api/v1/workspaces/{ws_b}/cartridges",
        json={"title": "Bundle", "workspace_permission": "none", "items": []},
        headers=_auth(api_key),
    )
    assert cartridge.status_code == 201
    cartridge_id = cartridge.json()["id"]

    snap = await client.post(
        f"/api/v1/workspaces/{ws_b}/cartridges/{cartridge_id}/snapshot-source",
        json={"source_id": src["id"], "path": "eng/1"},
        headers=_auth(api_key),
    )
    copied_pages = await pool.fetchval(
        "SELECT COUNT(*) FROM pages "
        "WHERE workspace_id = $1 AND metadata->>'shared_in_cartridge_id' = $2",
        ws_b,
        cartridge_id,
    )

    assert snap.status_code == 404
    assert copied_pages == 0


# --- VFS REST endpoints (browse / read / search) ----------------------------


@pytest.mark.asyncio
async def test_vfs_endpoints_browse_read_search(client: AsyncClient):
    """The unified VFS surface the agent uses is also reachable over REST so the
    CLI + MCP can browse, read, and search sources the same way."""
    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)

    page = await client.post(
        f"/api/v1/workspaces/{ws}/pages/new",
        json={"name": "Runbook", "content": "# Deploy\nrun the migration first"},
        headers=_auth(api_key),
    )
    assert page.status_code == 201
    page_id = page.json()["id"]

    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/specs",
        display_name="Specs",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="specs/auth.md",
        name="auth.md",
        content="auth spec: rotate tokens hourly",
    )

    # Browse a connected source like a file system.
    entries = await client.get(
        f"/api/v1/workspaces/{ws}/sources/{src['id']}/entries", headers=_auth(api_key)
    )
    assert entries.status_code == 200
    assert any(e["path"] == "specs/auth.md" for e in entries.json()["entries"])

    # Browse native files.
    files = await client.get(
        f"/api/v1/workspaces/{ws}/sources/{source_service.NATIVE_FILES}/entries",
        headers=_auth(api_key),
    )
    assert any(e["name"] == "Runbook" for e in files.json()["entries"])

    # Read a connected-source document and a native page.
    doc = await client.get(
        f"/api/v1/workspaces/{ws}/sources/{src['id']}/doc",
        params={"ref": "specs/auth.md"},
        headers=_auth(api_key),
    )
    assert doc.status_code == 200
    assert "rotate tokens hourly" in doc.json()["content"]

    native_doc = await client.get(
        f"/api/v1/workspaces/{ws}/sources/{source_service.NATIVE_FILES}/doc",
        params={"ref": page_id},
        headers=_auth(api_key),
    )
    assert native_doc.status_code == 200
    assert "migration" in native_doc.json()["content"]

    # Unscoped search spans native pages + the connected source.
    everything = await client.get(
        f"/api/v1/workspaces/{ws}/sources/search", params={"q": "migration"}, headers=_auth(api_key)
    )
    assert everything.status_code == 200
    assert any(h["source"] == source_service.NATIVE_FILES for h in everything.json()["results"])

    # Scoped search hits only the named source.
    scoped = await client.get(
        f"/api/v1/workspaces/{ws}/sources/search",
        params={"q": "rotate tokens", "source": src["id"]},
        headers=_auth(api_key),
    )
    assert any(h["ref"] == "specs/auth.md" for h in scoped.json()["results"])


@pytest.mark.asyncio
async def test_vfs_endpoints_reject_unowned_source(client: AsyncClient):
    """A member can't browse / read / search another member's connected source —
    every VFS endpoint resolves it as a not-found source."""
    owner_key, owner_id = await _register(client, "owner")
    ws = await _create_workspace(client, owner_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/private",
        display_name="Private",
    )

    # A second member of the same workspace.
    other_key, _ = await _register(client, "other")
    invite = await client.post(
        f"/api/v1/workspaces/{ws}/invite-tokens", json={"max_uses": 1}, headers=_auth(owner_key)
    )
    token = invite.json()["token"]
    await client.post(
        "/api/v1/workspaces/redeem-invite", json={"token": token}, headers=_auth(other_key)
    )

    for path, params in (
        (f"/api/v1/workspaces/{ws}/sources/{src['id']}/entries", {}),
        (f"/api/v1/workspaces/{ws}/sources/{src['id']}/doc", {"ref": "x"}),
        (f"/api/v1/workspaces/{ws}/sources/search", {"q": "anything", "source": src["id"]}),
    ):
        resp = await client.get(path, params=params, headers=_auth(other_key))
        assert resp.status_code == 404, path

    # The owner still does not see it leak into the other member's listing.
    other_listing = await client.get(f"/api/v1/workspaces/{ws}/sources", headers=_auth(other_key))
    assert src["id"] not in {s["source"] for s in other_listing.json()["sources"]}
