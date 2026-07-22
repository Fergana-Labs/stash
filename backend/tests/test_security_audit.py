import hashlib
import json
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import security_audit_service, source_service

from .conftest import unique_name


def test_hash_value_is_keyed_not_plain_sha256():
    """Audited values are often low-entropy (emails, IPv4s). A plain SHA-256
    can be reversed offline by hashing guesses, so redaction must be keyed."""
    assert security_audit_service.hash_value(None) is None
    assert (
        security_audit_service.hash_value("127.0.0.1") != hashlib.sha256(b"127.0.0.1").hexdigest()
    )


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


def _scope_for_user(user_id: UUID) -> UUID:
    """The scope id is just the user's id; there is no separate scope row."""
    return user_id


@pytest.mark.asyncio
async def test_security_events_are_isolated_per_user(
    client: AsyncClient,
):
    """Security events live only in the caller's own /me scope. A stranger
    reading /me/security-events sees their own (empty) log, never another
    user's events — there is no route to read someone else's audit trail."""
    owner_key, owner_id = await _register(client, "audit_owner")

    # Generate an auditable event in the owner's scope (the read itself is logged).
    owner_resp = await client.get("/api/v1/me/security-events", headers=_auth(owner_key))

    stranger_key, _ = await _register(client, "audit_stranger")
    stranger_resp = await client.get(
        "/api/v1/me/security-events",
        headers=_auth(stranger_key),
    )

    assert owner_resp.status_code == 200
    assert stranger_resp.status_code == 200

    owner_events = (
        await client.get("/api/v1/me/security-events", headers=_auth(owner_key))
    ).json()["events"]
    stranger_events = stranger_resp.json()["events"]

    assert any(event["actor_user_id"] == str(owner_id) for event in owner_events)
    assert all(event["actor_user_id"] != str(owner_id) for event in stranger_events)


