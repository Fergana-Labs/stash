import json
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import security_audit_service, source_service

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, prefix: str = "audit") -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(prefix), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


async def _create_workspace(client: AsyncClient, api_key: str) -> UUID:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": unique_name("audit_ws")},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


@pytest.mark.asyncio
async def test_security_events_are_workspace_admin_only(
    client: AsyncClient,
    _db_pool,
):
    owner_key, _ = await _register(client, "audit_owner")
    editor_key, editor_id = await _register(client, "audit_editor")
    ws = await _create_workspace(client, owner_key)
    await _db_pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws,
        editor_id,
    )

    owner_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events", headers=_auth(owner_key)
    )
    editor_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=_auth(editor_key),
    )
    # Non-members get 404 like every other workspace route, so the endpoint
    # never confirms a workspace's existence to outsiders.
    stranger_key, _ = await _register(client, "audit_stranger")
    stranger_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=_auth(stranger_key),
    )

    assert owner_resp.status_code == 200
    assert editor_resp.status_code == 403
    assert stranger_resp.status_code == 404


@pytest.mark.asyncio
async def test_source_access_audit_uses_hashes_not_sensitive_values(client: AsyncClient):
    api_key, _ = await _register(client)
    ws = await _create_workspace(client, api_key)

    added = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "source_type": "github_repo",
            "external_ref": "webflow/confidential-roadmap",
            "display_name": "webflow/confidential-roadmap",
        },
        headers=_auth(api_key),
    )
    assert added.status_code == 200
    source_id = UUID(added.json()["id"])
    ref = "docs/secret-launch-plan.md"
    query = "secret launch"
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=source_id,
        workspace_id=ws,
        path=ref,
        name="secret-launch-plan.md",
        content="secret launch plan",
    )

    search = await client.get(
        f"/api/v1/workspaces/{ws}/sources/search",
        params={"q": query, "source": str(source_id)},
        headers=_auth(api_key),
    )
    doc = await client.get(
        f"/api/v1/workspaces/{ws}/sources/{source_id}/doc",
        params={"ref": ref},
        headers=_auth(api_key),
    )
    assert search.status_code == 200
    assert doc.status_code == 200

    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=_auth(api_key),
    )
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    event_json = json.dumps(events)
    assert query not in event_json
    assert ref not in event_json
    assert "secret launch plan" not in event_json

    search_event = next(event for event in events if event["action"] == "source.searched")
    read_event = next(event for event in events if event["action"] == "source.document_read")
    assert search_event["provider"] == "github"
    assert search_event["source_type"] == "github_repo"
    assert search_event["metadata"]["query_hash"] == security_audit_service.hash_value(query)
    assert search_event["metadata"]["result_count"] == 1
    assert read_event["metadata"]["ref_hash"] == security_audit_service.hash_value(ref)


@pytest.mark.asyncio
async def test_source_reads_outside_the_rest_api_are_audited(client: AsyncClient):
    """Agent tools call source_service directly — the audit trail must cover
    that front door too, not just the REST endpoints, or a prompt-injected
    agent could exfiltrate source content without leaving a trace."""
    api_key, user_id = await _register(client, "audit_agent")
    ws = await _create_workspace(client, api_key)

    added = await client.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "source_type": "github_repo",
            "external_ref": "webflow/confidential-roadmap",
            "display_name": "webflow/confidential-roadmap",
        },
        headers=_auth(api_key),
    )
    assert added.status_code == 200
    source_id = UUID(added.json()["id"])
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=source_id,
        workspace_id=ws,
        path="docs/launch.md",
        name="launch.md",
        content="secret launch plan",
    )

    results = await source_service.search_all(ws, user_id, "secret launch", source=str(source_id))
    source_ok, doc = await source_service.source_document(
        ws, user_id, str(source_id), "docs/launch.md"
    )
    assert results
    assert source_ok and doc is not None

    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=_auth(api_key),
    )
    events = events_resp.json()["events"]
    search_event = next(event for event in events if event["action"] == "source.searched")
    read_event = next(event for event in events if event["action"] == "source.document_read")
    assert search_event["target_id"] == str(source_id)
    assert read_event["target_id"] == str(source_id)


