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

    assert owner_resp.status_code == 200
    assert editor_resp.status_code == 403


@pytest.mark.asyncio
async def test_security_event_reads_are_audited_with_hashed_filters(
    client: AsyncClient,
    _db_pool,
):
    owner_key, owner_id = await _register(client, "audit_reader_owner")
    editor_key, editor_id = await _register(client, "audit_reader_editor")
    ws = await _create_workspace(client, owner_key)
    await _db_pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws,
        editor_id,
    )
    sensitive_filter = "source.document_read token=secret-token customer transcript"

    denied = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        params={"action": sensitive_filter, "limit": 5},
        headers=_auth(editor_key),
    )
    filtered_read = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        params={"action": sensitive_filter, "limit": 5},
        headers=_auth(owner_key),
    )
    unfiltered_read = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=_auth(owner_key),
    )

    assert denied.status_code == 403
    assert filtered_read.status_code == 200
    assert unfiltered_read.status_code == 200

    events = unfiltered_read.json()["events"]
    event_json = json.dumps(events)
    assert sensitive_filter not in event_json
    assert "secret-token" not in event_json
    assert "customer transcript" not in event_json

    filter_hash = security_audit_service.hash_value(sensitive_filter)
    read_event = next(
        event
        for event in events
        if event["action"] == "security_audit.read"
        and event["metadata"]["action_filter_hash"] == filter_hash
    )
    denied_event = next(
        event for event in events if event["action"] == "security_audit.read_denied"
    )

    assert read_event["actor_user_id"] == str(owner_id)
    assert read_event["target_type"] == "security_audit_log"
    assert read_event["metadata"] == {"action_filter_hash": filter_hash, "limit": 5}
    assert denied_event["actor_user_id"] == str(editor_id)
    assert denied_event["target_type"] == "security_audit_log"
    assert denied_event["metadata"] == {
        "action_filter_hash": filter_hash,
        "limit": 5,
        "role": "editor",
    }


@pytest.mark.asyncio
async def test_cartridge_member_changes_are_audited_without_recipient_or_content(
    client: AsyncClient,
):
    owner_key, owner_id = await _register(client, "audit_stash_owner")
    recipient_name = unique_name("webflow_secret_recipient")
    recipient_display_name = "Webflow Secret Recipient"
    recipient_email = f"{recipient_name}@example.com"
    recipient_resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": recipient_name,
            "display_name": recipient_display_name,
            "email": recipient_email,
            "password": "securepassword1",
        },
    )
    assert recipient_resp.status_code == 201
    recipient_id = UUID(recipient_resp.json()["id"])
    ws = await _create_workspace(client, owner_key)
    headers = _auth(owner_key)

    page_name = "Webflow confidential launch notes"
    page_content = "secret pricing plan for Webflow"
    page_resp = await client.post(
        f"/api/v1/workspaces/{ws}/pages/new",
        json={"name": page_name, "content": page_content},
        headers=headers,
    )
    assert page_resp.status_code == 201

    stash_title = "Webflow managed product demo"
    stash_resp = await client.post(
        f"/api/v1/workspaces/{ws}/cartridges",
        json={
            "title": stash_title,
            "workspace_permission": "none",
            "public_permission": "none",
            "items": [{"object_type": "page", "object_id": page_resp.json()["id"]}],
        },
        headers=headers,
    )
    assert stash_resp.status_code == 201
    stash_id = UUID(stash_resp.json()["id"])

    granted = await client.post(
        f"/api/v1/cartridges/{stash_id}/members",
        json={"user_id": str(recipient_id), "permission": "read"},
        headers=headers,
    )
    removed = await client.delete(
        f"/api/v1/cartridges/{stash_id}/members/{recipient_id}",
        headers=headers,
    )
    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=headers,
    )

    assert granted.status_code == 201
    assert removed.status_code == 204
    assert events_resp.status_code == 200

    events = events_resp.json()["events"]
    granted_event = next(event for event in events if event["action"] == "cartridge.member_granted")
    removed_event = next(event for event in events if event["action"] == "cartridge.member_removed")
    recipient_hash = security_audit_service.hash_value(str(recipient_id))

    assert granted_event["actor_user_id"] == str(owner_id)
    assert granted_event["target_type"] == "cartridge"
    assert granted_event["target_id"] == str(stash_id)
    assert granted_event["metadata"] == {
        "permission": "read",
        "recipient_user_hash": recipient_hash,
    }
    assert removed_event["actor_user_id"] == str(owner_id)
    assert removed_event["target_type"] == "cartridge"
    assert removed_event["target_id"] == str(stash_id)
    assert removed_event["metadata"] == {"recipient_user_hash": recipient_hash}

    event_json = json.dumps(events)
    assert str(recipient_id) not in event_json
    assert recipient_name not in event_json
    assert recipient_display_name not in event_json
    assert recipient_email not in event_json
    assert stash_title not in event_json
    assert page_name not in event_json
    assert page_content not in event_json


