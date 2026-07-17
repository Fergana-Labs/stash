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
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from backend.routers import sources as sources_router
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


async def _user_scope(client: AsyncClient, api_key: str) -> UUID:
    """The scope a user owns is just the user id (owner_user_id == user id)."""
    resp = await client.get("/api/v1/users/me", headers=_auth(api_key))
    assert resp.status_code == 200
    return UUID(resp.json()["id"])


def _tool_json(result: dict):
    return json.loads(result["content"][0]["text"])


def _external_ref_for_source_type(source_type: str) -> str:
    refs = {
        "github_repo": "acme/widgets",
        "gmail": "cleanup@example.com",
        "google_drive": "drive-root",
        "google_drive_folder": "drive-folder-1",
        "notion": "notion-root",
        "slack": "T123",
        "granola": "granola",
        "jira_project": "cloud-1:PROJ_1",
        "asana_project": "asana-project-1",
        "linear": "me",
        "gong_calls": "gong-source",
        "x_saves": "saves",
        "instagram_saves": "saves",
        "posthog_project": "project",
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
    owner_user_id: UUID,
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
            owner_user_id=owner_user_id,
            path="record-1",
            name="Record 1",
            external_ref="provider-record-1",
        )
        return

    extra = {}
    if table == "slack_messages":
        extra = {"channel_id": "C123", "channel_name": "eng", "ts": "1720000000.000100"}
    elif table == "gong_documents":
        extra = {"gong_account_id": "GONG_WS"}

    await source_service.upsert_content_document(
        table=table,
        source_id=source_id,
        owner_user_id=owner_user_id,
        path="record-1",
        name="Record 1",
        content="confidential customer content",
        external_ref="provider-record-1",
        extra=extra,
    )


async def _insert_slack_source_without_channels(owner_id: UUID) -> dict:
    from backend.database import get_pool

    row = await get_pool().fetchrow(
        """
        INSERT INTO user_sources (
            owner_user_id, source_type, external_ref,
            display_name, capability, sync_interval_s, sync_enabled, settings
        )
        VALUES ($1, 'slack', 'T1', 'Slack', 'searchable', 21600, true, '{}'::jsonb)
        RETURNING id
        """,
        owner_id,
    )
    source = await source_service.get_source_for_sync(row["id"])
    assert source is not None
    return source


# --- registry endpoints -----------------------------------------------------


@pytest.mark.asyncio
async def test_add_list_remove_source(client: AsyncClient):
    api_key, _ = await _register(client)

    add = await client.post(
        "/api/v1/me/sources",
        json={
            "source_type": "github_repo",
            "external_ref": "acme/widgets",
            "display_name": "acme/widgets",
        },
        headers=_auth(api_key),
    )
    assert add.status_code == 200
    source_id = add.json()["id"]

    listing = await client.get("/api/v1/me/sources", headers=_auth(api_key))
    assert listing.status_code == 200
    sources = listing.json()["sources"]
    handles = {s["source"] for s in sources}
    # Native sources are always present; the connected source shows by id.
    assert source_service.NATIVE_FILES in handles
    assert source_service.NATIVE_SESSIONS in handles
    assert source_id in handles

    removed = await client.delete(f"/api/v1/me/sources/{source_id}", headers=_auth(api_key))
    assert removed.status_code == 200
    after = await client.get("/api/v1/me/sources", headers=_auth(api_key))
    assert source_id not in {s["source"] for s in after.json()["sources"]}


@pytest.mark.asyncio
async def test_disconnect_provider_removes_sources_and_copied_documents(
    client: AsyncClient,
    monkeypatch,
    _db_pool,
):
    from backend.integrations import router as integrations_router

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    slack = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T123",
        display_name="Acme Slack",
        settings={"allowed_channel_ids": ["C123"]},
    )
    github = await source_service.create_source(
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
        owner_user_id=ws,
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
    ws = await _user_scope(client, api_key)
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type=source_type,
        external_ref=_external_ref_for_source_type(source_type),
        display_name=f"{source_type} source",
        settings=_settings_for_source_type(source_type),
    )
    source_id = UUID(source["id"])
    await _insert_representative_source_document(owner_user_id=ws, source=source)

    removed_sources = await source_service.delete_sources_for_provider(owner_id, provider)

    assert [UUID(removed["id"]) for removed in removed_sources] == [source_id]
    assert await source_service.get_owned_source(source_id, owner_id) is None
    table = source_service.SOURCE_TABLE.get(source_type)
    if table is not None:
        assert (
            await _db_pool.fetchval(f"SELECT COUNT(*) FROM {table} WHERE source_id = $1", source_id)
            == 0
        )


@pytest.mark.asyncio
async def test_source_sync_resolves_via_owner(client: AsyncClient):
    """A source's scope is its owner_user_id, which is the user itself — it can't
    be handed off, so the sync queue and the sync-task fetch always resolve it
    from that owner directly."""
    owner_key, owner_id = await _register(client, "src_sync_owner")
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="TWEBFLOW",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["CWEBFLOW"]},
    )
    source_id = UUID(source["id"])

    due_ids = {UUID(source["id"]) for source in await source_service.due_sources(limit=20)}

    assert source_id in due_ids
    fetched = await source_service.get_source_for_sync(source_id)
    assert fetched is not None
    assert UUID(fetched["owner_user_id"]) == owner_id


@pytest.mark.asyncio
async def test_due_sources_reclaims_stuck_syncing(client: AsyncClient, _db_pool):
    """A sync killed mid-run leaves the source 'syncing'; due_sources reclaims it
    once it's been stuck past the threshold, but leaves a fresh one alone."""
    _, owner_id = await _register(client, "src_stuck")
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="TSTUCK",
        display_name="Stuck",
        settings={"allowed_channel_ids": ["CSTUCK"]},
    )
    sid = UUID(source["id"])

    # Currently syncing and not due by schedule, freshly started -> left alone.
    await _db_pool.execute(
        "UPDATE user_sources SET sync_status = 'syncing', "
        "next_sync_at = now() + interval '1 hour', updated_at = now() WHERE id = $1",
        sid,
    )
    due = {UUID(s["id"]) for s in await source_service.due_sources(limit=50)}
    assert sid not in due

    # Stuck syncing past the threshold -> reclaimed even though not schedule-due.
    await _db_pool.execute(
        "UPDATE user_sources SET updated_at = now() - interval '15 minutes' WHERE id = $1", sid
    )
    due = {UUID(s["id"]) for s in await source_service.due_sources(limit=50)}
    assert sid in due


@pytest.mark.asyncio
async def test_unknown_source_type_rejected(client: AsyncClient):
    api_key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/me/sources",
        json={"source_type": "dropbox", "external_ref": "x", "display_name": "x"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_jira_source_rejects_unsafe_external_ref(client: AsyncClient):
    api_key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/me/sources",
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
        "/api/v1/me/sources",
        json={
            "source_type": "slack",
            "settings": {"allowed_channel_ids": ["C1", " C2 ", "C1"]},
        },
        headers=_auth(api_key),
    )
    assert added.status_code == 200
    assert added.json()["settings"] == {"allowed_channel_ids": ["C1", "C2"]}

    missing = await client.post(
        "/api/v1/me/sources",
        json={"source_type": "slack"},
        headers=_auth(api_key),
    )
    assert missing.status_code == 400
    assert "allowed_channel_ids" in missing.json()["detail"]

    invalid = await client.post(
        "/api/v1/me/sources",
        json={"source_type": "slack", "settings": {"allowed_channel_ids": "C1"}},
        headers=_auth(api_key),
    )
    assert invalid.status_code == 400