@pytest.mark.asyncio
async def test_integration_disconnect_audits_workspace_source_purge(
    client: AsyncClient,
    monkeypatch,
):
    from backend.integrations import router as integrations_router

    api_key, owner_id = await _register(client, "audit_disconnect")
    ws = await _create_workspace(client, api_key)
    source = await source_service.create_source(
        workspace_id=ws,
        owner_user_id=owner_id,
        source_type="slack",
        external_ref="T123",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["C123"]},
    )

    async def fake_revoke_stored(user_id, provider):
        assert user_id == owner_id
        assert provider == "slack"

    monkeypatch.setattr(integrations_router.storage, "revoke_stored", fake_revoke_stored)

    disconnected = await client.post(
        "/api/v1/integrations/slack/disconnect",
        headers=_auth(api_key),
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["removed_sources"] == 1

    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=_auth(api_key),
    )
    events = events_resp.json()["events"]
    deleted = next(event for event in events if event["action"] == "source.deleted")
    assert deleted["target_id"] == source["id"]
    assert deleted["provider"] == "slack"
    assert deleted["source_type"] == "slack"
    assert deleted["metadata"] == {"reason": "integration_disconnect"}
    # The credential revocation itself must be visible through the only read
    # surface (per-workspace), not written as an unreadable NULL-workspace row.
    disconnected_event = next(
        event for event in events if event["action"] == "integration.disconnected"
    )
    assert disconnected_event["provider"] == "slack"
    assert disconnected_event["metadata"] == {"removed_sources": 1}


@pytest.mark.asyncio
async def test_content_lifecycle_audit_records_delete_restore_and_purge(
    client: AsyncClient,
    _db_pool,
    monkeypatch,
):
    api_key, owner_id = await _register(client, "audit_content")
    ws = await _create_workspace(client, api_key)
    headers = _auth(api_key)

    page = await client.post(
        f"/api/v1/workspaces/{ws}/pages/new",
        json={"name": "Webflow Roadmap", "content": "secret launch plan"},
        headers=headers,
    )
    assert page.status_code == 201
    page_id = UUID(page.json()["id"])

    file_id = await _db_pool.fetchval(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, 'text/plain', 12, $3, $4) RETURNING id",
        ws,
        "Webflow board notes.txt",
        "customer/webflow/file-secret-key",
        owner_id,
    )

    session = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "webflow-session", "agent_name": "codex"},
        headers=headers,
    )
    assert session.status_code == 201
    session_row_id = UUID(session.json()["id"])
    await _db_pool.execute(
        "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, 'screenshots/home.png', $2, 32)",
        session_row_id,
        "customer/webflow/artifact-secret-key",
    )

    deleted_storage_keys: list[str] = []

    async def fake_delete_file(storage_key: str) -> None:
        deleted_storage_keys.append(storage_key)

    monkeypatch.setattr("backend.routers.files.storage_service.delete_file", fake_delete_file)
    monkeypatch.setattr("backend.routers.sessions.storage_service.delete_file", fake_delete_file)

    for object_type, object_id, base_url in [
        ("page", page_id, f"/api/v1/workspaces/{ws}/pages/{page_id}"),
        ("file", file_id, f"/api/v1/workspaces/{ws}/files/{file_id}"),
        ("session", session_row_id, f"/api/v1/workspaces/{ws}/sessions/{session_row_id}"),
    ]:
        deleted = await client.delete(base_url, headers=headers)
        restored = await client.post(f"{base_url}/restore", headers=headers)
        deleted_again = await client.delete(base_url, headers=headers)
        purged = await client.delete(f"{base_url}/purge", headers=headers)

        assert deleted.status_code == 204, object_type
        assert restored.status_code == 204, object_type
        assert deleted_again.status_code == 204, object_type
        assert purged.status_code == 204, object_type

    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=headers,
    )
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    by_action = {event["action"]: event for event in events}

    for object_type, object_id in [
        ("page", page_id),
        ("file", file_id),
        ("session", session_row_id),
    ]:
        for operation in ["deleted", "restored", "purged"]:
            action = f"content.{object_type}_{operation}"
            assert by_action[action]["target_type"] == object_type
            assert by_action[action]["target_id"] == str(object_id)
            assert by_action[action]["actor_user_id"] == str(owner_id)

    assert by_action["content.file_purged"]["metadata"] == {"storage_key_count": 1}
    assert by_action["content.session_purged"]["metadata"] == {"storage_key_count": 1}
    assert deleted_storage_keys == [
        "customer/webflow/file-secret-key",
        "customer/webflow/artifact-secret-key",
    ]

    event_json = json.dumps(events)
    assert "Webflow Roadmap" not in event_json
    assert "secret launch plan" not in event_json
    assert "Webflow board notes" not in event_json
    assert "file-secret-key" not in event_json
    assert "artifact-secret-key" not in event_json