@pytest.mark.asyncio
async def test_object_share_changes_are_audited_without_recipient_or_content(
    client: AsyncClient,
):
    owner_key, owner_id = await _register(client, "audit_share_owner")
    recipient_name = unique_name("webflow_share_recipient")
    recipient_display_name = "Webflow Share Recipient"
    recipient_email = f"{recipient_name}@example.com"
    recipient_resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": recipient_name,
            "display_name": recipient_display_name,
            "email": recipient_email,
            "password": "securepassword1",
        },
    )
    assert recipient_resp.status_code == 201
    recipient_id = UUID(recipient_resp.json()["id"])
    ws = await _create_workspace(client, owner_key)
    headers = _auth(owner_key)

    page_name = "Webflow board escalation plan"
    page_content = "confidential Webflow security escalation notes"
    page_resp = await client.post(
        f"/api/v1/workspaces/{ws}/pages/new",
        json={"name": page_name, "content": page_content},
        headers=headers,
    )
    assert page_resp.status_code == 201
    page_id = page_resp.json()["id"]

    granted = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": recipient_email.upper(),
            "permission": "write",
        },
        headers=headers,
    )
    revoked = await client.request(
        "DELETE",
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "principal_type": "user",
            "principal_id": str(recipient_id),
        },
        headers=headers,
    )
    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=headers,
    )

    assert granted.status_code == 200
    assert revoked.status_code == 200
    assert events_resp.status_code == 200

    events = events_resp.json()["events"]
    granted_event = next(event for event in events if event["action"] == "share.granted")
    revoked_event = next(event for event in events if event["action"] == "share.revoked")
    recipient_hash = security_audit_service.hash_value(str(recipient_id))

    assert granted_event["actor_user_id"] == str(owner_id)
    assert granted_event["target_type"] == "page"
    assert granted_event["target_id"] == page_id
    assert granted_event["metadata"] == {
        "permission": "write",
        "principal_type": "user",
        "recipient_user_hash": recipient_hash,
    }
    assert revoked_event["actor_user_id"] == str(owner_id)
    assert revoked_event["target_type"] == "page"
    assert revoked_event["target_id"] == page_id
    assert revoked_event["metadata"] == {
        "permission": "write",
        "principal_type": "user",
        "recipient_user_hash": recipient_hash,
    }

    event_json = json.dumps(events)
    assert str(recipient_id) not in event_json
    assert recipient_name not in event_json
    assert recipient_display_name not in event_json
    assert recipient_email not in event_json
    assert recipient_email.upper() not in event_json
    assert page_name not in event_json
    assert page_content not in event_json