@pytest.mark.asyncio
async def test_security_event_reads_are_audited_with_hashed_filters(
    client: AsyncClient,
):
    owner_key, owner_id = await _register(client, "audit_reader_owner")
    sensitive_filter = "source.document_read token=secret-token customer transcript"

    filtered_read = await client.get(
        "/api/v1/me/security-events",
        params={"action": sensitive_filter, "limit": 5},
        headers=_auth(owner_key),
    )
    unfiltered_read = await client.get(
        "/api/v1/me/security-events",
        headers=_auth(owner_key),
    )

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

    assert read_event["actor_user_id"] == str(owner_id)
    assert read_event["target_type"] == "security_audit_log"
    assert read_event["metadata"] == {"action_filter_hash": filter_hash, "limit": 5}


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
    headers = _auth(owner_key)

    page_name = "Webflow board escalation plan"
    page_content = "confidential Webflow security escalation notes"
    page_resp = await client.post(
        "/api/v1/me/pages/new",
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
        "/api/v1/me/security-events",
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
    headers = _auth(owner_key)

    page_name = "Webflow confidential partner plan"
    page_content = "private Webflow integration launch narrative"
    page_resp = await client.post(
        "/api/v1/me/pages/new",
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
        "/api/v1/me/security-events",
        headers=headers,
    )

    assert invited.status_code == 200
    assert invited.json() == {"ok": True, "email": recipient_email}
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
    headers = _auth(owner_key)

    page_name = "Webflow revoked partner plan"
    page_content = "private Webflow revocation launch narrative"
    page_resp = await client.post(
        "/api/v1/me/pages/new",
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
        "/api/v1/me/security-events",
        headers=headers,
    )

    assert invited.status_code == 200
    assert invited.json() == {"ok": True, "email": recipient_email}
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
async def test_source_access_audit_uses_hashes_not_sensitive_values(client: AsyncClient):
    api_key, user_id = await _register(client)
    scope = _scope_for_user(user_id)

    added = await client.post(
        "/api/v1/me/sources",
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
        owner_user_id=scope,
        path=ref,
        name="secret-launch-plan.md",
        content="secret launch plan",
    )

    search = await client.get(
        "/api/v1/me/sources/search",
        params={"q": query, "source": str(source_id)},
        headers=_auth(api_key),
    )
    doc = await client.get(
        f"/api/v1/me/sources/{source_id}/doc",
        params={"ref": ref},
        headers=_auth(api_key),
    )
    assert search.status_code == 200
    assert doc.status_code == 200

    events_resp = await client.get(
        "/api/v1/me/security-events",
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
async def test_lazy_source_read_failure_redacts_provider_error_and_audits_hashes(
    client: AsyncClient,
    monkeypatch,
):
    from backend.integrations.jira import indexer

    api_key, user_id = await _register(client, "audit_lazy_read")
    scope = _scope_for_user(user_id)
    headers = _auth(api_key)
    ref = "PROJ-9"
    external_ref = "cloud-1:PROJ-9"
    captured_logs = []

    async def fail_fetch(owner_user_id, provider_ref):
        raise RuntimeError(
            f"token=secret-token external_ref={provider_ref} customer transcript body"
        )

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(indexer, "fetch_jira_content", fail_fetch)
    monkeypatch.setattr(source_service.logger, "warning", capture_warning)

    added = await client.post(
        "/api/v1/me/sources",
        json={
            "source_type": "jira_project",
            "external_ref": "cloud-1:PROJ",
            "display_name": "Webflow confidential Jira",
        },
        headers=headers,
    )
    assert added.status_code == 200
    source_id = UUID(added.json()["id"])
    await source_service.upsert_index_row(
        table="jira_documents",
        source_id=source_id,
        owner_user_id=scope,
        path=ref,
        name="PROJ-9: confidential launch bug",
        kind="issue",
        external_ref=external_ref,
    )

    doc = await client.get(
        f"/api/v1/me/sources/{source_id}/doc",
        params={"ref": ref},
        headers=headers,
    )
    events_resp = await client.get(
        "/api/v1/me/security-events",
        headers=headers,
    )

    assert doc.status_code == 200
    assert doc.json() == {
        "path": ref,
        "name": "PROJ-9: confidential launch bug",
        "kind": "issue",
        "content": "",
        "error": "source document fetch failed",
    }
    response_json = json.dumps(doc.json())
    assert "secret-token" not in response_json
    assert external_ref not in response_json
    assert "customer transcript body" not in response_json
    assert captured_logs == [
        (
            "source document fetch failed source=%s source_type=%s exception_type=%s",
            (str(source_id), "jira_project", "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert external_ref not in str(captured_logs)
    assert "customer transcript body" not in str(captured_logs)
    assert events_resp.status_code == 200

    events = events_resp.json()["events"]
    event_json = json.dumps(events)
    assert ref not in event_json
    assert external_ref not in event_json
    assert "secret-token" not in event_json
    assert "customer transcript body" not in event_json
    assert "Webflow confidential Jira" not in event_json
    assert "confidential launch bug" not in event_json

    read_event = next(event for event in events if event["action"] == "source.document_read")
    assert read_event["target_id"] == str(source_id)
    assert read_event["provider"] == "jira"
    assert read_event["source_type"] == "jira_project"
    assert read_event["metadata"] == {"ref_hash": security_audit_service.hash_value(ref)}


@pytest.mark.asyncio
async def test_history_fetch_failure_audit_redacts_provider_error_and_filters(
    client: AsyncClient,
    monkeypatch,
):
    from backend.integrations.slack import indexer as slack_indexer

    api_key, owner_id = await _register(client, "audit_history")
    scope = _scope_for_user(owner_id)
    headers = _auth(api_key)
    sensitive_since = "2026-01-01T00:00:00Z"
    sensitive_until = "2026-02-01T00:00:00Z"
    source = await source_service.create_source(
        owner_user_id=scope,
        source_type="slack",
        external_ref="T_SECRET",
        display_name="Webflow confidential Slack",
        settings={"allowed_channel_ids": ["C_SECRET"]},
    )
    captured_logs = []

    async def fail_fetch(source, since, until, limit):
        raise RuntimeError(
            f"token=secret-token channel=C_SECRET Webflow transcript {sensitive_since}"
        )

    def capture_warning(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(slack_indexer, "fetch_history", fail_fetch)
    monkeypatch.setattr(source_service.logger, "warning", capture_warning)

    fetched = await client.post(
        f"/api/v1/me/sources/{source['id']}/history",
        json={"since": sensitive_since, "until": sensitive_until, "limit": 77},
        headers=headers,
    )
    events_resp = await client.get(
        "/api/v1/me/security-events",
        headers=headers,
    )

    assert fetched.status_code == 200
    assert fetched.json() == {"error": "source history fetch failed"}
    assert captured_logs == [
        (
            "source history fetch failed source=%s source_type=%s exception_type=%s",
            (source["id"], "slack", "RuntimeError"),
        )
    ]
    assert events_resp.status_code == 200

    events = events_resp.json()["events"]
    event_json = json.dumps(events)
    assert sensitive_since not in event_json
    assert sensitive_until not in event_json
    assert "secret-token" not in event_json
    assert "C_SECRET" not in event_json
    assert "T_SECRET" not in event_json
    assert "Webflow confidential Slack" not in event_json
    assert "Webflow transcript" not in event_json
    assert "secret-token" not in str(captured_logs)
    assert "C_SECRET" not in str(captured_logs)

    history_event = next(event for event in events if event["action"] == "source.history_fetched")
    assert history_event["target_id"] == source["id"]
    assert history_event["provider"] == "slack"
    assert history_event["source_type"] == "slack"
    assert history_event["metadata"] == {
        "since_hash": security_audit_service.hash_value(sensitive_since),
        "until_hash": security_audit_service.hash_value(sensitive_until),
        "limit": 77,
        "fetched": None,
        "error": True,
    }


@pytest.mark.asyncio
async def test_source_snapshot_audit_uses_hashes_not_sensitive_values(client: AsyncClient):
    api_key, user_id = await _register(client, "audit_snapshot")
    scope = _scope_for_user(user_id)
    headers = _auth(api_key)

    added = await client.post(
        "/api/v1/me/sources",
        json={
            "source_type": "github_repo",
            "external_ref": "webflow/confidential-sales",
            "display_name": "webflow/confidential-sales",
        },
        headers=headers,
    )
    assert added.status_code == 200
    source_id = UUID(added.json()["id"])
    ref = "docs/private-webflow-pricing.md"
    await source_service.upsert_content_document(
        table="github_documents",
        source_id=source_id,
        owner_user_id=scope,
        path=ref,
        name="private-webflow-pricing.md",
        content="Webflow confidential pricing notes",
    )
    folder = await client.post(
        "/api/v1/me/folders",
        json={"name": "Snapshot bundle", "is_skill": True},
        headers=headers,
    )
    assert folder.status_code == 201
    skill_md = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": "SKILL.md",
            "folder_id": folder.json()["id"],
            "content": (
                "---\nname: Snapshot bundle\ndescription: Preserve source snapshots.\n---\n"
            ),
        },
        headers=headers,
    )
    assert skill_md.status_code == 201
    skill = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder.json()["id"]},
        headers=headers,
    )
    assert skill.status_code == 201
    skill_id = skill.json()["id"]

    snap = await client.post(
        f"/api/v1/me/skills/{skill_id}/snapshot-source",
        json={"source_id": str(source_id), "path": ref},
        headers=headers,
    )
    events_resp = await client.get(
        "/api/v1/me/security-events",
        headers=headers,
    )

    assert snap.status_code == 201
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    event_json = json.dumps(events)
    assert "webflow/confidential-sales" not in event_json
    assert ref not in event_json
    assert "private-webflow-pricing.md" not in event_json
    assert "Webflow confidential pricing notes" not in event_json

    snapshot_event = next(
        event for event in events if event["action"] == "source.document_snapshotted"
    )
    assert snapshot_event["target_id"] == str(source_id)
    assert snapshot_event["provider"] == "github"
    assert snapshot_event["source_type"] == "github_repo"
    assert snapshot_event["metadata"] == {
        "ref_hash": security_audit_service.hash_value(ref),
        "skill_id": skill_id,
    }


@pytest.mark.asyncio
async def test_source_reads_outside_the_rest_api_are_audited(client: AsyncClient):
    """Agent tools call source_service directly — the audit trail must cover
    that front door too, not just the REST endpoints, or a prompt-injected
    agent could exfiltrate source content without leaving a trace."""
    api_key, user_id = await _register(client, "audit_agent")
    scope = _scope_for_user(user_id)

    added = await client.post(
        "/api/v1/me/sources",
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
        owner_user_id=scope,
        path="docs/launch.md",
        name="launch.md",
        content="secret launch plan",
    )

    results = await source_service.search_all(
        scope, user_id, "secret launch", source=str(source_id)
    )
    source_ok, doc = await source_service.source_document(
        scope, user_id, str(source_id), "docs/launch.md"
    )
    assert results
    assert source_ok and doc is not None

    events_resp = await client.get(
        "/api/v1/me/security-events",
        headers=_auth(api_key),
    )
    events = events_resp.json()["events"]
    search_event = next(event for event in events if event["action"] == "source.searched")
    read_event = next(event for event in events if event["action"] == "source.document_read")
    assert search_event["target_id"] == str(source_id)
    assert read_event["target_id"] == str(source_id)


@pytest.mark.asyncio
async def test_integration_disconnect_audits_source_purge(
    client: AsyncClient,
    monkeypatch,
):
    from backend.integrations import router as integrations_router

    api_key, owner_id = await _register(client, "audit_disconnect")
    scope = _scope_for_user(owner_id)
    source = await source_service.create_source(
        owner_user_id=scope,
        source_type="slack",
        external_ref="T123",
        display_name="Webflow Slack",
        settings={"allowed_channel_ids": ["C123"]},
    )

    async def fake_revoke_stored(user_id, provider):
        assert user_id == owner_id
        assert provider == "slack"

    monkeypatch.setattr(integrations_router.storage, "revoke_stored", fake_revoke_stored)

    # Data deletion happens only on the explicit delete_data path, and the
    # audit trail must record each purged source.
    disconnected = await client.post(
        "/api/v1/integrations/slack/disconnect",
        headers=_auth(api_key),
        json={"delete_data": True},
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["sources"] == 1

    events_resp = await client.get(
        "/api/v1/me/security-events",
        headers=_auth(api_key),
    )
    events = events_resp.json()["events"]
    purged = next(event for event in events if event["action"] == "source.purged")
    assert purged["target_id"] == source["id"]
    assert purged["provider"] == "slack"
    assert purged["source_type"] == "slack"
    assert purged["metadata"] == {"reason": "integration_disconnect"}
    # The credential revocation itself must be visible through the only read
    # surface (per-scope), not written as an unreadable NULL-scope row.
    disconnected_event = next(
        event for event in events if event["action"] == "integration.disconnected"
    )
    assert disconnected_event["provider"] == "slack"
    assert disconnected_event["metadata"] == {"sources": 1, "data_deleted": True}


@pytest.mark.asyncio
async def test_content_lifecycle_audit_records_delete_restore_and_purge(
    client: AsyncClient,
    _db_pool,
    monkeypatch,
):
    api_key, owner_id = await _register(client, "audit_content")
    scope = _scope_for_user(owner_id)
    headers = _auth(api_key)

    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Webflow Roadmap", "content": "secret launch plan"},
        headers=headers,
    )
    assert page.status_code == 201
    page_id = UUID(page.json()["id"])

    file_id = await _db_pool.fetchval(
        "INSERT INTO files "
        "(owner_user_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, 'text/plain', 12, $3, $4) RETURNING id",
        scope,
        "Webflow board notes.txt",
        "customer/webflow/file-secret-key",
        owner_id,
    )

    session = await client.post(
        "/api/v1/me/sessions",
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
        ("page", page_id, f"/api/v1/me/pages/{page_id}"),
        ("file", file_id, f"/api/v1/me/files/{file_id}"),
        ("session", session_row_id, f"/api/v1/me/sessions/{session_row_id}"),
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
        "/api/v1/me/security-events",
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


@pytest.mark.asyncio
async def test_batch_delete_and_restore_are_audited(client: AsyncClient):
    """Batch endpoints (and agent tools) call the services directly, skipping
    the single-item routers — the audit trail must cover that front door too,
    or a bulk deletion leaves no trace."""
    api_key, owner_id = await _register(client, "audit_batch")
    headers = _auth(api_key)

    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Bulk target", "content": "doomed"},
        headers=headers,
    )
    assert page.status_code == 201
    page_id = page.json()["id"]
    items = {"items": [{"object_type": "page", "object_id": page_id}]}

    deleted = await client.post("/api/v1/me/batch/delete", json=items, headers=headers)
    restored = await client.post("/api/v1/me/batch/restore", json=items, headers=headers)
    assert deleted.status_code == 200 and not deleted.json()["errors"]
    assert restored.status_code == 200 and not restored.json()["errors"]

    events_resp = await client.get(
        "/api/v1/me/security-events",
        headers=headers,
    )
    by_action = {event["action"]: event for event in events_resp.json()["events"]}
    for action in ["content.page_deleted", "content.page_restored"]:
        assert by_action[action]["target_id"] == page_id
        assert by_action[action]["actor_user_id"] == str(owner_id)
