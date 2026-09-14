"""An opted-out customer's data must be unavailable, even to a disobedient curator."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from pydantic import ValidationError

from backend.services import end_user_service, source_service
from backend.services import scoped_curation_service as curation

from .conftest import unique_name
from .test_developer_platform import _developer, _event, _mint_workspace_key, _push
from .test_permissions import _auth


@pytest_asyncio.fixture
async def dataset(client, pool):
    api_key, _, workspace = await _developer(client)
    key = await _mint_workspace_key(client, api_key, workspace)
    events = [
        _event("private-job", "private", "Protected customer"),
        _event("public-job", "public", "Participating customer"),
    ]
    events[0]["content"] = "SECRET_TRANSCRIPT: protected engine serial and service history"
    events[1]["content"] = "ALLOWED_TRANSCRIPT: reusable parts identification lesson"
    await _push(client, key, events)
    owner = UUID(workspace["scope_user_id"])
    users = {
        u["external_id"]: dict(u)
        for u in await pool.fetch(
            "SELECT * FROM end_users WHERE workspace_id=$1", UUID(workspace["id"])
        )
    }
    await end_user_service.update_end_user(users["private"]["id"], share_wiki=False)
    workspace = dict(
        await pool.fetchrow("SELECT * FROM workspaces WHERE id=$1", UUID(workspace["id"]))
    )
    pages = {}
    for name, user in users.items():
        pages[name] = await pool.fetchval(
            "INSERT INTO pages (owner_user_id,folder_id,name,content_markdown,created_by) "
            "VALUES ($1,$2,$3,$4,$1) RETURNING id",
            owner,
            user["wiki_folder_id"],
            f"{name} notes",
            f"{name.upper()}_WIKI_SECRET",
        )
    shared = await pool.fetchval(
        "INSERT INTO pages (owner_user_id,folder_id,name,content_markdown,created_by) "
        "VALUES ($1,$2,'Index','ALLOWED_SHARED_KNOWLEDGE',$1) RETURNING id",
        owner,
        workspace["external_wiki_folder_id"],
    )
    private_file = await pool.fetchval(
        "INSERT INTO files (owner_user_id,end_user_id,name,content_type,size_bytes,storage_key,"
        "uploaded_by,extracted_text,extraction_status) "
        "VALUES ($1,$2,'Protected upload','text/plain',12,'test-scoped-upload',$1,'SECRET_FILE','done') "
        "RETURNING id",
        owner,
        users["private"]["id"],
    )
    source = await source_service.create_source(
        owner_user_id=owner,
        source_type="google_drive_folder",
        external_ref=unique_name("drive"),
        display_name="Protected drive",
        end_user_id=users["private"]["id"],
    )
    source_doc = await pool.fetchval(
        "INSERT INTO drive_documents (owner_user_id,source_id,path,name,kind,content,extraction_status) "
        "VALUES ($1,$2,'secret','Protected source','file','SECRET_SOURCE','done') RETURNING id",
        owner,
        UUID(source["id"]),
    )
    return SimpleNamespace(
        workspace=workspace,
        owner=owner,
        users=users,
        pages=pages,
        shared=shared,
        private_file=private_file,
        source_doc=source_doc,
        key=key,
        api_key=api_key,
    )


async def scope(data, purpose, user="public"):
    if purpose == "shared":
        destination = data.workspace["external_wiki_folder_id"]
        users = [data.users["public"]["id"]]
    else:
        destination = data.users[user]["wiki_folder_id"]
        users = [data.users[user]["id"]]
    return await curation.load_scope(
        data.workspace,
        purpose,
        destination,
        users,
        "agent-curate-security-test",
        None,
        datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_shared_curator_cannot_discover_or_guess_protected_material(dataset):
    shared = await scope(dataset, "shared")
    corpus = json.dumps(shared.documents)
    for secret in ("SECRET_TRANSCRIPT", "PRIVATE_WIKI_SECRET", "SECRET_FILE", "SECRET_SOURCE"):
        assert secret not in corpus
    assert "ALLOWED_TRANSCRIPT" in corpus and "ALLOWED_SHARED_KNOWLEDGE" in corpus
    # Private wikis aren't shared inputs, including those of participating users.
    assert "PUBLIC_WIKI_SECRET" not in corpus
    for document_id in (
        f"page:{dataset.pages['private']}",
        "session:private-job",
        f"file:{dataset.private_file}",
        f"source:{dataset.source_doc}",
    ):
        with pytest.raises(PermissionError):
            await shared.tool("read_document", {"document_id": document_id})
    with pytest.raises(PermissionError):
        await shared.tool("bash", {"command": "stash changes --json"})


@pytest.mark.asyncio
async def test_private_curator_reads_own_material_and_shared_knowledge_only(dataset):
    private = await scope(dataset, "private", "private")
    corpus = json.dumps(private.documents)
    assert all(
        s in corpus
        for s in ("SECRET_TRANSCRIPT", "PRIVATE_WIKI_SECRET", "SECRET_FILE", "SECRET_SOURCE")
    )
    assert "ALLOWED_SHARED_KNOWLEDGE" in corpus
    assert "ALLOWED_TRANSCRIPT" not in corpus and "PUBLIC_WIKI_SECRET" not in corpus
    for page in (dataset.shared, dataset.pages["public"]):
        with pytest.raises(PermissionError):
            await private.tool(
                "write_page", {"page_id": str(page), "title": "Leak", "content": "SECRET"}
            )
    with pytest.raises(ValidationError):
        await private.tool(
            "write_page",
            {
                "page_id": None,
                "title": "Leak",
                "content": "SECRET",
                "folder_id": str(dataset.workspace["external_wiki_folder_id"]),
            },
        )


@pytest.mark.asyncio
async def test_model_can_write_only_its_fixed_destination(dataset, pool):
    private = await scope(dataset, "private", "private")
    result = await private.tool(
        "write_page", {"page_id": None, "title": "Maintenance", "content": "SECRET_RECORD"}
    )
    page = await pool.fetchrow("SELECT * FROM pages WHERE id=$1", UUID(result["page_id"]))
    assert page["folder_id"] == dataset.users["private"]["wiki_folder_id"]
    assert page["end_user_id"] == dataset.users["private"]["id"]
    assert page["public_permission"] == "none"
    await private.tool(
        "write_page",
        {"page_id": str(page["id"]), "title": "Maintenance", "content": "Updated SECRET_RECORD"},
    )
    with pytest.raises(PermissionError):
        shared = await scope(dataset, "shared")
        await shared.tool(
            "write_page", {"page_id": str(page["id"]), "title": "Public", "content": "SECRET"}
        )


@pytest.mark.asyncio
async def test_revocation_invalidates_inflight_read_write_and_old_shared_corpus(
    dataset, client, pool
):
    shared = await scope(dataset, "shared")
    old_root = dataset.workspace["external_wiki_folder_id"]
    await end_user_service.update_end_user(dataset.users["public"]["id"], share_wiki=False)
    for tool, args in (
        ("read_document", {"document_id": f"page:{dataset.shared}"}),
        ("write_page", {"page_id": None, "title": "Leaked", "content": "ALLOWED_TRANSCRIPT"}),
    ):
        with pytest.raises(PermissionError, match="permissions changed"):
            await shared.tool(tool, args)
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "ALLOWED_SHARED_KNOWLEDGE"
    )
    assert (
        await pool.fetchval(
            "SELECT external_wiki_folder_id FROM workspaces WHERE id=$1", dataset.workspace["id"]
        )
        != old_root
    )
    for user_id in (None, "private", "public", "new-customer"):
        r = await client.post(
            "/api/v1/me/vfs",
            headers=_auth(dataset.key),
            json={"script": "grep -r ALLOWED_SHARED_KNOWLEDGE /memory /files", "user_id": user_id},
        )
        assert r.status_code == 200
        assert "ALLOWED_SHARED_KNOWLEDGE" not in r.json()["stdout"]


@pytest.mark.asyncio
async def test_shared_input_excludes_replayed_retrieval_results(dataset, client):
    event = _event("public-job", "public", "Participating customer")
    event.update(
        event_type="tool_result", tool_name="search_stash", content="OLD_COPIED_PRIVATE_DATA"
    )
    await _push(client, dataset.key, [event])
    assert "OLD_COPIED_PRIVATE_DATA" not in json.dumps((await scope(dataset, "shared")).documents)


@pytest.mark.asyncio
async def test_shared_reads_recheck_consent_even_without_a_generation_change(dataset, pool):
    shared = await scope(dataset, "shared")
    await pool.execute(
        "UPDATE end_users SET share_wiki=false WHERE id=$1", dataset.users["public"]["id"]
    )
    with pytest.raises(PermissionError, match="no longer shared"):
        await shared.tool("search_documents", {"query": ""})


@pytest.mark.asyncio
async def test_separate_model_contexts_and_no_sprite_execution(
    dataset, pool, monkeypatch, sprite_exec
):
    from backend.services import agent_service, sprite_agent_service

    calls = []

    async def fake_run(scope, instructions):
        calls.append((scope.purpose, json.dumps(scope.documents)))
        return "Completed this isolated wiki."

    async def forbidden(*args, **kwargs):
        pytest.fail("Developer curator must never run in a credential-bearing sprite")

    monkeypatch.setattr(curation, "run_scope", fake_run)
    monkeypatch.setattr(sprite_agent_service, "run_chat", forbidden)
    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="external")
    agent["curated_through"] = None
    await sprite_agent_service.run_scheduled(agent, "security-test")
    assert len([p for p, _ in calls if p == "private"]) == 2
    assert len([p for p, _ in calls if p == "shared"]) == 1
    assert all("SECRET_TRANSCRIPT" not in text for p, text in calls if p == "shared")
    assert any("SECRET_TRANSCRIPT" in text for p, text in calls if p == "private")
    assert sprite_exec.calls == [] and sprite_exec.writes == []


@pytest.mark.asyncio
async def test_internal_developer_curator_cannot_read_customer_inputs(
    dataset, pool, monkeypatch, sprite_exec
):
    from backend.services import agent_service, sprite_agent_service

    calls = []

    async def fake_run(scope, instructions):
        calls.append(scope)
        assert "SECRET_TRANSCRIPT" not in json.dumps(scope.documents)
        assert "ALLOWED_TRANSCRIPT" not in json.dumps(scope.documents)
        return "No private developer changes."

    monkeypatch.setattr(curation, "run_scope", fake_run)
    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="internal")
    agent["curated_through"] = None
    await sprite_agent_service.run_scheduled(agent, "security-test")
    assert len(calls) == 1 and calls[0].purpose == "internal"
    assert sprite_exec.calls == [] and sprite_exec.writes == []
    with pytest.raises(PermissionError):
        await sprite_agent_service.build_scheduled_turn(agent, "security-test")


@pytest.mark.asyncio
async def test_optout_during_model_request_blocks_publication(
    dataset, pool, monkeypatch, sprite_exec
):
    from anthropic.types import ToolUseBlock

    shared = await scope(dataset, "shared")

    async def create(**kwargs):
        await end_user_service.update_end_user(dataset.users["public"]["id"], share_wiki=False)
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[
                ToolUseBlock(
                    type="tool_use",
                    id="write",
                    name="write_page",
                    input={
                        "page_id": None,
                        "title": "Leaked after revocation",
                        "content": "ALLOWED_TRANSCRIPT",
                    },
                )
            ],
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    with pytest.raises(PermissionError, match="permissions changed"):
        await curation.run_scope(shared, None)
    assert (
        await pool.fetchval("SELECT count(*) FROM pages WHERE name='Leaked after revocation'") == 0
    )


@pytest.mark.asyncio
async def test_native_model_loop_uses_fresh_messages_and_restricted_tools(
    dataset, monkeypatch, sprite_exec
):
    from anthropic.types import TextBlock, ToolUseBlock

    private = await scope(dataset, "private", "private")
    shared = await scope(dataset, "shared")
    requests = []

    async def create(**kwargs):
        requests.append(json.loads(json.dumps(kwargs)))
        assert {t["name"] for t in kwargs["tools"]} == {
            "search_documents",
            "read_document",
            "write_page",
        }
        if len(requests) == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id="read",
                        name="read_document",
                        input={"document_id": "session:private-job"},
                    )
                ],
            )
        return SimpleNamespace(
            stop_reason="end_turn", content=[TextBlock(type="text", text="Done.")]
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    await curation.run_scope(private, None)
    await curation.run_scope(shared, None)
    assert "SECRET_TRANSCRIPT" in json.dumps(requests[1]["messages"])
    assert "SECRET_TRANSCRIPT" not in json.dumps(requests[2])
    assert len(requests[2]["messages"]) == 1


@pytest.mark.asyncio
async def test_missing_backend_key_fails_without_dispatch(dataset, client, monkeypatch):
    from backend.tasks import agent_schedules

    monkeypatch.setattr(curation.settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(
        agent_schedules.run_curator_now, "delay", lambda *a, **k: pytest.fail("Not configured")
    )
    r = await client.post(
        "/api/v1/me/developer/curator/run",
        headers={**_auth(dataset.api_key), "X-Stash-Scope": str(dataset.owner)},
    )
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


@pytest.mark.asyncio
async def test_developer_prompt_preview_describes_scoped_runner(dataset):
    from backend.routers.agents import get_agent_prompt
    from backend.services import agent_service

    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="external")
    preview = await get_agent_prompt(UUID(agent["id"]), current_user={"id": dataset.owner})
    assert "separate" in preview["system_prompt"].lower()
    assert "stash changes" not in preview["system_prompt"]


@pytest.mark.asyncio
async def test_failed_shared_run_does_not_report_success_or_advance_watermark(
    dataset, pool, monkeypatch, sprite_exec
):
    from backend.services import agent_service, sprite_agent_service

    async def fail_shared(scope, instructions):
        if scope.purpose == "shared":
            raise PermissionError("Publication denied")
        return "Private curation completed."

    monkeypatch.setattr(curation, "run_scope", fail_shared)
    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="external")
    agent["curated_through"] = None
    before = await pool.fetchval(
        "SELECT curated_through FROM agents WHERE id=$1", UUID(agent["id"])
    )
    with pytest.raises(PermissionError):
        await sprite_agent_service.run_scheduled(agent, "failed-test")
    assert (
        await pool.fetchval("SELECT curated_through FROM agents WHERE id=$1", UUID(agent["id"]))
        == before
    )
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM history_events WHERE session_id LIKE 'agent-curate-%' AND event_type='assistant_message'"
        )
        == 0
    )