@pytest.mark.asyncio
async def test_pending_share_invite_conversion_is_audited_without_email_or_content(
    client: AsyncClient,
):
    owner_key, owner_id = await _register(client, "audit_pending_share_owner")
    ws = await _create_workspace(client, owner_key)
    headers = _auth(owner_key)

    page_name = "Webflow confidential partner plan"
    page_content = "private Webflow integration launch narrative"
    page_resp = await client.post(
        f"/api/v1/workspaces/{ws}/pages/new",
        json={"name": page_name, "content": page_content},
        headers=headers,
    )
    assert page_resp.status_code == 201
    page_id = page_resp.json()["id"]

    recipient_name = unique_name("webflow_pending_recipient")
    recipient_display_name = "Webflow Pending Recipient"
    recipient_email = f"{recipient_name}@example.com"
    invited = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": recipient_email.upper(),
            "permission": "read",
        },
        headers=headers,
    )
    recipient_resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": recipient_name,
            "display_name": recipient_display_name,
            "email": recipient_email,
            "password": "securepassword1",
        },
    )
    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=headers,
    )

    assert invited.status_code == 200
    assert invited.json() == {"pending": True, "email": recipient_email}
    assert recipient_resp.status_code == 201
    assert events_resp.status_code == 200

    recipient_id = UUID(recipient_resp.json()["id"])
    events = events_resp.json()["events"]
    invited_event = next(event for event in events if event["action"] == "share.invited")
    converted_event = next(event for event in events if event["action"] == "share.invite_converted")
    email_hash = security_audit_service.hash_value(recipient_email)
    recipient_hash = security_audit_service.hash_value(str(recipient_id))

    assert invited_event["actor_user_id"] == str(owner_id)
    assert invited_event["target_type"] == "page"
    assert invited_event["target_id"] == page_id
    assert invited_event["metadata"] == {
        "permission": "read",
        "recipient_email_hash": email_hash,
    }
    assert converted_event["actor_user_id"] == str(owner_id)
    assert converted_event["target_type"] == "page"
    assert converted_event["target_id"] == page_id
    assert converted_event["metadata"] == {
        "permission": "read",
        "recipient_email_hash": email_hash,
        "recipient_user_hash": recipient_hash,
    }

    event_json = json.dumps(events)
    assert str(recipient_id) not in event_json
    assert recipient_name not in event_json
    assert recipient_display_name not in event_json
    assert recipient_email not in event_json
    assert recipient_email.upper() not in event_json
    assert page_name not in event_json
    assert page_content not in event_json


@pytest.mark.asyncio
async def test_pending_share_invite_revocation_is_audited_without_email_or_content(
    client: AsyncClient,
):
    owner_key, owner_id = await _register(client, "audit_pending_share_revoke_owner")
    ws = await _create_workspace(client, owner_key)
    headers = _auth(owner_key)

    page_name = "Webflow revoked partner plan"
    page_content = "private Webflow revocation launch narrative"
    page_resp = await client.post(
        f"/api/v1/workspaces/{ws}/pages/new",
        json={"name": page_name, "content": page_content},
        headers=headers,
    )
    assert page_resp.status_code == 201
    page_id = page_resp.json()["id"]

    recipient_name = unique_name("webflow_revoked_recipient")
    recipient_email = f"{recipient_name}@example.com"
    invited = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": recipient_email.upper(),
            "permission": "write",
        },
        headers=headers,
    )
    revoked = await client.request(
        "DELETE",
        "/api/v1/share/invite",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": recipient_email,
        },
        headers=headers,
    )
    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/security-events",
        headers=headers,
    )

    assert invited.status_code == 200
    assert invited.json() == {"pending": True, "email": recipient_email}
    assert revoked.status_code == 200
    assert events_resp.status_code == 200

    events = events_resp.json()["events"]
    revoked_event = next(event for event in events if event["action"] == "share.invite_revoked")
    email_hash = security_audit_service.hash_value(recipient_email)

    assert revoked_event["actor_user_id"] == str(owner_id)
    assert revoked_event["target_type"] == "page"
    assert revoked_event["target_id"] == page_id
    assert revoked_event["metadata"] == {
        "permission": "write",
        "recipient_email_hash": email_hash,
    }

    event_json = json.dumps(events)
    assert recipient_name not in event_json
    assert recipient_email not in event_json
    assert recipient_email.upper() not in event_json
    assert page_name not in event_json
    assert page_content not in event_json