@pytest.mark.asyncio
async def test_slack_channel_picker_lists_conversations(client: AsyncClient, monkeypatch):
    from backend.integrations import router as integrations_router
    from backend.integrations.slack import indexer

    api_key, _ = await _register(client)

    async def fake_get_valid_token(user_id, provider):
        assert provider == "slack"
        return "slack-token"

    class FakeSlackResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeSlackClient:
        def __init__(self, *, timeout, headers):
            assert timeout == 30.0
            assert headers["Authorization"] == "Bearer slack-token"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params):
            if url == integrations_router.SLACK_CONVERSATIONS_LIST_URL:
                assert params == {
                    "types": integrations_router.SLACK_CHANNEL_TYPES,
                    "limit": integrations_router.SLACK_CHANNEL_LIMIT,
                }
                return FakeSlackResponse(
                    {
                        "ok": True,
                        "channels": [
                            {"id": "C1", "name": "general", "is_private": False},
                            {"id": "G1", "name": "leadership", "is_private": True},
                            {"id": "D1", "is_im": True, "user": "U1"},
                        ],
                    }
                )
            if url == indexer.AUTH_TEST_URL:
                return FakeSlackResponse({"ok": True, "user_id": "U_SELF"})
            assert url == indexer.USERS_INFO_URL and params == {"user": "U1"}
            return FakeSlackResponse(
                {"ok": True, "user": {"name": "sam", "profile": {"display_name": "Sam Liu"}}}
            )

    monkeypatch.setattr(integrations_router.storage, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(integrations_router.httpx, "AsyncClient", FakeSlackClient)

    resp = await client.get("/api/v1/integrations/slack/channels", headers=_auth(api_key))

    assert resp.status_code == 200
    # The DM surfaces as the human it's with — never the raw D…/U… id.
    assert resp.json() == [
        {"id": "C1", "name": "general", "is_private": False},
        {"id": "G1", "name": "leadership", "is_private": True},
        {"id": "D1", "name": "dm-sam-liu", "is_private": False},
    ]


# --- user-scoping (the access-control invariant) ----------------------------


@pytest.mark.asyncio
async def test_connected_source_is_user_scoped(client: AsyncClient):
    owner_key, owner_id = await _register(client, "owner")
    other_key, other_id = await _register(client, "other")
    await _user_scope(client, owner_key)

    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T123",
        display_name="Acme Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(src["id"])

    # Owner sees it; the other user does not.
    assert any(s["id"] == src["id"] for s in await source_service.list_connected_sources(owner_id))
    assert await source_service.list_connected_sources(other_id) == []
    assert await source_service.get_owned_source(source_id, owner_id) is not None
    assert await source_service.get_owned_source(source_id, other_id) is None


@pytest.mark.asyncio
async def test_connected_source_handles_are_owner_scoped(
    client: AsyncClient,
    monkeypatch,
):
    owner_key, owner_id = await _register(client, "owner")
    # Sources are user-scoped: another user's scope can't reach them.
    other_key, other_id = await _register(client, "other")
    ws_a = await _user_scope(client, owner_key)
    src = await source_service.create_source(
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
        owner_user_id=ws_a,
        path="eng/1",
        name="#eng",
        kind="message",
        content="owner A roadmap",
        external_ref="C1:1",
        extra={"channel_id": "C1", "channel_name": "eng", "ts": "1"},
    )

    same_owner = await client.get(
        f"/api/v1/me/sources/{source_id}/doc",
        params={"ref": "eng/1"},
        headers=_auth(owner_key),
    )
    sent_tasks: list[dict] = []

    def fake_send_task(*args, **kwargs):
        sent_tasks.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("backend.routers.sources.celery.send_task", fake_send_task)
    cross_owner_doc = await client.get(
        f"/api/v1/me/sources/{source_id}/doc",
        params={"ref": "eng/1"},
        headers=_auth(other_key),
    )
    cross_owner_entries = await client.get(
        f"/api/v1/me/sources/{source_id}/entries",
        headers=_auth(other_key),
    )
    cross_owner_status = await client.get(
        f"/api/v1/me/sources/{source_id}/status",
        headers=_auth(other_key),
    )
    cross_owner_sync = await client.post(
        f"/api/v1/me/sources/{source_id}/sync",
        headers=_auth(other_key),
    )
    cross_owner_delete = await client.delete(
        f"/api/v1/me/sources/{source_id}",
        headers=_auth(other_key),
    )

    assert same_owner.status_code == 200
    assert same_owner.json()["content"] == "owner A roadmap"
    assert cross_owner_doc.status_code == 404
    assert cross_owner_entries.status_code == 404
    assert cross_owner_status.status_code == 404
    assert cross_owner_sync.status_code == 404
    assert cross_owner_delete.status_code == 404
    assert sent_tasks == []
    assert await source_service.get_owned_source(UUID(source_id), owner_id) is not None


@pytest.mark.asyncio
async def test_search_documents_owner_scoped(client: AsyncClient):
    owner_key, owner_id = await _register(client, "owner")
    _, other_id = await _register(client, "other")
    ws = await _user_scope(client, owner_key)

    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="#eng/1.ts",
        name="msg",
        kind="message",
        content="the postgres migration is blocked on review",
        extra={"channel_id": "C1", "channel_name": "eng", "ts": "1"},
    )

    owner_hits = await source_service.search_documents(user_id=owner_id, query="postgres migration")
    assert len(owner_hits) == 1
    other_hits = await source_service.search_documents(user_id=other_id, query="postgres migration")
    assert other_hits == []


# --- copied-content idempotent re-sync --------------------------------------


@pytest.mark.asyncio
async def test_upsert_idempotency_and_missing_copied_content_delete(
    client: AsyncClient,
    pool,
):
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
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
            owner_user_id=ws,
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
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive",
        external_ref="drive-root",
        display_name="Drive",
    )
    sid = UUID(src["id"])
    await source_service.upsert_index_row(
        table="drive_index",
        source_id=sid,
        owner_user_id=ws,
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


@pytest.mark.asyncio
async def test_list_documents_pages_with_after_cursor(client: AsyncClient):
    """A source bigger than one page must be fully reachable by walking the
    `after` keyset cursor — before this, everything past the first page was
    invisible to the VFS (a 6k-message Gmail showed 200 messages)."""
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive",
        external_ref="drive-root",
        display_name="Drive",
    )
    sid = UUID(src["id"])
    for i in range(5):
        await source_service.upsert_index_row(
            table="drive_index",
            source_id=sid,
            owner_user_id=ws,
            path=f"doc-{i}",
            name=f"Doc {i}",
            external_ref=f"file-id-{i}",
        )

    page_one = await source_service.list_documents(src, limit=2)
    page_two = await source_service.list_documents(src, limit=2, after=page_one[-1]["path"])
    page_three = await source_service.list_documents(src, limit=2, after=page_two[-1]["path"])

    assert [d["path"] for d in page_one] == ["doc-0", "doc-1"]
    assert [d["path"] for d in page_two] == ["doc-2", "doc-3"]
    assert [d["path"] for d in page_three] == ["doc-4"]
    # The provider id rides along so callers can tie a path to the provider object.
    assert page_one[0]["external_ref"] == "file-id-0"


@pytest.mark.asyncio
async def test_search_all_resolves_a_provider_id_to_its_document(client: AsyncClient):
    """An agent holding only a provider URL (a Drive link, a GitHub blob) must
    be able to resolve the id inside it to the document's Stash path — the
    external_ref is the only join key between the provider's world and ours."""
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/widgets",
        display_name="acme/widgets",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="docs/status.md",
        name="status.md",
        content="quarterly integration status",
        external_ref="gh-blob-1a2b3c",
    )

    results = await source_service.search_all(ws, owner_id, "gh-blob-1a2b3c", source=src["id"])

    assert [(r["ref"], r["name"]) for r in results] == [("docs/status.md", "status.md")]
    assert await source_service.search_all(ws, owner_id, "no-such-id", source=src["id"]) == []


@pytest.mark.asyncio
async def test_upsert_index_row_updates_on_name_change(client: AsyncClient):
    """name is part of the freshness check: an index row's name can change
    without external_updated_at moving. Dropping the comparison would leave
    stale names in list/search forever."""
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="linear",
        external_ref="me",
        display_name="Linear",
    )
    sid = UUID(src["id"])

    kwargs = dict(
        table="linear_index",
        source_id=sid,
        owner_user_id=ws,
        path="ISS-1",
        kind="issue",
        external_ref="ISS-1",
        external_updated_at=None,
    )
    assert await source_service.upsert_index_row(name="Old title", **kwargs) == "inserted"
    assert await source_service.upsert_index_row(name="Old title", **kwargs) == "unchanged"
    assert await source_service.upsert_index_row(name="New title", **kwargs) == "updated"
    live = await source_service.list_documents(src)
    assert [d["name"] for d in live] == ["New title"]


