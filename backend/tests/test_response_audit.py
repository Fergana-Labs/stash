"""Returned developer payloads are durable evidence, never wiki material."""

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from backend.services import (
    response_audit_service,
    scoped_curation_service,
    skill_service,
    vfs_service,
)
from backend.services.vfs_service import VfsBudgetExceeded

from .test_developer_platform import _developer, _mint_workspace_key
from .test_permissions import _auth


async def developer_key(client):
    api_key, user, workspace = await _developer(client)
    key = await _mint_workspace_key(client, api_key, workspace)
    return key, api_key, user, workspace


async def audit_for(pool, response):
    request_id = UUID(response.headers["X-Stash-Request-Id"])
    row = await pool.fetchrow("SELECT * FROM read_response_audits WHERE id=$1", request_id)
    assert row is not None
    assert bytes(row["response_body"]) == response.content
    assert row["response_sha256"] == hashlib.sha256(response.content).hexdigest()
    assert row["status_code"] == response.status_code
    return row


@pytest.mark.asyncio
async def test_vfs_records_complete_response_and_authoritative_scope(client, pool, monkeypatch):
    key, _, _, workspace = await developer_key(client)
    # A payload beyond every transcript cap, with multibyte text and a NUL.
    payload = {
        "stdout": "part 🔧\n" * 10_000 + "\x00TAIL",
        "stderr": "",
        "exit_code": 0,
        "cwd": "/",
    }
    run = AsyncMock(return_value=payload)
    monkeypatch.setattr(vfs_service, "run_vfs_script", run)
    body = {"script": "cat /files/notes.md", "user_id": "org_actual", "cwd": "/"}
    headers = {
        **_auth(key),
        "X-Stash-User-Id": "org_wrong_header",
        "X-Stash-Session-Id": "conversation-1",
        "X-Stash-Workflow-Run-Id": "turn-2",
    }
    response = await client.post("/api/v1/me/vfs", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json() == payload
    row = await audit_for(pool, response)
    assert str(row["workspace_id"]) == workspace["id"]
    assert str(row["actor_user_id"]) == workspace["scope_user_id"]
    assert row["external_user_id"] == "org_actual"
    assert run.call_args.args[-1]["external_id"] == "org_actual"
    assert row["session_id"] == "conversation-1"
    assert row["workflow_run_id"] == "turn-2"
    assert row["request_data"] == body
    assert row["method"] == "POST" and row["path"] == "/api/v1/me/vfs"
    # Repeated calls remain distinguishable even when the session and script match.
    again = await client.post("/api/v1/me/vfs", headers=headers, json=body)
    assert again.headers["X-Stash-Request-Id"] != response.headers["X-Stash-Request-Id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [None, "brand_new_org"])
async def test_shared_and_new_org_reads_are_not_inferred_from_uploads(client, pool, user_id):
    key, _, _, _ = await developer_key(client)
    response = await client.post(
        "/api/v1/me/vfs", headers=_auth(key), json={"script": "ls /", "user_id": user_id}
    )
    assert response.status_code == 200, response.text
    row = await audit_for(pool, response)
    assert row["external_user_id"] == user_id
    assert row["session_id"] is None and row["workflow_run_id"] is None
    assert await pool.fetchval("SELECT count(*) FROM sessions") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "method", "payload"),
    [
        ("/api/v1/me/skills", "list_skills", [{"name": "Parts", "description": "Routing"}]),
        ("/api/v1/me/skills/Parts", "read_skill", {"body": "Private evidence"}),
        ("/api/v1/me/source-skills/upstream-id", "read_source_skill", {"body": "Source evidence"}),
        ("/api/v1/me/skills/missing", "read_skill", None),
        ("/api/v1/me/source-skills/missing", "read_source_skill", None),
    ],
)
async def test_skill_reads_record_scope_and_not_found(
    client, pool, monkeypatch, path, method, payload
):
    _, api_key, user, workspace = await developer_key(client)
    monkeypatch.setattr(skill_service, method, AsyncMock(return_value=payload))
    response = await client.get(
        path,
        headers={
            **_auth(api_key),
            "X-Stash-Scope": workspace["scope_user_id"],
            "X-Stash-User-Id": "org_parts",
            "X-Stash-Session-Id": "conversation-parts",
        },
    )
    assert response.status_code == (404 if payload is None else 200), response.text
    row = await audit_for(pool, response)
    assert str(row["workspace_id"]) == workspace["id"]
    assert str(row["actor_user_id"]) == user["id"]
    assert row["external_user_id"] == "org_parts"
    assert row["session_id"] == "conversation-parts"
    assert row["path"] == path