@pytest.mark.asyncio
async def test_workspace_invite_and_membership_changes_are_audited_without_tokens_or_names(
    client: AsyncClient,
):
    owner_key, owner_id = await _register(client, "audit_workspace_owner")
    joiner_name = unique_name("webflow_workspace_joiner")
    joiner_display_name = "Webflow Workspace Joiner"
    joiner_email = f"{joiner_name}@example.com"
    joiner_resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": joiner_name,
            "display_name": joiner_display_name,
            "email": joiner_email,
            "password": "securepassword1",
        },
    )
    assert joiner_resp.status_code == 201
    joiner_key = joiner_resp.json()["api_key"]
    joiner_id = UUID(joiner_resp.json()["id"])
    workspace_name = "Webflow confidential access hub"
    workspace_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": workspace_name},
        headers=_auth(owner_key),
    )
    assert workspace_resp.status_code == 201
    workspace_id = UUID(workspace_resp.json()["id"])
    owner_headers = _auth(owner_key)

    first_invite = await client.post(
        f"/api/v1/workspaces/{workspace_id}/invite-tokens",
        json={"max_uses": 1, "ttl_days": 3},
        headers=owner_headers,
    )
    assert first_invite.status_code == 201
    first_invite_body = first_invite.json()
    redeemed = await client.post(
        "/api/v1/workspaces/redeem-invite",
        json={"token": first_invite_body["token"]},
        headers=_auth(joiner_key),
    )
    left = await client.post(
        f"/api/v1/workspaces/{workspace_id}/leave",
        headers=_auth(joiner_key),
    )
    second_invite = await client.post(
        f"/api/v1/workspaces/{workspace_id}/invite-tokens",
        json={"max_uses": 2, "ttl_days": 5},
        headers=owner_headers,
    )
    assert second_invite.status_code == 201
    second_invite_body = second_invite.json()
    revoked = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/invite-tokens/{second_invite_body['id']}",
        headers=owner_headers,
    )
    events_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/security-events",
        headers=owner_headers,
    )

    assert redeemed.status_code == 200
    assert left.status_code == 204
    assert revoked.status_code == 204
    assert events_resp.status_code == 200

    events = events_resp.json()["events"]
    first_invite_hash = security_audit_service.hash_value(first_invite_body["id"])
    second_invite_hash = security_audit_service.hash_value(second_invite_body["id"])
    joiner_hash = security_audit_service.hash_value(str(joiner_id))
    created_events = {
        event["metadata"]["invite_token_id_hash"]: event
        for event in events
        if event["action"] == "workspace.invite_token_created"
    }
    joined_event = next(event for event in events if event["action"] == "workspace.member_joined")
    left_event = next(event for event in events if event["action"] == "workspace.member_left")
    revoked_event = next(
        event for event in events if event["action"] == "workspace.invite_token_revoked"
    )

    assert created_events[first_invite_hash]["actor_user_id"] == str(owner_id)
    assert created_events[first_invite_hash]["target_type"] == "workspace"
    assert created_events[first_invite_hash]["target_id"] == str(workspace_id)
    assert created_events[first_invite_hash]["metadata"] == {
        "invite_token_id_hash": first_invite_hash,
        "max_uses": 1,
        "ttl_days": 3,
    }
    assert created_events[second_invite_hash]["metadata"] == {
        "invite_token_id_hash": second_invite_hash,
        "max_uses": 2,
        "ttl_days": 5,
    }
    assert joined_event["actor_user_id"] == str(joiner_id)
    assert joined_event["target_type"] == "workspace"
    assert joined_event["target_id"] == str(workspace_id)
    assert joined_event["metadata"] == {
        "member_user_hash": joiner_hash,
        "role": "editor",
        "method": "invite_token",
    }
    assert left_event["actor_user_id"] == str(joiner_id)
    assert left_event["metadata"] == {"member_user_hash": joiner_hash}
    assert revoked_event["actor_user_id"] == str(owner_id)
    assert revoked_event["metadata"] == {"invite_token_id_hash": second_invite_hash}

    event_json = json.dumps(events)
    assert first_invite_body["token"] not in event_json
    assert first_invite_body["id"] not in event_json
    assert second_invite_body["token"] not in event_json
    assert second_invite_body["id"] not in event_json
    assert joiner_name not in event_json
    assert joiner_display_name not in event_json
    assert joiner_email not in event_json
    assert workspace_name not in event_json


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