# --- source-aware agent tools -----------------------------------------------


@pytest.mark.asyncio
async def test_source_tools_span_native_and_connected(client: AsyncClient):
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)

    # A native page.
    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Runbook", "content": "# Deploy steps\nrun the migration first"},
        headers=_auth(api_key),
    )
    assert page.status_code == 201

    # A connected source with one document (github copies content, so list/
    # read/search all resolve from the stored body).
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/specs",
        display_name="Specs",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="specs/auth.md",
        name="auth.md",
        content="auth spec: rotate tokens hourly",
    )

    scope_token = agent_runtime._scope_ctx.set(ws)
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
        agent_runtime._scope_ctx.reset(scope_token)


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
    src = await source_service.create_source(
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

    # HEAD moves between the two syncs, so both crawl.
    shas = iter(["a" * 40, "b" * 40])

    async def fake_head_sha(url, headers):
        return next(shas)

    async def fake_snapshot_tree(url, headers, sha):
        return {"truncated": False, "tree": [{"type": "blob", "size": 10}]}

    monkeypatch.setattr(indexer, "_github_head_sha", fake_head_sha)
    monkeypatch.setattr(indexer, "_github_snapshot_tree", fake_snapshot_tree)
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
async def test_github_indexer_skips_files_too_big_to_index(client, monkeypatch):
    # Postgres caps a row's tsvector at 1MB and github_documents is FTS-indexed
    # on content, so an oversized text file (minified bundle, lockfile) must be
    # skipped like a binary — not abort the whole repo's sync at insert time.
    from backend.integrations.github import indexer
    from backend.tasks import sources as sources_task

    api_key, owner_id = await _register(client)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/bundled",
        display_name="acme/bundled",
    )

    bundle = b"var x=1;" * (indexer.MAX_INDEXED_TEXT_BYTES // 8 + 1)
    repo_zip = _make_repo_zip(
        {
            "README.md": b"# Bundled",
            "dist/bundle.min.js": bundle,
        }
    )

    async def fake_head_sha(url, headers):
        return "d" * 40

    async def fake_download(url, headers, dest):
        Path(dest).write_bytes(repo_zip)
        return len(repo_zip)

    async def fake_snapshot_tree(url, headers, sha):
        return {"truncated": False, "tree": [{"type": "blob", "size": 10}]}

    monkeypatch.setattr(indexer, "_github_head_sha", fake_head_sha)
    monkeypatch.setattr(indexer, "_github_snapshot_tree", fake_snapshot_tree)
    monkeypatch.setattr(indexer, "_download_archive", fake_download)

    result = await sources_task._sync_source(UUID(src["id"]))
    assert result["status"] == "done"

    paths = {d["path"] for d in await source_service.list_documents(src)}
    assert paths == {"README.md"}


@pytest.mark.asyncio
async def test_sync_source_unknown_type_is_noop(client: AsyncClient, monkeypatch):
    from backend.tasks import sources as sources_task

    api_key, owner_id = await _register(client)
    src = await source_service.create_source(
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
    src = await source_service.create_source(
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
        f"/api/v1/me/sources/{src['id']}/status",
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
    ws = await _user_scope(client, api_key)
    unconfigured = await _insert_slack_source_without_channels(owner_id)
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(unconfigured["id"]),
        owner_user_id=ws,
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
    assert await source_service.search_documents(user_id=owner_id, query="secret launch") == []

    configured = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T2",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(configured["id"]),
        owner_user_id=ws,
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
        owner_user_id=ws,
        path="exec/1",
        name="#exec",
        kind="message",
        content="blocked board plan",
        external_ref="C2:1",
        extra={"channel_id": "C2", "channel_name": "exec", "ts": "1"},
    )

    # Messages project as one transcript per channel per UTC day; ts=1 epoch
    # lands on 1970-01-01. The blocked channel contributes no document.
    docs = await source_service.list_documents(configured)
    assert [doc["path"] for doc in docs] == ["general/1970-01-01"]
    assert await source_service.read_document(configured, "exec/1") is None
    assert await source_service.source_item_count(configured) == 1
    allowed_hits = await source_service.search_documents(user_id=owner_id, query="allowed roadmap")
    blocked_hits = await source_service.search_documents(user_id=owner_id, query="blocked board")
    assert len(allowed_hits) == 1
    assert blocked_hits == []


@pytest.mark.asyncio
async def test_gong_visibility_requires_account_allowlist(client: AsyncClient):
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    unconfigured = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="gong_calls",
        external_ref="calls",
        display_name="Gong",
    )
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=UUID(unconfigured["id"]),
        owner_user_id=ws,
        path="call-1",
        name="Launch Call",
        kind="call",
        content="secret revenue plan",
        external_ref="call-1",
        extra={"gong_account_id": "W1"},
    )

    assert await source_service.list_documents(unconfigured) == []
    assert await source_service.read_document(unconfigured, "call-1") is None
    assert await source_service.source_item_count(unconfigured) == 0
    assert await source_service.search_documents(user_id=owner_id, query="secret revenue") == []

    configured = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="gong_calls",
        external_ref="calls-2",
        display_name="Gong",
        settings={"allowed_workspace_ids": ["W1"]},
    )
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=UUID(configured["id"]),
        owner_user_id=ws,
        path="call-1",
        name="Allowed Call",
        kind="call",
        content="allowed revenue plan",
        external_ref="call-1",
        extra={"gong_account_id": "W1"},
    )
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=UUID(configured["id"]),
        owner_user_id=ws,
        path="call-2",
        name="Blocked Call",
        kind="call",
        content="blocked revenue plan",
        external_ref="call-2",
        extra={"gong_account_id": "W2"},
    )

    docs = await source_service.list_documents(configured)
    assert [doc["path"] for doc in docs] == ["call-1"]
    assert await source_service.read_document(configured, "call-2") is None
    assert await source_service.source_item_count(configured) == 1
    allowed_hits = await source_service.search_documents(user_id=owner_id, query="allowed revenue")
    blocked_hits = await source_service.search_documents(user_id=owner_id, query="blocked revenue")
    assert len(allowed_hits) == 1
    assert blocked_hits == []


