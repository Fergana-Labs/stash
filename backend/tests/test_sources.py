"""Phase 1 sources foundation: registry, index store, and source-aware tools.

Covers the user-scoping invariant (a connected source is visible only to its
owner), idempotent re-sync of the per-integration tables, lazy reads for the
index-only sources (drive/notion), and the agent tools that span native (files,
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
async def test_unknown_source_type_rejected(client: AsyncClient):
    api_key, _ = await _register(client)
    ws = await _create_workspace(client, api_key)
    resp = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"source_type": "dropbox", "external_ref": "x", "display_name": "x"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 400


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
    )
    source_id = UUID(src["id"])

    # Owner sees it; the other user does not.
    assert any(s["id"] == src["id"] for s in await source_service.list_connected_sources(ws, owner_id))
    assert await source_service.list_connected_sources(ws, other_id) == []
    assert await source_service.get_owned_source(source_id, owner_id) is not None
    assert await source_service.get_owned_source(source_id, other_id) is None


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
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="#eng/1.ts",
        name="msg",
        kind="message",
        content="the postgres migration is blocked on review",
    )

    owner_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_id, query="postgres migration"
    )
    assert len(owner_hits) == 1
    other_hits = await source_service.search_documents(
        workspace_id=ws, user_id=other_id, query="postgres migration"
    )
    assert other_hits == []


# --- source_documents idempotent re-sync ------------------------------------


@pytest.mark.asyncio
async def test_upsert_idempotency_and_soft_delete(client: AsyncClient):
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

    # A re-sync that only saw README.md soft-deletes docs/old.md.
    removed = await source_service.soft_delete_missing("github_documents", sid, ["README.md"])
    assert removed == 1
    live = await source_service.list_documents(src)
    assert {d["path"] for d in live} == {"README.md"}


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
        listing = _tool_json(
            await agent_runtime._list_source.handler({"source": src["id"]})
        )
        assert any(d["path"] == "specs/auth.md" for d in listing)
        doc = _tool_json(
            await agent_runtime._read_source.handler(
                {"source": src["id"], "ref": "specs/auth.md"}
            )
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


# --- slack webhook + event ingest -------------------------------------------


def _slack_sign(secret: str, body: bytes) -> tuple[str, str]:
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256).hexdigest()
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
async def test_slack_event_ingest_fans_out_per_owner(client: AsyncClient):
    from backend.integrations.slack.indexer import ingest_slack_message

    # Two members each connect the same Slack team — each gets their own source.
    owner_a_key, owner_a = await _register(client, "a")
    owner_b_key, owner_b = await _register(client, "b")
    ws = await _create_workspace(client, owner_a_key)
    src_a = await source_service.create_source(
        workspace_id=ws, owner_user_id=owner_a, source_type="slack",
        external_ref="T_SHARED", display_name="Acme",
    )
    src_b = await source_service.create_source(
        workspace_id=ws, owner_user_id=owner_b, source_type="slack",
        external_ref="T_SHARED", display_name="Acme",
    )

    n = await ingest_slack_message(
        "T_SHARED",
        {"type": "message", "channel": "C1", "ts": "1717.0001", "text": "ship the sources PR"},
    )
    assert n == 2  # both team sources updated

    # Each owner sees the message only in their own source.
    a_hits = await source_service.search_documents(
        workspace_id=ws, user_id=owner_a, query="ship sources"
    )
    assert any(h["source_id"] == src_a["id"] for h in a_hits)
    assert all(h["source_id"] != src_b["id"] for h in a_hits)


# --- index-only sources (drive/notion): lazy read ---------------------------


@pytest.mark.asyncio
async def test_notion_index_only_reads_lazily(client: AsyncClient, monkeypatch):
    """Notion stores an index row only; reading triggers a lazy provider fetch."""
    from backend.integrations.notion import indexer

    api_key, owner_id = await _register(client)
    ws = await _create_workspace(client, api_key)
    src = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="notion",
        external_ref="page-root",
        display_name="Specs",
    )
    # Index row: path + provider id, no body stored.
    await source_service.upsert_index_row(
        table="notion_index",
        source_id=UUID(src["id"]),
        workspace_id=ws,
        path="Auth",
        name="Auth",
        kind="note",
        external_ref="page-123",
    )

    fetched: list[str] = []

    async def fake_fetch(owner, page_id):
        fetched.append(page_id)
        return "rotate tokens hourly"

    monkeypatch.setattr(indexer, "fetch_notion_content", fake_fetch)

    doc = await source_service.read_document(src, "Auth")
    assert doc["content"] == "rotate tokens hourly"
    assert fetched == ["page-123"]  # lazily fetched the provider page on read


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