@pytest.mark.asyncio
async def test_expected_vfs_error_is_recorded(client, pool, monkeypatch):
    key, _, _, _ = await developer_key(client)
    monkeypatch.setattr(
        vfs_service, "run_vfs_script", AsyncMock(side_effect=VfsBudgetExceeded("too big"))
    )
    response = await client.post(
        "/api/v1/me/vfs", headers=_auth(key), json={"script": "ls /", "user_id": "org_parts"}
    )
    assert response.status_code == 413
    await audit_for(pool, response)


@pytest.mark.asyncio
async def test_failed_audit_never_releases_the_payload(client, pool, monkeypatch):
    key, _, _, _ = await developer_key(client)
    monkeypatch.setattr(
        skill_service, "read_skill", AsyncMock(return_value={"body": "SECRET_BODY"})
    )
    monkeypatch.setattr(
        response_audit_service,
        "get_pool",
        lambda: SimpleNamespace(
            execute=AsyncMock(side_effect=RuntimeError("SECRET_SQL_ARGUMENTS"))
        ),
    )
    response = await client.get("/api/v1/me/skills/Parts", headers=_auth(key))
    assert response.status_code == 503
    assert "SECRET" not in response.text
    assert "X-Stash-Request-Id" not in response.headers
    assert await pool.fetchval("SELECT count(*) FROM read_response_audits") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["", "x" * 129])
async def test_invalid_correlation_does_not_release_content(client, pool, monkeypatch, value):
    key, _, _, _ = await developer_key(client)
    monkeypatch.setattr(
        skill_service, "read_skill", AsyncMock(return_value={"body": "SECRET_BODY"})
    )
    response = await client.get(
        "/api/v1/me/skills/Parts", headers={**_auth(key), "X-Stash-Session-Id": value}
    )
    assert response.status_code == 400
    assert "SECRET_BODY" not in response.text
    assert await pool.fetchval("SELECT count(*) FROM read_response_audits") == 0


@pytest.mark.asyncio
async def test_personal_reads_are_not_copied_to_developer_journal(client, pool):
    _, api_key, _, _ = await developer_key(client)
    response = await client.get("/api/v1/me/skills", headers=_auth(api_key))
    assert response.status_code == 200
    assert "X-Stash-Request-Id" not in response.headers
    assert await pool.fetchval("SELECT count(*) FROM read_response_audits") == 0


@pytest.mark.asyncio
async def test_raw_audits_never_become_content_or_curator_inputs(client, pool, monkeypatch):
    key, _, _, workspace = await developer_key(client)
    sentinel = "AUDIT_ONLY_SECRET_95bf17"
    with monkeypatch.context() as patch:
        patch.setattr(skill_service, "read_skill", AsyncMock(return_value={"body": sentinel}))
        response = await client.get("/api/v1/me/skills/Parts", headers=_auth(key))
    await audit_for(pool, response)
    for table in ("history_events", "pages", "files", "security_audit_events"):
        # The names are a fixed list; inspect every field so metadata can't hide a copy.
        rows = await pool.fetch(f"SELECT row_to_json(t) AS data FROM {table} t")
        assert sentinel not in json.dumps([row["data"] for row in rows])
    vfs = await client.post(
        "/api/v1/me/vfs", headers=_auth(key), json={"script": f"grep -ri {sentinel} /"}
    )
    assert vfs.status_code == 200, vfs.text
    assert sentinel not in vfs.json()["stdout"]
    db_workspace = dict(
        await pool.fetchrow("SELECT * FROM workspaces WHERE id=$1", UUID(workspace["id"]))
    )
    scope = await scoped_curation_service.load_scope(
        db_workspace,
        "shared",
        db_workspace["external_wiki_folder_id"],
        [],
        "agent-curate-audit-test",
        None,
        datetime.now(UTC),
    )
    assert sentinel not in json.dumps(scope.documents)