@pytest.mark.asyncio
async def test_slack_allowlist_update_purges_disallowed_copied_messages(
    client: AsyncClient,
    pool,
):
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    source = await source_service.create_source(
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
        owner_user_id=ws,
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
        owner_user_id=ws,
        path="keep/1",
        name="#keep",
        kind="message",
        content="kept confidential launch thread",
        external_ref="C_KEEP:1",
        extra={"channel_id": "C_KEEP", "channel_name": "keep", "ts": "1"},
    )

    updated = await source_service.create_source(
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
    ws = await _user_scope(client, api_key)
    source = await source_service.create_source(
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
        owner_user_id=ws,
        path="old-call",
        name="Old Call",
        kind="call",
        content="old confidential sales call",
        external_ref="old-call",
        extra={"gong_account_id": "W_OLD"},
    )
    await source_service.upsert_content_document(
        table="gong_documents",
        source_id=source_id,
        owner_user_id=ws,
        path="keep-call",
        name="Keep Call",
        kind="call",
        content="kept confidential sales call",
        external_ref="keep-call",
        extra={"gong_account_id": "W_KEEP"},
    )

    updated = await source_service.create_source(
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
            "WHERE source_id = $1 AND gong_account_id = 'W_OLD'",
            source_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM gong_documents "
            "WHERE source_id = $1 AND gong_account_id = 'W_KEEP'",
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
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
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
        owner_user_id=ws,
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
        if url == indexer.AUTH_TEST_URL:
            return {"user_id": "U_SELF"}
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
    assert [doc["path"] for doc in docs] == ["general/1970-01-01"]


@pytest.mark.asyncio
async def test_slack_sync_without_channels_records_sync_error(client: AsyncClient):
    from backend.tasks import sources as sources_task

    # A malformed Slack source with no channel allowlist must not report a
    # successful sync that silently ingested nothing.
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await _insert_slack_source_without_channels(owner_id)

    result = await sources_task._sync_source(UUID(src["id"]))

    assert result["status"] == "failed"
    sources = await source_service.list_sources(ws, owner_id)
    slack = next(s for s in sources if s["type"] == "slack")
    assert slack["sync_status"] == "failed"
    # The stored error is a redacted constant — raw exception text could carry
    # secrets, so the detail lives only in server logs.
    assert slack["sync_error"] == sources_task.SYNC_FAILED_MESSAGE


def _fake_webhook_channel_resolution(monkeypatch, channel_name="general"):
    """A live event for a never-synced channel resolves its name against Slack
    with the owner's token — fake that seam for webhook tests."""
    from backend.integrations.slack import indexer

    async def fake_get_valid_token(user_id, provider):
        return "slack-token"

    async def fake_slack_get(client_, url, params):
        if url == indexer.AUTH_TEST_URL:
            return {"user_id": "U_SELF"}
        assert url == indexer.CONVERSATIONS_INFO_URL
        return {"channel": {"id": params["channel"], "name": channel_name}}

    monkeypatch.setattr(indexer, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(indexer, "_slack_get", fake_slack_get)


@pytest.mark.asyncio
async def test_slack_event_ingest_fans_out_per_owner(client: AsyncClient, monkeypatch):
    from backend.integrations.slack.indexer import ingest_slack_message

    _fake_webhook_channel_resolution(monkeypatch)
    # Two users each connect the same Slack team, but only the source that
    # explicitly allowed the event channel stores the message.
    owner_a_key, owner_a = await _register(client, "a")
    owner_b_key, owner_b = await _register(client, "b")
    await _user_scope(client, owner_a_key)
    src_a = await source_service.create_source(
        owner_user_id=owner_a,
        source_type="slack",
        external_ref="T_SHARED",
        display_name="Acme",
        settings={"allowed_channel_ids": ["C1"]},
    )
    src_b = await source_service.create_source(
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
    a_hits = await source_service.search_documents(user_id=owner_a, query="ship sources")
    assert any(h["source_id"] == src_a["id"] for h in a_hits)
    assert all(h["source_id"] != src_b["id"] for h in a_hits)
    b_hits = await source_service.search_documents(user_id=owner_b, query="ship sources")
    assert b_hits == []


@pytest.mark.asyncio
async def test_slack_event_ingest_requires_enabled_source(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    from backend.integrations.slack.indexer import ingest_slack_message

    _fake_webhook_channel_resolution(monkeypatch)
    _, active_owner = await _register(client, "active_slack")
    _, disabled_owner = await _register(client, "disabled_slack")
    active_source = await source_service.create_source(
        owner_user_id=active_owner,
        source_type="slack",
        external_ref="T_WEBFLOW",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["C_CONFIDENTIAL"]},
    )
    disabled_source = await source_service.create_source(
        owner_user_id=disabled_owner,
        source_type="slack",
        external_ref="T_WEBFLOW",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["C_CONFIDENTIAL"]},
    )
    await pool.execute(
        "UPDATE user_sources SET sync_enabled = false WHERE id = $1",
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
        "disabled": await pool.fetchval(
            "SELECT COUNT(*) FROM slack_messages WHERE source_id = $1",
            UUID(disabled_source["id"]),
        ),
    }
    assert ingested == 1
    assert counts == {"active": 1, "disabled": 0}


@pytest.mark.asyncio
async def test_slack_event_ingest_deletes_removed_messages(client: AsyncClient, pool):
    from backend.integrations.slack.indexer import ingest_slack_message

    api_key, owner_id = await _register(client, "slack_delete")
    ws = await _user_scope(client, api_key)
    source = await source_service.create_source(
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
        owner_user_id=ws,
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
    ws = await _user_scope(client, api_key)
    source = await source_service.create_source(
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
        owner_user_id=ws,
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


@pytest.mark.asyncio
async def test_slack_projects_day_transcripts_with_authors(client: AsyncClient):
    """The agent-facing projection is one attributed transcript per channel per
    UTC day — not one file per message. Chronology and authorship must survive
    into both the listing (external_updated_at/size) and the rendered body,
    and a per-message ref (what search returns) must resolve to its day."""
    api_key, owner_id = await _register(client, "slack_days")
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T_DAYS",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    # 2026-07-05 18:17/18:18 UTC and 2026-07-06 01:24 UTC — two UTC days.
    messages = [
        ("1783275420.000100", "henry", "interesting treehacks project"),
        ("1783275480.000200", "sam", "lol"),
        ("1783301040.000300", "henry", "I'm gonna try these three"),
    ]
    for ts, author, text in messages:
        await source_service.upsert_content_document(
            table="slack_messages",
            source_id=UUID(src["id"]),
            owner_user_id=ws,
            path=f"random/{ts}",
            name="#random",
            kind="message",
            content=text,
            external_ref=f"C1:{ts}",
            extra={
                "channel_id": "C1",
                "channel_name": "random",
                "ts": ts,
                "author_id": f"U_{author}",
                "author": author,
            },
        )

    docs = await source_service.list_documents(src)
    assert [d["path"] for d in docs] == ["random/2026-07-05", "random/2026-07-06"]
    assert [d["kind"] for d in docs] == ["transcript", "transcript"]
    day_one = docs[0]
    assert day_one["name"] == "#random 2026-07-05"
    assert day_one["external_updated_at"].startswith("2026-07-05")
    assert day_one["size"] == len("interesting treehacks project") + len("lol")

    doc = await source_service.read_document(src, "random/2026-07-05")
    assert doc["kind"] == "transcript"
    lines = doc["content"].splitlines()
    assert lines[0] == "# #random — 2026-07-05 (UTC)"
    assert "henry: interesting treehacks project" in lines[2]
    assert "sam: lol" in lines[3]
    assert lines[2] < lines[3]  # HH:MM prefixes keep the transcript chronological

    # A search/history ref (channel/ts) reads as the day it belongs to.
    by_ref = await source_service.read_document(src, "random/1783301040.000300")
    assert by_ref["path"] == "random/2026-07-06"


@pytest.mark.asyncio
async def test_slack_backfill_resolves_authors_and_caches_lookups(
    client: AsyncClient, monkeypatch, pool
):
    """Backfilled messages must be attributable: msg["user"] resolves to a
    display name via users.info, one lookup per distinct user per sync."""
    from backend.integrations.slack import indexer

    api_key, owner_id = await _register(client, "slack_authors")
    await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T_AUTHORS",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    users_info_calls: list[str] = []

    async def fake_get_valid_token(user_id, provider):
        return "slack-token"

    async def fake_slack_get(client_, url, params):
        if url == indexer.CONVERSATIONS_LIST_URL:
            return {"channels": [{"id": "C1", "name": "general"}]}
        if url == indexer.AUTH_TEST_URL:
            return {"user_id": "U_SELF"}
        if url == indexer.USERS_INFO_URL:
            users_info_calls.append(params["user"])
            return {"ok": True, "user": {"name": "hdowling", "profile": {"display_name": "henry"}}}
        return {
            "messages": [
                {"type": "message", "ts": "1783362000.1", "text": "one", "user": "U_HENRY"},
                {"type": "message", "ts": "1783362001.1", "text": "two", "user": "U_HENRY"},
            ]
        }

    monkeypatch.setattr(indexer, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(indexer, "_slack_get", fake_slack_get)

    await indexer.index_slack(src)

    assert users_info_calls == ["U_HENRY"]  # cached after the first resolution
    rows = await pool.fetch(
        "SELECT author_id, author FROM slack_messages WHERE source_id = $1 ORDER BY ts",
        UUID(src["id"]),
    )
    assert [(r["author_id"], r["author"]) for r in rows] == [
        ("U_HENRY", "henry"),
        ("U_HENRY", "henry"),
    ]


@pytest.mark.asyncio
async def test_slack_backfill_discloses_history_cap(client: AsyncClient, monkeypatch):
    """A channel whose history exceeds the backfill cap must say so in its
    listing — an agent must be able to tell "never discussed" apart from
    "not indexed". The notice lists first and clears when history fits."""
    from backend.integrations.slack import indexer

    api_key, owner_id = await _register(client, "slack_cap")
    await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T_CAP",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    has_more = True

    async def fake_get_valid_token(user_id, provider):
        return "slack-token"

    async def fake_slack_get(client_, url, params):
        if url == indexer.CONVERSATIONS_LIST_URL:
            return {"channels": [{"id": "C1", "name": "general"}]}
        if url == indexer.AUTH_TEST_URL:
            return {"user_id": "U_SELF"}
        return {
            "messages": [{"type": "message", "ts": "1783362000.1", "text": "hi"}],
            "has_more": has_more,
        }

    monkeypatch.setattr(indexer, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(indexer, "_slack_get", fake_slack_get)

    await indexer.index_slack(src)
    docs = await source_service.list_documents(src)
    assert [d["kind"] for d in docs] == ["notice", "transcript"]
    assert docs[0]["path"] == f"general/{indexer.CAP_MARKER_LEAF}"
    notice = await source_service.read_document(src, docs[0]["path"])
    assert "not searchable here" in notice["content"]

    # Full history now fits — the stale notice must disappear.
    has_more = False
    await indexer.index_slack(src)
    docs = await source_service.list_documents(src)
    assert [d["kind"] for d in docs] == ["transcript"]


@pytest.mark.asyncio
async def test_slack_dms_are_named_after_their_humans(client: AsyncClient, monkeypatch, pool):
    """A DM carries no name in Slack's API — it must surface as the person
    you're talking to (dm-sam-liu), and a group DM as everyone except
    yourself. Rows ingested before the name was known (webhook rows stamped
    with the raw channel id) must migrate onto the resolved name at sync."""
    from backend.integrations.slack import indexer

    api_key, owner_id = await _register(client, "slack_dms")
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T_DMS",
        display_name="Slack",
        settings={"allowed_channel_ids": ["D1", "G1"]},
    )
    # A pre-fix webhook row, stamped with the raw channel id as its name.
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="D1/1783362000.0",
        name="#D1",
        kind="message",
        content="pre-fix webhook message",
        external_ref="D1:1783362000.0",
        extra={"channel_id": "D1", "channel_name": "D1", "ts": "1783362000.0"},
    )

    user_names = {"U_SAM": "Sam Liu", "U_JANE": "Jane Doe"}

    async def fake_get_valid_token(user_id, provider):
        return "slack-token"

    async def fake_slack_get(client_, url, params):
        if url == indexer.CONVERSATIONS_LIST_URL:
            return {
                "channels": [
                    {"id": "D1", "is_im": True, "user": "U_SAM"},
                    {"id": "G1", "is_mpim": True},
                ]
            }
        if url == indexer.AUTH_TEST_URL:
            return {"user_id": "U_SELF"}
        if url == indexer.CONVERSATIONS_MEMBERS_URL:
            assert params["channel"] == "G1"
            return {"members": ["U_SELF", "U_SAM", "U_JANE"]}
        if url == indexer.USERS_INFO_URL:
            return {"user": {"name": "n", "profile": {"display_name": user_names[params["user"]]}}}
        return {
            "messages": [{"type": "message", "ts": "1783362001.0", "text": "hey", "user": "U_SAM"}]
        }

    monkeypatch.setattr(indexer, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(indexer, "_slack_get", fake_slack_get)

    await indexer.index_slack(src)

    docs = await source_service.list_documents(src)
    assert sorted(d["path"] for d in docs) == [
        "dm-jane-doe--sam-liu/2026-07-06",
        "dm-sam-liu/2026-07-06",
    ]
    migrated = await pool.fetchrow(
        "SELECT path, name, channel_name FROM slack_messages "
        "WHERE source_id = $1 AND ts = '1783362000.0'",
        UUID(src["id"]),
    )
    assert migrated["path"] == "dm-sam-liu/1783362000.0"
    assert migrated["name"] == "#dm-sam-liu"
    assert migrated["channel_name"] == "dm-sam-liu"


@pytest.mark.asyncio
async def test_slack_event_ingest_drops_edits_of_subtyped_messages(
    client: AsyncClient,
    pool,
):
    """Fresh subtyped messages (bot_message, thread_broadcast, ...) are never
    ingested, so editing one must not sneak it in via message_changed either."""
    from backend.integrations.slack.indexer import ingest_slack_message

    api_key, owner_id = await _register(client, "slack_bot_edit")
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T_BOT_EDIT",
        display_name="Acme",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(source["id"])

    ingested = await ingest_slack_message(
        "T_BOT_EDIT",
        {
            "type": "message",
            "subtype": "message_changed",
            "channel": "C1",
            "message": {
                "type": "message",
                "subtype": "bot_message",
                "ts": "1717.0002",
                "text": "edited bot message",
            },
        },
    )

    assert ingested == 0
    assert (
        await pool.fetchval("SELECT COUNT(*) FROM slack_messages WHERE source_id = $1", source_id)
        == 0
    )


# --- index-only sources (drive): lazy read ----------------------------------


@pytest.mark.asyncio
async def test_drive_index_only_reads_lazily(client: AsyncClient, monkeypatch):
    """Google Drive stores an index row only; reading triggers a lazy provider fetch.
    (Notion used to work this way too, but it now copies content for FTS — Drive is
    the sole remaining index-only source.)"""
    from backend.integrations.google import indexer

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive",
        external_ref="root",
        display_name="My Drive",
    )
    # Index row: path + provider id, no body stored.
    await source_service.upsert_index_row(
        table="drive_index",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
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
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="notion",
        external_ref="page-root",
        display_name="Specs",
    )
    await source_service.upsert_content_document(
        table="notion_index",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
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
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="jira_project",
        external_ref="cloud-1:PROJ",
        display_name="PROJ",
    )
    # Index row only — no body stored; external_ref carries cloudId:key for read.
    await source_service.upsert_index_row(
        table="jira_documents",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
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
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
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

    # Unscoped fan-out surfaces a redacted error marker (never raising) and logs
    # only failure metadata; a scoped search raises instead.
    hits = await source_service.search_all(ws, owner_id, "customer transcript")

    assert hits == [
        {
            "source": src["id"],
            "source_name": "PROJ",
            "error": "PROJ search failed",
            "needs_reconnect": False,
        }
    ]
    assert captured_logs == [
        (
            "federated search failed source=%s source_type=%s exception_type=%s",
            (src["id"], "jira_project", "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
    # An unmapped exception's raw text (token, query) must not leak into the
    # surfaced marker either.
    assert "secret-token" not in str(hits)
    assert "customer transcript" not in str(hits)


@pytest.mark.asyncio
async def test_unscoped_search_surfaces_dead_federated_source(client: AsyncClient, monkeypatch):
    """A dead connection (expired/revoked token) must not vanish from unscoped
    search as if it had no matches — it surfaces a needs_reconnect marker so the
    caller can tell "reconnect me" apart from "nothing found"."""
    from fastapi import HTTPException

    from backend.integrations.gmail import indexer

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="gmail",
        external_ref="henry@ferganalabs.com",
        display_name="Gmail (henry@ferganalabs.com)",
    )

    async def dead_search(source, query, limit):
        raise HTTPException(status_code=401, detail="gmail token expired; reconnect required")

    monkeypatch.setattr(indexer, "search_gmail", dead_search)

    results = await source_service.search_all(ws, owner_id, "anything")

    markers = [r for r in results if r.get("source") == src["id"]]
    assert markers == [
        {
            "source": src["id"],
            "source_name": "Gmail (henry@ferganalabs.com)",
            "error": "gmail token expired; reconnect required",
            "needs_reconnect": True,
        }
    ]


@pytest.mark.asyncio
async def test_search_appends_truncation_marker_when_provider_caps(
    client: AsyncClient, monkeypatch
):
    """A capped federated result must disclose the cut: search appends a
    truncation marker so callers don't present the top slice as the whole set."""
    from backend.integrations.gmail import indexer

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="gmail",
        external_ref="henry@ferganalabs.com",
        display_name="Gmail (henry@ferganalabs.com)",
    )

    async def capped_search(source, query, limit):
        return {
            "hits": [{"ref": f"m{i}", "name": f"msg {i}", "snippet": ""} for i in range(2)],
            "truncated": True,
            "estimated_total": 213,
        }

    monkeypatch.setattr(indexer, "search_gmail", capped_search)
    results = await source_service.search_all(ws, owner_id, "anything", source=src["id"])

    assert [r for r in results if r.get("ref")] == [
        {
            "source": src["id"],
            "source_name": "Gmail (henry@ferganalabs.com)",
            "ref": "m0",
            "name": "msg 0",
            "snippet": "",
        },
        {
            "source": src["id"],
            "source_name": "Gmail (henry@ferganalabs.com)",
            "ref": "m1",
            "name": "msg 1",
            "snippet": "",
        },
    ]
    assert [r for r in results if r.get("truncated")] == [
        {
            "source": src["id"],
            "source_name": "Gmail (henry@ferganalabs.com)",
            "truncated": True,
            "returned": 2,
            "estimated_total": 213,
        }
    ]


@pytest.mark.asyncio
async def test_search_omits_truncation_marker_when_not_capped(client: AsyncClient, monkeypatch):
    from backend.integrations.gmail import indexer

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="gmail",
        external_ref="henry@ferganalabs.com",
        display_name="Gmail (henry@ferganalabs.com)",
    )

    async def complete_search(source, query, limit):
        return {
            "hits": [{"ref": "m0", "name": "only", "snippet": ""}],
            "truncated": False,
            "estimated_total": 1,
        }

    monkeypatch.setattr(indexer, "search_gmail", complete_search)
    results = await source_service.search_all(ws, owner_id, "anything", source=src["id"])

    assert not any(r.get("truncated") for r in results)


@pytest.mark.asyncio
async def test_search_gmail_reports_truncation_from_next_page_token(monkeypatch):
    """search_gmail maps Gmail's nextPageToken to truncated and surfaces the
    resultSizeEstimate — the authoritative "there is more" signal, not a
    len(hits) == limit guess."""
    from backend.integrations.gmail import indexer

    class GmailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    async def token(*args, **kwargs):
        return "tok"

    async def get_metadata(client, message_id):
        return {"id": message_id, "payload": {"headers": [{"name": "Subject", "value": "hi"}]}}

    async def upsert(source, message):
        return message["id"]

    monkeypatch.setattr(indexer, "get_valid_token", token)
    monkeypatch.setattr(indexer.httpx, "AsyncClient", lambda *a, **k: GmailClient())
    monkeypatch.setattr(indexer, "_get_message_metadata", get_metadata)
    monkeypatch.setattr(indexer, "_upsert_message_metadata", upsert)
    source = {"id": str(uuid4()), "owner_user_id": str(uuid4()), "external_ref": "e@x.com"}

    async def more_pages(client, query, limit):
        return [{"id": "m1"}, {"id": "m2"}], "PAGE_2", 213

    monkeypatch.setattr(indexer, "_list_message_refs", more_pages)
    result = await indexer.search_gmail(source, "q", 25)
    assert result["truncated"] is True
    assert result["estimated_total"] == 213
    assert len(result["hits"]) == 2

    async def last_page(client, query, limit):
        return [{"id": "m1"}], None, 1

    monkeypatch.setattr(indexer, "_list_message_refs", last_page)
    result = await indexer.search_gmail(source, "q", 25)
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_lazy_source_read_failure_logs_only_failure_metadata(
    client: AsyncClient, monkeypatch
):
    from backend.integrations.jira import indexer

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="jira_project",
        external_ref="cloud-1:PROJ",
        display_name="PROJ",
    )
    await source_service.upsert_index_row(
        table="jira_documents",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
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
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="jira_project",
        external_ref="cloud-1:PROJ",
        display_name="PROJ",
    )
    await source_service.upsert_index_row(
        table="jira_documents",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
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
    ws = await _user_scope(client, api_key)
    slack = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T123",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    github = await source_service.create_source(
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
    ws = await _user_scope(client, api_key)
    slack = await source_service.create_source(
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
    carries the status fields, and /status reports the indexed-doc count."""
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/widgets",
        display_name="acme/widgets",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="README.md",
        name="README.md",
        content="hi",
    )

    listing = await client.get("/api/v1/me/sources", headers=_auth(api_key))
    connected = next(s for s in listing.json()["sources"] if s["source"] == src["id"])
    assert "sync_status" in connected and "last_synced_at" in connected

    status = await client.get(f"/api/v1/me/sources/{src['id']}/status", headers=_auth(api_key))
    assert status.status_code == 200
    assert status.json()["item_count"] == 1


@pytest.mark.asyncio
async def test_read_source_rejects_unowned_connected_source(client: AsyncClient):
    owner_key, owner_id = await _register(client, "owner")
    _, other_id = await _register(client, "other")
    ws = await _user_scope(client, owner_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/secret",
        display_name="secret",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="README.md",
        name="README.md",
        content="top secret",
    )

    # The other user, asking with their own context, cannot read it.
    scope_token = agent_runtime._scope_ctx.set(ws)
    utoken = agent_runtime._user_ctx.set(other_id)
    try:
        result = _tool_json(
            await agent_runtime._read_source.handler({"source": src["id"], "ref": "README.md"})
        )
        assert result == {"error": "source not found"}
    finally:
        agent_runtime._user_ctx.reset(utoken)
        agent_runtime._scope_ctx.reset(scope_token)


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


# --- skill snapshot-on-add ----------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_source_into_skill_copies_lazy_content(client: AsyncClient, monkeypatch):
    """Adding an index-only (Google Drive) source doc to a skill fetches its
    body at add time and copies it in as a page, so the bundle is self-contained."""
    from backend.integrations.google import indexer

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)

    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive",
        external_ref="root",
        display_name="My Drive",
    )
    await source_service.upsert_index_row(
        table="drive_index",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="Auth",
        name="Auth",
        kind="file",
        external_ref="file-abc",
    )

    async def fake_fetch(owner, file_id):
        return f"snapshot body for {file_id}"

    monkeypatch.setattr(indexer, "fetch_drive_content", fake_fetch)

    folder = await client.post(
        "/api/v1/me/folders",
        json={"name": "Bundle"},
        headers=_auth(api_key),
    )
    assert folder.status_code == 201
    skill = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder.json()["id"], "title": "Bundle"},
        headers=_auth(api_key),
    )
    assert skill.status_code == 201
    skill_id = skill.json()["id"]

    snap = await client.post(
        f"/api/v1/me/skills/{skill_id}/snapshot-source",
        json={"source_id": src["id"], "path": "Auth"},
        headers=_auth(api_key),
    )
    assert snap.status_code == 201
    page = snap.json()
    assert page["name"] == "Auth"
    # The body was copied in (a point-in-time snapshot), not left as a live ref.
    assert "snapshot body for file-abc" in page["content_markdown"]

    # And the snapshot page landed inside the skill's folder.
    public = await client.get(f"/api/v1/skills/{skill.json()['slug']}")
    page_ids = {p["id"] for p in public.json()["contents"]["pages"]}
    assert page["id"] in page_ids


@pytest.mark.asyncio
async def test_snapshot_source_into_skill_fails_when_provider_fetch_fails(
    client: AsyncClient, pool, monkeypatch
):
    """A failed provider fetch must fail the snapshot request — never persist
    an empty page or record a success audit event for content that was
    never copied."""
    from backend.integrations.google import indexer

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)

    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive",
        external_ref="root",
        display_name="My Drive",
    )
    await source_service.upsert_index_row(
        table="drive_index",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="Auth",
        name="Auth",
        kind="file",
        external_ref="file-abc",
    )

    async def fail_fetch(owner, file_id):
        raise RuntimeError("provider down")

    monkeypatch.setattr(indexer, "fetch_drive_content", fail_fetch)

    folder = await client.post(
        "/api/v1/me/folders",
        json={"name": "Bundle"},
        headers=_auth(api_key),
    )
    assert folder.status_code == 201
    skill = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder.json()["id"], "title": "Bundle"},
        headers=_auth(api_key),
    )
    assert skill.status_code == 201
    skill_id = skill.json()["id"]

    snap = await client.post(
        f"/api/v1/me/skills/{skill_id}/snapshot-source",
        json={"source_id": src["id"], "path": "Auth"},
        headers=_auth(api_key),
    )
    copied_pages = await pool.fetchval(
        "SELECT COUNT(*) FROM pages WHERE owner_user_id = $1 AND name = 'Auth'",
        ws,
    )
    snapshot_events = await pool.fetchval(
        "SELECT COUNT(*) FROM security_audit_events "
        "WHERE owner_user_id = $1 AND action = 'source.document_snapshotted'",
        ws,
    )

    assert snap.status_code == 404
    assert copied_pages == 0
    assert snapshot_events == 0


@pytest.mark.asyncio
async def test_snapshot_source_into_skill_requires_same_owner(client: AsyncClient, pool):
    # Sources are user-scoped: a different user can't snapshot the owner's source.
    api_key, owner_id = await _register(client)
    other_key, other_id = await _register(client, "other_snap")
    ws_a = await _user_scope(client, api_key)
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T1",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=UUID(src["id"]),
        owner_user_id=ws_a,
        path="eng/1",
        name="#eng",
        kind="message",
        content="owner A roadmap",
        external_ref="C1:1",
        extra={"channel_id": "C1", "channel_name": "eng", "ts": "1"},
    )
    folder = await client.post(
        "/api/v1/me/folders",
        json={"name": "Bundle"},
        headers=_auth(other_key),
    )
    assert folder.status_code == 201
    folder_id = folder.json()["id"]
    skill = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder_id, "title": "Bundle"},
        headers=_auth(other_key),
    )
    assert skill.status_code == 201
    skill_id = skill.json()["id"]

    snap = await client.post(
        f"/api/v1/me/skills/{skill_id}/snapshot-source",
        json={"source_id": src["id"], "path": "eng/1"},
        headers=_auth(other_key),
    )
    copied_pages = await pool.fetchval(
        "SELECT COUNT(*) FROM pages WHERE folder_id = $1 AND name = '#eng'",
        UUID(folder_id),
    )

    assert snap.status_code == 404
    assert copied_pages == 0


# --- VFS REST endpoints (browse / read / search) ----------------------------


@pytest.mark.asyncio
async def test_vfs_endpoints_browse_read_search(client: AsyncClient):
    """The unified VFS surface the agent uses is also reachable over REST so the
    CLI + MCP can browse, read, and search sources the same way."""
    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)

    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Runbook", "content": "# Deploy\nrun the migration first"},
        headers=_auth(api_key),
    )
    assert page.status_code == 201
    page_id = page.json()["id"]

    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/specs",
        display_name="Specs",
    )
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=UUID(src["id"]),
        owner_user_id=ws,
        path="specs/auth.md",
        name="auth.md",
        content="auth spec: rotate tokens hourly",
    )

    # Browse a connected source like a file system.
    entries = await client.get(f"/api/v1/me/sources/{src['id']}/entries", headers=_auth(api_key))
    assert entries.status_code == 200
    assert any(e["path"] == "specs/auth.md" for e in entries.json()["entries"])

    # Browse native files.
    files = await client.get(
        f"/api/v1/me/sources/{source_service.NATIVE_FILES}/entries",
        headers=_auth(api_key),
    )
    assert any(e["name"] == "Runbook" for e in files.json()["entries"])

    # Read a connected-source document and a native page.
    doc = await client.get(
        f"/api/v1/me/sources/{src['id']}/doc",
        params={"ref": "specs/auth.md"},
        headers=_auth(api_key),
    )
    assert doc.status_code == 200
    assert "rotate tokens hourly" in doc.json()["content"]

    native_doc = await client.get(
        f"/api/v1/me/sources/{source_service.NATIVE_FILES}/doc",
        params={"ref": page_id},
        headers=_auth(api_key),
    )
    assert native_doc.status_code == 200
    assert "migration" in native_doc.json()["content"]

    # Unscoped search spans native pages + the connected source.
    everything = await client.get(
        "/api/v1/me/sources/search", params={"q": "migration"}, headers=_auth(api_key)
    )
    assert everything.status_code == 200
    assert any(h["source"] == source_service.NATIVE_FILES for h in everything.json()["results"])

    # Scoped search hits only the named source.
    scoped = await client.get(
        "/api/v1/me/sources/search",
        params={"q": "rotate tokens", "source": src["id"]},
        headers=_auth(api_key),
    )
    assert any(h["ref"] == "specs/auth.md" for h in scoped.json()["results"])


@pytest.mark.asyncio
async def test_vfs_endpoints_reject_unowned_source(client: AsyncClient):
    """Another user can't browse / read / search someone else's connected source —
    every VFS endpoint resolves it as a not-found source (the scope itself is
    owner-private, so the non-owner gets 404 on every path)."""
    owner_key, owner_id = await _register(client, "owner")
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="github_repo",
        external_ref="acme/private",
        display_name="Private",
    )

    other_key, _ = await _register(client, "other")

    for path, params in (
        (f"/api/v1/me/sources/{src['id']}/entries", {}),
        (f"/api/v1/me/sources/{src['id']}/doc", {"ref": "x"}),
        ("/api/v1/me/sources/search", {"q": "anything", "source": src["id"]}),
    ):
        resp = await client.get(path, params=params, headers=_auth(other_key))
        assert resp.status_code == 404, path

    # The source never leaks into the other user's own listing either.
    other_listing = await client.get("/api/v1/me/sources", headers=_auth(other_key))
    assert other_listing.status_code == 200
    assert src["id"] not in {s["source"] for s in other_listing.json()["sources"]}


# --- Linear: navigable + searchable source ----------------------------------


async def _create_linear_source(ws: UUID, owner_id: UUID) -> dict:
    return await source_service.create_source(
        owner_user_id=owner_id,
        source_type="linear",
        external_ref="me",
        display_name="Linear",
    )


@pytest.mark.asyncio
async def test_linear_source_resolves_to_all_issues(monkeypatch):
    """A Linear source has one canonical ref ('me') covering every issue the
    connected user can read; the resolver only confirms the token exists."""

    async def fake_token(user_id, provider):
        assert provider == "linear"
        return "tok"

    monkeypatch.setattr(sources_router.integration_storage, "get_valid_token", fake_token)

    external_ref, display_name = await sources_router._resolve_linear_source(uuid4())

    assert external_ref == "me"
    assert display_name == "Linear"


@pytest.mark.asyncio
async def test_linear_index_builds_navigable_issue_rows(client: AsyncClient, monkeypatch):
    """The sync paginates the user's issues into a navigable index — one row per
    issue filed under its team folder in numeric order — without copying the body."""
    from backend.integrations.linear import indexer as linear_indexer
    from backend.services import linear_api_service

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await _create_linear_source(ws, owner_id)

    async def fake_token(user_id, provider):
        return "tok"

    pages = [
        ([{"identifier": "FER-1", "title": "First", "updated_at": None}], "cursor-1"),
        ([{"identifier": "FER-2", "title": "Second", "updated_at": None}], None),
    ]

    async def fake_list_issues(token, after=None):
        return pages.pop(0)

    monkeypatch.setattr(linear_indexer, "get_valid_token", fake_token)
    monkeypatch.setattr(linear_api_service, "list_issues", fake_list_issues)

    await linear_indexer.index_linear(src)

    live = await source_service.list_documents(src)
    assert {d["path"] for d in live} == {"FER/FER-00001", "FER/FER-00002"}
    assert {d["name"] for d in live} == {"FER-1 First", "FER-2 Second"}


@pytest.mark.asyncio
async def test_linear_source_reads_issue_body_lazily(client: AsyncClient, monkeypatch):
    """Reading an issue renders its body — including the description — fetched
    live from Linear. The identifier is readable even without a prior sync."""
    from backend.integrations.linear import indexer as linear_indexer
    from backend.services import linear_api_service

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await _create_linear_source(ws, owner_id)

    async def fake_token(user_id, provider):
        return "tok"

    async def fake_fetch_issue(identifier, token):
        assert identifier == "FER-199"
        return linear_api_service.LinearIssue(
            issue_id="uuid-1",
            identifier="FER-199",
            title="Make Linear a real source",
            url="https://linear.app/ferganalabs/issue/FER-199",
            status="In Progress",
            assignee_name="Henry",
            team_key="FER",
            team_name="Fergana",
            project_name="Sources",
            updated_at=None,
            description="Stash should let agents view Linear issues.",
        )

    monkeypatch.setattr(linear_indexer, "get_valid_token", fake_token)
    monkeypatch.setattr(linear_api_service, "fetch_issue", fake_fetch_issue)

    doc = await source_service.read_document(src, "FER-199")

    assert doc["path"] == "FER-199"
    assert doc["kind"] == "issue"
    assert "Make Linear a real source" in doc["content"]
    assert "Status: In Progress" in doc["content"]
    assert "Stash should let agents view Linear issues." in doc["content"]


@pytest.mark.asyncio
async def test_linear_federated_search_returns_issue_hits(client: AsyncClient, monkeypatch):
    """Search is federated live to Linear's native search; hits are keyed by the
    index path (the ref the agent can then read)."""
    from backend.integrations.linear import indexer as linear_indexer
    from backend.services import linear_api_service

    api_key, owner_id = await _register(client)
    ws = await _user_scope(client, api_key)
    src = await _create_linear_source(ws, owner_id)

    async def fake_token(user_id, provider):
        return "tok"

    async def fake_search_issues(token, term, first=25):
        assert term == "real source"
        return [{"identifier": "FER-199", "title": "Make Linear a real source"}]

    monkeypatch.setattr(linear_indexer, "get_valid_token", fake_token)
    monkeypatch.setattr(linear_api_service, "search_issues", fake_search_issues)

    results = await source_service.search_all(ws, owner_id, "real source", source=src["id"])

    assert any(r["ref"] == "FER/FER-00199" for r in results)
    hit = next(r for r in results if r["ref"] == "FER/FER-00199")
    assert hit["source"] == src["id"]
    assert hit["name"] == "FER-199 Make Linear a real source"


@pytest.mark.asyncio
async def test_connected_source_is_shareable_read_only(client: AsyncClient, pool):
    """A connected source can be shared (read). The recipient reads its content
    through Stash (delegated to the OWNER's token, never the token itself) and
    sees it listed; management/sync stay owner-only; unsharing revokes access."""
    from backend.services import share_service

    _, owner_id = await _register(client, "owner")
    _, friend_id = await _register(client, "friend")
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T-share",
        display_name="Shared Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(src["id"])

    # 'source' is a permitted share target now (would raise 400 before).
    await share_service.share_with_user_by_email(
        object_type="source",
        object_id=source_id,
        email="invitee@example.com",
        permission="read",
        owner_id=owner_id,
    )
    # Only the owner may share it.
    with pytest.raises(Exception):
        await share_service.share_with_user_by_email(
            object_type="source",
            object_id=source_id,
            email="invitee@example.com",
            permission="read",
            owner_id=friend_id,
        )

    # Before a share lands: friend can't read, list, or manage.
    assert await source_service.get_readable_source(source_id, friend_id) is None
    assert await source_service.list_connected_sources(friend_id) == []
    assert await source_service.get_owned_source(source_id, friend_id) is None

    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,'source',$2,'user',$3,'read',$1)",
        owner_id,
        source_id,
        friend_id,
    )

    # Now friend reads the source and sees it listed.
    shared = await source_service.get_readable_source(source_id, friend_id)
    assert shared is not None
    # Row keeps the real owner, so reads delegate to the OWNER's token...
    assert shared["owner_user_id"] == str(owner_id)
    # ...and the token is never part of the row handed to the recipient.
    assert not any("token" in key for key in shared)
    assert any(s["id"] == src["id"] for s in await source_service.list_connected_sources(friend_id))

    # Management and sync remain owner-only.
    assert await source_service.get_owned_source(source_id, friend_id) is None

    # Unshare → access revoked immediately.
    await pool.execute(
        "DELETE FROM shares WHERE object_type='source' AND object_id=$1 AND principal_id=$2",
        source_id,
        friend_id,
    )
    assert await source_service.get_readable_source(source_id, friend_id) is None
    assert await source_service.list_connected_sources(friend_id) == []


@pytest.mark.asyncio
async def test_shared_source_is_searchable_by_recipient(client: AsyncClient, pool):
    """A read-share lets the recipient FTS-search the source's copied content;
    a non-sharee gets nothing."""
    _, owner_id = await _register(client, "owner")
    _, friend_id = await _register(client, "friend")
    _, stranger_id = await _register(client, "stranger")
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T-search",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(src["id"])
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        owner_user_id=owner_id,
        path="#eng/1.ts",
        name="msg",
        kind="message",
        content="the postgres migration is blocked on review",
        extra={"channel_id": "C1", "channel_name": "eng", "ts": "1"},
    )

    # Before the share: recipient can't search it.
    assert (
        await source_service.search_documents(user_id=friend_id, query="postgres migration") == []
    )

    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,'source',$2,'user',$3,'read',$1)",
        owner_id,
        source_id,
        friend_id,
    )

    # Now the recipient's search finds the shared source's content.
    assert (
        len(await source_service.search_documents(user_id=friend_id, query="postgres migration"))
        == 1
    )
    # An unrelated user still finds nothing.
    assert (
        await source_service.search_documents(user_id=stranger_id, query="postgres migration") == []
    )


@pytest.mark.asyncio
async def test_delegated_read_is_audited_to_the_source_owner(client: AsyncClient, pool):
    """When a recipient reads a shared source, the audit trail lands in the
    OWNER's log (owner_user_id = source owner) with the recipient as the actor —
    so the owner can see who read what they shared, not just their own reads."""
    _, owner_id = await _register(client, "owner")
    _, friend_id = await _register(client, "friend")
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T-audit",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(src["id"])
    await source_service.upsert_content_document(
        table="slack_messages",
        source_id=source_id,
        owner_user_id=owner_id,
        path="#eng/1.ts",
        name="msg",
        kind="message",
        content="the postgres migration is blocked on review",
        extra={"channel_id": "C1", "channel_name": "eng", "ts": "1"},
    )
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,'source',$2,'user',$3,'read',$1)",
        owner_id,
        source_id,
        friend_id,
    )

    # The recipient reads the shared source (routers pass current_user as both
    # the owner and viewer arg — the recipient is acting in their own request).
    await source_service.source_entries(friend_id, friend_id, str(source_id))

    row = await pool.fetchrow(
        "SELECT owner_user_id, actor_user_id, target_id FROM security_audit_events "
        "WHERE action = 'source.entries_listed' AND target_id = $1",
        str(source_id),
    )
    assert row is not None
    # Attributed to the data owner, actioned by the recipient.
    assert str(row["owner_user_id"]) == str(owner_id)
    assert str(row["actor_user_id"]) == str(friend_id)


@pytest.mark.asyncio
async def test_folder_share_does_not_grant_source_access(client: AsyncClient, pool):
    """Sources have no container: a folder share must NOT cascade into read
    access to a source. Only a direct source share grants it."""
    _, owner_id = await _register(client, "owner")
    _, friend_id = await _register(client, "friend")
    folder = await pool.fetchval(
        "INSERT INTO folders (owner_user_id, name, created_by) VALUES ($1, 'docs', $1) RETURNING id",
        owner_id,
    )
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,'folder',$2,'user',$3,'read',$1)",
        owner_id,
        folder,
        friend_id,
    )
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T-nocascade",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(src["id"])
    # Folder share grants the friend nothing on the source.
    assert await source_service.get_readable_source(source_id, friend_id) is None
    assert await source_service.list_connected_sources(friend_id) == []

    # A direct source share does grant it.
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,'source',$2,'user',$3,'read',$1)",
        owner_id,
        source_id,
        friend_id,
    )
    assert await source_service.get_readable_source(source_id, friend_id) is not None


@pytest.mark.asyncio
async def test_source_recipient_cannot_reshare_or_share_write(client: AsyncClient, pool):
    """A read-sharee cannot re-share the source (only the owner can), and a
    source can never be shared above read."""
    from backend.services import share_service

    _, owner_id = await _register(client, "owner")
    _, friend_id = await _register(client, "friend")
    src = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T-reshare",
        display_name="Slack",
        settings={"allowed_channel_ids": ["C1"]},
    )
    source_id = UUID(src["id"])
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,'source',$2,'user',$3,'read',$1)",
        owner_id,
        source_id,
        friend_id,
    )

    # The recipient can read it but cannot re-share it onward.
    assert await source_service.get_readable_source(source_id, friend_id) is not None
    with pytest.raises(Exception):
        await share_service.share_with_user_by_email(
            object_type="source",
            object_id=source_id,
            email="third@example.com",
            permission="read",
            owner_id=friend_id,
        )
    # Even the owner cannot grant above read on a source.
    with pytest.raises(Exception):
        await share_service.share_with_user_by_email(
            object_type="source",
            object_id=source_id,
            email="third@example.com",
            permission="write",
            owner_id=owner_id,
        )
