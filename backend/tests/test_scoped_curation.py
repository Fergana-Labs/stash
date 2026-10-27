"""An opted-out customer's data must be unavailable, even to a disobedient curator."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from pydantic import ValidationError

from backend.services import end_user_service, source_service
from backend.services import scoped_curation_service as curation

from .conftest import unique_name
from .shared_wiki_helpers import approve_fixture_pages
from .test_developer_platform import _developer, _event, _mint_workspace_key, _push
from .test_permissions import _auth


@pytest_asyncio.fixture
async def dataset(client, pool, monkeypatch):
    async def approve(**kwargs):
        return curation.shared_wiki_privacy.PrivacyReview(approved=True, issues=[])

    monkeypatch.setattr(curation.shared_wiki_privacy.llm, "complete_structured", approve)
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
    async with curation.get_pool().acquire() as conn:
        await approve_fixture_pages(conn, data.workspace)
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
        str(dataset.pages["private"]),
        "session:private-job",
        f"file:{dataset.private_file}",
        f"source:{dataset.source_doc}",
    ):
        denied = await shared.tool("read_document", {"document_id": document_id})
        assert "unavailable" in denied["error"] and "content" not in denied
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
        denied = await private.tool(
            "write_page", {"page_id": str(page), "title": "Leak", "content": "SECRET"}
        )
        assert "outside" in denied["error"]
    denied = await private.tool(
        "write_page",
        {
            "page_id": None,
            "title": "Leak",
            "content": "SECRET",
            "folder_id": str(dataset.workspace["external_wiki_folder_id"]),
        },
    )
    assert "Invalid tool arguments" in denied["error"]
    assert denied["fields"][0]["field"] == "folder_id"


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
    shared = await scope(dataset, "shared")
    denied = await shared.tool(
        "write_page", {"page_id": str(page["id"]), "title": "Public", "content": "SECRET"}
    )
    assert "outside" in denied["error"]


@pytest.mark.asyncio
async def test_revocation_invalidates_inflight_read_write_and_old_shared_corpus(
    dataset, client, pool
):
    shared = await scope(dataset, "shared")
    old_root = dataset.workspace["external_wiki_folder_id"]
    await end_user_service.update_end_user(dataset.users["public"]["id"], share_wiki=False)
    for tool, args in (
        ("read_document", {"document_id": str(dataset.shared)}),
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
async def test_discovered_page_id_can_be_read_and_updated_without_translation(dataset):
    shared = await scope(dataset, "shared")
    listing = await shared.tool("search_documents", {"query": "Index"})
    page_id = listing["documents"][0]["id"]
    original = await shared.tool("read_document", {"document_id": page_id})
    assert original["content"] == "ALLOWED_SHARED_KNOWLEDGE"
    result = await shared.tool(
        "write_page",
        {"page_id": page_id, "title": "Index", "content": "Updated permitted knowledge."},
    )
    assert result["page_id"] == page_id
    updated = await shared.tool("read_document", {"document_id": page_id})
    assert updated["content"] == "Updated permitted knowledge."


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
    all_started = asyncio.Event()

    async def fake_run(scope, instructions):
        calls.append((scope.purpose, json.dumps(scope.documents)))
        if len(calls) == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=1)
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
            "edit_page",
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
async def test_denied_lookup_is_an_explicit_tool_error_without_protected_content(
    dataset, monkeypatch, sprite_exec
):
    from anthropic.types import TextBlock, ToolUseBlock

    shared = await scope(dataset, "shared")
    requests = []

    async def create(**kwargs):
        requests.append(json.loads(json.dumps(kwargs)))
        if len(requests) == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id="denied",
                        name="read_document",
                        input={"document_id": "session:private-job"},
                    )
                ],
            )
        return SimpleNamespace(
            stop_reason="end_turn", content=[TextBlock(type="text", text="No update needed.")]
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    await curation.run_scope(shared, None)
    result = requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "unavailable" in result["content"]
    assert "SECRET_TRANSCRIPT" not in json.dumps(requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["edit_page", "write_page"])
async def test_model_corrects_malformed_page_id_without_aborting_scope(
    dataset, pool, monkeypatch, sprite_exec, tool_name
):
    from anthropic.types import TextBlock, ToolUseBlock

    shared = await scope(dataset, "shared")
    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            result = kwargs["messages"][-1]["content"][0]
            assert result["is_error"]
            assert "page_id" in result["content"] and "UUID" in result["content"]
            assert await pool.fetchval("SELECT count(*) FROM page_edits") == 0
        if calls <= 2:
            arguments = (
                {"old_text": "ALLOWED_SHARED_KNOWLEDGE", "new_text": "Corrected knowledge"}
                if tool_name == "edit_page"
                else {"title": "Index", "content": "Corrected knowledge"}
            )
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id=f"edit-{calls}",
                        name=tool_name,
                        input={
                            "page_id": "d792f10c-d6ac40fe-a73d-f5a2e493a3df"
                            if calls == 1
                            else str(dataset.shared),
                            **arguments,
                        },
                    )
                ],
            )
        assert not kwargs["messages"][-1]["content"][0]["is_error"]
        return SimpleNamespace(
            stop_reason="end_turn", content=[TextBlock(type="text", text="Done.")]
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    assert await curation.run_scope(shared, None) == "Done."
    assert calls == 3
    assert await pool.fetchval("SELECT count(*) FROM page_edits") == 1
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "Corrected knowledge"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "arguments", "field"),
    [
        ("search_documents", {"query": "", "offset": -1}, "offset"),
        ("read_document", {}, "document_id"),
        ("edit_page", {"page_id": "bad", "old_text": "old", "new_text": "new"}, "page_id"),
        ("write_page", {"page_id": None, "title": "", "content": "SECRET"}, "title"),
    ],
)
async def test_invalid_tool_arguments_return_errors_without_writes(
    dataset, pool, name, arguments, field
):
    shared = await scope(dataset, "shared")
    result = await shared.tool(name, arguments)
    assert "Invalid tool arguments" in result["error"]
    assert any(error["field"] == field for error in result["fields"])
    assert "SECRET" not in json.dumps(result)
    assert await pool.fetchval("SELECT count(*) FROM page_edits") == 0
    assert "documents" in await shared.tool("search_documents", {"query": ""})


@pytest.mark.asyncio
async def test_invalid_tool_arguments_do_not_mask_revoked_permissions(dataset):
    shared = await scope(dataset, "shared")
    await end_user_service.update_end_user(dataset.users["public"]["id"], share_wiki=False)
    with pytest.raises(PermissionError):
        await shared.tool("edit_page", {"page_id": "bad"})


@pytest.mark.asyncio
async def test_tool_argument_recovery_does_not_swallow_internal_validation_failure(
    dataset, monkeypatch
):
    shared = await scope(dataset, "shared")

    async def broken_write(*args, **kwargs):
        curation.Search.model_validate({"query": []})

    monkeypatch.setattr(shared, "write", broken_write)
    with pytest.raises(ValidationError):
        await shared.tool("write_page", {"page_id": None, "title": "Valid", "content": "Valid"})


@pytest.mark.asyncio
async def test_repeated_invalid_arguments_still_exhaust_the_turn_limit(
    dataset, monkeypatch, sprite_exec
):
    from anthropic.types import ToolUseBlock

    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[
                ToolUseBlock(type="tool_use", id=f"bad-{calls}", name="read_document", input={})
            ],
        )

    monkeypatch.setattr(curation, "_MAX_TURNS", 2)
    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    with pytest.raises(RuntimeError, match="exhausted its tool turns"):
        await curation.run_scope(await scope(dataset, "shared"), None)
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_text", [None, " \n\t"])
async def test_empty_completion_continues_without_replaying_saved_write(
    dataset, pool, monkeypatch, sprite_exec, empty_text
):
    from anthropic.types import TextBlock, ToolUseBlock

    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id="saved-edit",
                        name="edit_page",
                        input={
                            "page_id": str(dataset.shared),
                            "old_text": "ALLOWED_SHARED_KNOWLEDGE",
                            "new_text": "Saved knowledge",
                        },
                    )
                ],
            )
        if calls == 2:
            assert not kwargs["messages"][-1]["content"][0]["is_error"]
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[] if empty_text is None else [TextBlock(type="text", text=empty_text)],
            )
        assert calls == 3
        messages = kwargs["messages"]
        assert messages[-1]["role"] == "user"
        assert "summary" in messages[-1]["content"]
        assert messages[-2]["content"][0]["tool_use_id"] == "saved-edit"
        assert all(message["content"] for message in messages)
        assert await pool.fetchval("SELECT count(*) FROM page_edits") == 1
        return SimpleNamespace(
            stop_reason="end_turn", content=[TextBlock(type="text", text="Updated wiki.")]
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    assert await curation.run_scope(await scope(dataset, "shared"), None) == "Updated wiki."
    assert calls == 3
    assert await pool.fetchval("SELECT count(*) FROM page_edits") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_limit", [1, 40])
async def test_empty_completion_retry_is_bounded(dataset, monkeypatch, sprite_exec, turn_limit):
    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(stop_reason="end_turn", content=[])

    monkeypatch.setattr(curation, "_MAX_TURNS", turn_limit)
    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    error = RuntimeError if turn_limit == 1 else ValueError
    with pytest.raises(error, match="exhausted its tool turns|no completion summary"):
        await curation.run_scope(await scope(dataset, "shared"), None)
    assert calls == min(turn_limit, 2)


@pytest.mark.asyncio
async def test_empty_completion_does_not_retry_after_optout(dataset, monkeypatch, sprite_exec):
    shared = await scope(dataset, "shared")
    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        await end_user_service.update_end_user(dataset.users["public"]["id"], share_wiki=False)
        return SimpleNamespace(stop_reason="end_turn", content=[])

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    with pytest.raises(PermissionError, match="permissions changed"):
        await curation.run_scope(shared, None)
    assert calls == 1


@pytest.mark.asyncio
async def test_truncated_response_cannot_execute_partial_page_writes(
    dataset, pool, monkeypatch, sprite_exec
):
    from anthropic.types import ToolUseBlock

    async def create(**kwargs):
        return SimpleNamespace(
            stop_reason="max_tokens",
            content=[
                ToolUseBlock(
                    type="tool_use",
                    id="truncated",
                    name="write_page",
                    input={"page_id": None, "title": "Partial page", "content": "Incomplete"},
                )
            ],
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    with pytest.raises(RuntimeError, match="max_tokens"):
        await curation.run_scope(await scope(dataset, "shared"), None)
    assert await pool.fetchval("SELECT count(*) FROM pages WHERE name='Partial page'") == 0


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

    private_started = set()
    private_cancelled = set()
    all_private_started = asyncio.Event()

    async def fail_shared(scope, instructions):
        if scope.purpose == "shared":
            await asyncio.wait_for(all_private_started.wait(), timeout=1)
            raise PermissionError("Publication denied")
        private_started.add(scope.destination)
        if len(private_started) == 2:
            all_private_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            private_cancelled.add(scope.destination)
            raise

    monkeypatch.setattr(curation, "run_scope", fail_shared)
    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="external")
    agent["curated_through"] = None
    before = await pool.fetchval(
        "SELECT curated_through FROM agents WHERE id=$1", UUID(agent["id"])
    )
    with pytest.raises(ExceptionGroup) as failure:
        await sprite_agent_service.run_scheduled(agent, "failed-test")
    assert any(isinstance(exc, PermissionError) for exc in failure.value.exceptions)
    assert private_cancelled == private_started and len(private_cancelled) == 2
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


@pytest.mark.asyncio
async def test_scoped_run_timeout_preserves_progress_and_releases_lock(
    dataset, pool, monkeypatch, sprite_exec
):
    from backend.services import agent_service, sprite_agent_service
    from backend.tasks.agent_schedules import _run_curator_now

    async def stuck(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(curation, "run_scope", stuck)
    monkeypatch.setattr(sprite_agent_service.settings, "AGENT_TURN_TIMEOUT_SECONDS", 0.05)
    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="external")
    before = await pool.fetchval(
        "SELECT curated_through FROM agents WHERE id=$1", UUID(agent["id"])
    )
    with pytest.raises(RuntimeError, match="run time limit"):
        await _run_curator_now(UUID(agent["id"]), metered=False)
    row = await pool.fetchrow(
        "SELECT curated_through,last_run_outcome,last_run_error FROM agents WHERE id=$1",
        UUID(agent["id"]),
    )
    assert row["curated_through"] == before
    assert row["last_run_outcome"] == "failed" and "run time limit" in row["last_run_error"]
    assert sprite_exec.redis.data == {}


@pytest.mark.asyncio
async def test_duplicate_create_returns_existing_page_without_overwriting_it(dataset, pool):
    shared = await scope(dataset, "shared")
    result = await shared.tool(
        "write_page", {"page_id": None, "title": "Index", "content": "Accidental replacement"}
    )
    assert "already exists" in result["error"]
    assert result["page_id"] == str(dataset.shared)
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "ALLOWED_SHARED_KNOWLEDGE"
    )
    assert (
        await pool.fetchval("SELECT count(*) FROM page_edits WHERE page_id=$1", dataset.shared) == 0
    )
    # The conflict rolls back to a savepoint; the same scope can read and
    # deliberately update the existing page instead of aborting the run.
    doc = await shared.tool("read_document", {"document_id": result["page_id"]})
    assert doc["content"] == "ALLOWED_SHARED_KNOWLEDGE"
    await shared.tool(
        "write_page", {"page_id": result["page_id"], "title": "Index", "content": "Reviewed update"}
    )
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "Reviewed update"
    )


@pytest.mark.asyncio
async def test_conflicting_rename_preserves_both_pages(dataset, pool):
    shared = await scope(dataset, "shared")
    other = await shared.tool(
        "write_page", {"page_id": None, "title": "Other", "content": "Original other page"}
    )
    conflict = await shared.tool(
        "write_page", {"page_id": other["page_id"], "title": "Index", "content": "Bad rename"}
    )
    assert conflict["page_id"] == str(dataset.shared) and "error" in conflict
    assert (
        await pool.fetchval(
            "SELECT content_markdown FROM pages WHERE id=$1", UUID(other["page_id"])
        )
        == "Original other page"
    )
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "ALLOWED_SHARED_KNOWLEDGE"
    )


@pytest.mark.asyncio
async def test_duplicate_title_lookup_never_returns_another_wikis_page(dataset, pool):
    shared = await scope(dataset, "shared")
    result = await shared.tool(
        "write_page", {"page_id": None, "title": "private notes", "content": "Public knowledge"}
    )
    assert "error" not in result
    assert result["page_id"] != str(dataset.pages["private"])
    assert "PRIVATE_WIKI_SECRET" not in json.dumps(shared.documents)


@pytest.mark.asyncio
async def test_successful_scoped_batches_queue_and_drain_without_skipping_private_input(
    dataset, pool, monkeypatch, sprite_exec
):
    from backend.services import agent_service, billing_service, curation_service
    from backend.tasks import agent_schedules

    async def entitled(_):
        return True

    monkeypatch.setattr(billing_service, "is_pro", entitled)
    await pool.execute(
        "INSERT INTO history_events (owner_user_id,created_by,agent_name,event_type,session_id,content) "
        "VALUES ($1,$1,'heavi-chat','user_message','public-job','Another permitted lesson')",
        dataset.owner,
    )
    # DB and runner clocks may differ; make this a fixed historical backlog.
    inputs = await pool.fetch(
        "SELECT id FROM history_events WHERE owner_user_id=$1 ORDER BY created_at,id", dataset.owner
    )
    base = datetime.now(UTC) - timedelta(minutes=1)
    for index, event in enumerate(inputs):
        await pool.execute(
            "UPDATE history_events SET created_at=$2 WHERE id=$1",
            event["id"],
            base + timedelta(milliseconds=index),
        )
    monkeypatch.setattr(curation_service, "_MAX_EVENTS", 2)
    seen = []

    async def fake_run(scope, instructions):
        text = json.dumps(scope.documents)
        if scope.purpose == "shared":
            assert "SECRET_TRANSCRIPT" not in text
        seen.append(text)
        return "Reviewed this batch."

    monkeypatch.setattr(curation, "run_scope", fake_run)
    queued = []
    monkeypatch.setattr(
        agent_schedules.run_curator_now, "apply_async", lambda **kw: queued.append(kw)
    )
    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="external")
    await pool.execute("UPDATE agents SET curated_through=NULL WHERE id=$1", UUID(agent["id"]))
    # A small event limit must split the real input rather than moving the
    # watermark over unseen data. Re-run only the tasks actually dispatched.
    await agent_schedules._run_curator_now(UUID(agent["id"]), metered=False)
    passes = 1
    while queued:
        task = queued.pop(0)
        await agent_schedules._run_curator_now(UUID(task["args"][0]), **task["kwargs"])
        passes += 1
        assert passes <= agent_schedules.CURATOR_CATCHUP_PASSES
    current = await agent_service.get_agent_by_id(UUID(agent["id"]))
    latest_input = await pool.fetchval(
        "SELECT max(created_at) FROM history_events WHERE owner_user_id=$1 "
        "AND session_id NOT LIKE 'agent-curate-%'",
        dataset.owner,
    )
    assert passes >= 2
    assert current["curated_through"] >= latest_input
    assert current["last_run_outcome"] == "ran"
    assert current["month_run_count"] == 0
    assert any("SECRET_TRANSCRIPT" in text for text in seen)


@pytest.mark.asyncio
async def test_truncated_write_is_discarded_before_one_complete_retry(
    dataset, pool, monkeypatch, sprite_exec
):
    from anthropic.types import TextBlock, ToolUseBlock

    requests = []

    async def create(**kwargs):
        requests.append(json.loads(json.dumps(kwargs)))
        if len(requests) <= 2:
            truncated = len(requests) == 1
            return SimpleNamespace(
                stop_reason="max_tokens" if truncated else "tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id=f"write-{len(requests)}",
                        name="write_page",
                        input={
                            "page_id": None,
                            "title": "Partial page" if truncated else "Concise page",
                            "content": "Discard this partial output"
                            if truncated
                            else "Complete permitted lesson.",
                        },
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
    assert await curation.run_scope(await scope(dataset, "shared"), None) == "Done."
    assert await pool.fetchval("SELECT count(*) FROM pages WHERE name='Partial page'") == 0
    assert await pool.fetchval("SELECT count(*) FROM pages WHERE name='Concise page'") == 1
    assert len(requests) == 3
    assert "Discard this partial output" not in json.dumps(requests[1:])
    assert "Partial page" in requests[1]["messages"][-1]["content"]
    retry_tools = {tool["name"]: tool for tool in requests[1]["tools"]}
    assert retry_tools["write_page"]["input_schema"]["properties"]["content"]["maxLength"] == 4000
    assert retry_tools["edit_page"]["input_schema"]["properties"]["new_text"]["maxLength"] == 2000


@pytest.mark.asyncio
async def test_rename_collision_resolves_in_the_pages_subfolder_not_the_wiki_root(dataset, pool):
    folder = await pool.fetchval(
        "INSERT INTO folders (owner_user_id,created_by,name,parent_folder_id) "
        "VALUES ($1,$1,'Nested',$2) RETURNING id",
        dataset.owner,
        dataset.workspace["external_wiki_folder_id"],
    )
    pages = {}
    for name in ("Index", "Other"):
        pages[name] = await pool.fetchval(
            "INSERT INTO pages (owner_user_id,folder_id,name,content_markdown,created_by) "
            "VALUES ($1,$2,$3,$4,$1) RETURNING id",
            dataset.owner,
            folder,
            name,
            "Nested " + name,
        )
    shared = await scope(dataset, "shared")
    result = await shared.tool(
        "write_page", {"page_id": str(pages["Other"]), "title": "Index", "content": "Bad rename"}
    )
    assert result["page_id"] == str(pages["Index"]) and "error" in result
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "ALLOWED_SHARED_KNOWLEDGE"
    )
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", pages["Other"])
        == "Nested Other"
    )


@pytest.mark.asyncio
async def test_duplicate_title_does_not_refresh_a_revision_changed_by_a_human(dataset, pool):
    shared = await scope(dataset, "shared")
    original = dict(shared.writable[dataset.shared])
    await pool.execute(
        "UPDATE pages SET content_markdown='Human edit',content_hash='human-revision' WHERE id=$1",
        dataset.shared,
    )
    with pytest.raises(ValueError, match="changed during curation"):
        await shared.tool(
            "write_page", {"page_id": None, "title": "Index", "content": "Stale replacement"}
        )
    assert shared.writable[dataset.shared] == original
    # Nor can a subsequent ordinary update reuse a silently refreshed hash.
    with pytest.raises(ValueError, match="changed during curation"):
        await shared.tool(
            "write_page",
            {"page_id": str(dataset.shared), "title": "Index", "content": "Stale replacement"},
        )
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "Human edit"
    )


@pytest.mark.asyncio
async def test_small_edit_preserves_large_page_and_tracks_revision(dataset, pool):
    text = "Existing detail.\n" * 3000 + "Unique ending."
    await pool.execute("UPDATE pages SET content_markdown=$2 WHERE id=$1", dataset.shared, text)
    shared = await scope(dataset, "shared")
    for old, new in [
        ("Unique ending.", "Unique ending.\nNew lesson."),
        ("New lesson.", "Verified new lesson."),
    ]:
        await shared.tool(
            "edit_page",
            {
                "page_id": str(dataset.shared),
                "old_text": old,
                "new_text": new,
            },
        )
    assert await pool.fetchval(
        "SELECT content_markdown FROM pages WHERE id=$1", dataset.shared
    ) == (text + "\nVerified new lesson.")
    assert (
        await pool.fetchval("SELECT count(*) FROM page_edits WHERE page_id=$1", dataset.shared) == 2
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("old,new", [("absent", "new"), ("repeat", "new"), ("repeat repeat", "")])
async def test_ambiguous_missing_or_destructive_edit_does_not_write(dataset, pool, old, new):
    await pool.execute(
        "UPDATE pages SET content_markdown='repeat repeat' WHERE id=$1", dataset.shared
    )
    shared = await scope(dataset, "shared")
    result = await shared.tool(
        "edit_page",
        {
            "page_id": str(dataset.shared),
            "old_text": old,
            "new_text": new,
        },
    )
    assert "error" in result
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "repeat repeat"
    )


@pytest.mark.asyncio
async def test_edit_cannot_overwrite_a_concurrent_human_edit(dataset, pool):
    shared = await scope(dataset, "shared")
    original = shared.documents[str(dataset.shared)]["content"]
    await pool.execute(
        "UPDATE pages SET content_markdown='Human edit',content_hash='new-revision' WHERE id=$1",
        dataset.shared,
    )
    with pytest.raises(ValueError, match="changed during curation"):
        await shared.tool(
            "edit_page",
            {
                "page_id": str(dataset.shared),
                "old_text": original,
                "new_text": "Agent edit",
            },
        )
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "Human edit"
    )


@pytest.mark.asyncio
async def test_edit_enforces_writable_scope_and_permission_revocation(dataset):
    private = await scope(dataset, "private")
    denied = await private.tool(
        "edit_page",
        {
            "page_id": str(dataset.shared),
            "old_text": "ALLOWED_SHARED_KNOWLEDGE",
            "new_text": "Bad edit",
        },
    )
    assert "outside" in denied["error"]
    shared = await scope(dataset, "shared")
    await end_user_service.update_end_user(dataset.users["public"]["id"], share_wiki=False)
    with pytest.raises(PermissionError):
        await shared.tool(
            "edit_page",
            {
                "page_id": str(dataset.shared),
                "old_text": "ALLOWED_SHARED_KNOWLEDGE",
                "new_text": "Bad edit",
            },
        )


@pytest.mark.asyncio
async def test_initial_prompt_identifies_delta_inputs_not_existing_wiki(
    dataset, monkeypatch, sprite_exec
):
    from anthropic.types import TextBlock

    requests = []

    async def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn", content=[TextBlock(type="text", text="No update needed.")]
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    shared = await scope(dataset, "shared")
    await curation.run_scope(shared, None)
    manifest = requests[0]["messages"][0]["content"]
    assert "session:public-job" in manifest
    assert "session:private-job" not in manifest
    assert "ALLOWED_SHARED_KNOWLEDGE" not in manifest
    assert requests[0]["max_tokens"] == 4096
    shared.documents = {
        key: doc
        for key, doc in shared.documents.items()
        if not key.startswith(("session:", "file:", "source:"))
    }
    assert "No new input" in await curation.run_scope(shared, None)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_text_edit_preserves_a_concurrent_title_only_change(dataset, pool):
    shared = await scope(dataset, "shared")
    await pool.execute("UPDATE pages SET name='Human title' WHERE id=$1", dataset.shared)
    await shared.tool(
        "edit_page",
        {
            "page_id": str(dataset.shared),
            "old_text": "ALLOWED_SHARED_KNOWLEDGE",
            "new_text": "Updated knowledge",
        },
    )
    row = await pool.fetchrow("SELECT name,content_markdown FROM pages WHERE id=$1", dataset.shared)
    assert row["name"] == "Human title"
    assert row["content_markdown"] == "Updated knowledge"
    assert shared.documents[str(dataset.shared)]["title"] == "Human title"


@pytest.mark.asyncio
async def test_small_edit_supports_existing_large_page_and_long_human_title(dataset, pool):
    title = "H" * 250
    content = "Existing detail.\n" * 10000 + "Unique ending."
    await pool.execute(
        "UPDATE pages SET name=$2,content_markdown=$3 WHERE id=$1", dataset.shared, title, content
    )
    shared = await scope(dataset, "shared")
    await shared.tool(
        "edit_page",
        {
            "page_id": str(dataset.shared),
            "old_text": "Unique ending.",
            "new_text": "Unique ending. New lesson.",
        },
    )
    row = await pool.fetchrow("SELECT name,content_markdown FROM pages WHERE id=$1", dataset.shared)
    assert row["name"] == title
    assert row["content_markdown"] == content + " New lesson."


@pytest.mark.asyncio
async def test_editing_reserved_log_returns_recoverable_error(dataset, pool):
    await pool.execute("UPDATE pages SET name='Changelog' WHERE id=$1", dataset.shared)
    shared = await scope(dataset, "shared")
    result = await shared.tool(
        "edit_page",
        {
            "page_id": str(dataset.shared),
            "old_text": "ALLOWED_SHARED_KNOWLEDGE",
            "new_text": "Audit output",
        },
    )
    assert "error" in result
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "ALLOWED_SHARED_KNOWLEDGE"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["edit_page", "write_page"])
async def test_model_recovers_from_readonly_write_without_changing_shared_page(
    dataset, pool, monkeypatch, sprite_exec, tool_name
):
    from anthropic.types import TextBlock, ToolUseBlock

    private = await scope(dataset, "private", "private")
    read = await private.tool("read_document", {"document_id": str(dataset.shared)})
    assert read["writable"] is False
    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            args = (
                {"old_text": "ALLOWED_SHARED_KNOWLEDGE", "new_text": "PRIVATE detail"}
                if tool_name == "edit_page"
                else {"title": "Index", "content": "PRIVATE detail"}
            )
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id="denied",
                        name=tool_name,
                        input={"page_id": str(dataset.shared), **args},
                    )
                ],
            )
        if calls == 2:
            result = kwargs["messages"][-1]["content"][0]
            assert result["is_error"] and "outside" in result["content"]
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id="allowed",
                        name="edit_page",
                        input={
                            "page_id": str(dataset.pages["private"]),
                            "old_text": "PRIVATE_WIKI_SECRET",
                            "new_text": "PRIVATE_WIKI_SECRET with new detail",
                        },
                    )
                ],
            )
        assert not kwargs["messages"][-1]["content"][0]["is_error"]
        return SimpleNamespace(
            stop_reason="end_turn", content=[TextBlock(type="text", text="Updated private wiki.")]
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    assert await curation.run_scope(private, None) == "Updated private wiki."
    assert calls == 3
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == "ALLOWED_SHARED_KNOWLEDGE"
    )
    assert (
        await pool.fetchval("SELECT count(*) FROM page_edits WHERE page_id=$1", dataset.shared) == 0
    )
    assert (
        await pool.fetchval(
            "SELECT content_markdown FROM pages WHERE id=$1", dataset.pages["private"]
        )
        == "PRIVATE_WIKI_SECRET with new detail"
    )


@pytest.mark.asyncio
async def test_collision_cannot_adopt_a_page_created_after_snapshot(dataset, pool):
    shared = await scope(dataset, "shared")
    human_page = await pool.fetchval(
        "INSERT INTO pages (owner_user_id,folder_id,name,content_markdown,created_by) "
        "VALUES ($1,$2,'New human page','Human work',$1) RETURNING id",
        dataset.owner,
        shared.destination,
    )
    with pytest.raises(ValueError, match="created during curation"):
        await shared.tool(
            "write_page",
            {
                "page_id": None,
                "title": "New human page",
                "content": "Stale agent replacement",
            },
        )
    assert human_page not in shared.writable
    denied = await shared.tool(
        "write_page",
        {
            "page_id": str(human_page),
            "title": "New human page",
            "content": "Still stale",
        },
    )
    assert "error" in denied
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", human_page)
        == "Human work"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resumed", [False, True], ids=["partial-last-event", "partial-first-event"]
)
async def test_session_manifest_does_not_promote_event_offsets_to_document_bounds(
    dataset, pool, monkeypatch, sprite_exec, resumed
):
    from anthropic.types import TextBlock, ToolUseBlock

    from backend.services import scoped_curation_inputs

    stamp = datetime.now(UTC) - timedelta(minutes=5)
    until = stamp + timedelta(seconds=2)
    texts = ["First complete event", 'Tool result: "bolt" \\ café\n' * 80, "Last complete event"]
    await pool.execute("DELETE FROM history_events WHERE owner_user_id=$1", dataset.owner)
    for index, text in enumerate(texts):
        await pool.execute(
            "INSERT INTO history_events (owner_user_id,created_by,agent_name,event_type,session_id,content,created_at) "
            "VALUES ($1,$1,'test','user_message','private-job',$2,$3)",
            dataset.owner,
            text,
            stamp + timedelta(seconds=index),
        )
    batch = await scoped_curation_inputs.load_batch(
        dataset.owner,
        stamp - timedelta(microseconds=1),
        until,
        internal=False,
        generation=dataset.workspace["curation_generation"],
        max_chars=2048,
    )
    assert len(batch.documents) == 2 and batch.cursor
    if resumed:
        batch = await scoped_curation_inputs.load_batch(
            dataset.owner,
            batch.through,
            until,
            internal=False,
            generation=dataset.workspace["curation_generation"],
            cursor=batch.cursor,
            max_chars=2048,
        )
        assert len(batch.documents) == 2 and not batch.cursor
    private = await curation.load_scope(
        dataset.workspace,
        "private",
        dataset.users["private"]["wiki_folder_id"],
        [dataset.users["private"]["id"]],
        "agent-curate-session-chunks",
        None,
        until,
        batch=batch,
    )
    requests = []

    async def create(**kwargs):
        requests.append(json.loads(json.dumps(kwargs)))
        if len(requests) == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id="read-session",
                        name="read_document",
                        input={"document_id": "session:private-job"},
                    )
                ],
            )
        return SimpleNamespace(
            stop_reason="end_turn", content=[TextBlock(type="text", text="Read supplied events.")]
        )

    monkeypatch.setattr(
        curation.llm,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    await curation.run_scope(private, None)
    manifest = json.loads(
        requests[0]["messages"][0]["content"].split("New input documents: ", 1)[1]
    )
    read = json.loads(requests[1]["messages"][-1]["content"][0]["content"])
    events = [json.loads(line) for line in read["content"].splitlines()]
    assert len(manifest) == 1 and len(events) == 2
    assert manifest[0]["characters"] == read["total_characters"] == len(read["content"])
    assert "chunk" not in manifest[0]  # The merged document has no single event's bounds.
    assert read["next_offset"] is None
    expected_texts = texts[1:] if resumed else texts[:2]
    for event, original in zip(events, expected_texts, strict=True):
        offset = event["offset"]
        assert event["total_characters"] == len(original)
        assert event["content"] == original[offset : offset + len(event["content"])]
    if resumed:
        assert events[0]["offset"] > 0 and events[1]["content"] == texts[2]
    else:
        assert events[0]["content"] == texts[0]
        assert len(events[1]["content"]) < events[1]["total_characters"]


@pytest.mark.asyncio
async def test_large_files_and_sources_resume_without_skipping_or_unbounded_input(dataset, pool):
    from backend.services import scoped_curation_inputs

    stamp = datetime.now(UTC) - timedelta(minutes=5)
    file_text, source_text = "A" * 6000 + "FILE_END", "B" * 9000 + "SOURCE_END"
    await pool.execute(
        "UPDATE files SET extracted_text=$2,created_at=$3 WHERE id=$1",
        dataset.private_file,
        file_text,
        stamp,
    )
    await pool.execute(
        "UPDATE drive_documents SET content=$2,updated_at=$3 WHERE id=$1",
        dataset.source_doc,
        source_text,
        stamp,
    )
    await pool.execute("DELETE FROM history_events WHERE owner_user_id=$1", dataset.owner)
    since, cursor = stamp - timedelta(microseconds=1), {}
    collected = {}
    for _ in range(12):
        batch = await scoped_curation_inputs.load_batch(
            dataset.owner,
            since,
            datetime.now(UTC),
            internal=False,
            generation=dataset.workspace["curation_generation"],
            cursor=cursor,
            max_chars=2048,
        )
        assert sum(len(d["content"]) for d in batch.documents) <= 2048
        private = await curation.load_scope(
            dataset.workspace,
            "private",
            dataset.users["private"]["wiki_folder_id"],
            [dataset.users["private"]["id"]],
            "agent-curate-file-source-chunks",
            since,
            datetime.now(UTC),
            batch=batch,
        )
        for doc in batch.documents:
            collected[doc["document_id"]] = collected.get(doc["document_id"], "") + doc["content"]
            read = await private.tool("read_document", {"document_id": doc["document_id"]})
            assert read["content"] == doc["content"]
            assert read["total_characters"] == len(doc["content"])
            assert read["next_offset"] is None
            assert private.documents[doc["document_id"]]["chunk"] == {
                "offset": doc["offset"],
                "end": doc["next_offset"],
                "total_characters": doc["characters"],
            }
        if batch.cursor:
            assert batch.through < stamp
            assert batch.cursor != cursor
        since, cursor = batch.through, batch.cursor
        if not cursor:
            break
    assert not cursor and since >= stamp
    assert collected == {
        f"file:{dataset.private_file}": file_text,
        f"source:{dataset.source_doc}": source_text,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "empty_completion"])
async def test_cursor_is_committed_only_after_all_scopes_succeed(
    dataset, pool, monkeypatch, sprite_exec, failure
):
    from backend.services import agent_service, sprite_agent_service

    await pool.execute(
        "UPDATE files SET extracted_text=$2 WHERE id=$1", dataset.private_file, "X" * 10000
    )
    monkeypatch.setattr(curation, "_MAX_INPUT_CHARS", 2048)
    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="external")
    await pool.execute("UPDATE agents SET curated_through=NULL WHERE id=$1", UUID(agent["id"]))
    seen = []

    async def completed(scope, instructions):
        seen.append(scope)
        return "Curated supplied chunk."

    real_run_scope = curation.run_scope
    monkeypatch.setattr(curation, "run_scope", completed)
    agent = await agent_service.get_agent_by_id(UUID(agent["id"]))
    await sprite_agent_service.run_scheduled(agent, "chunk-one")
    before = await agent_service.get_agent_by_id(UUID(agent["id"]))
    assert before["curation_cursor"]
    assert "X" * 100 not in json.dumps([s.documents for s in seen if s.purpose == "shared"])

    async def failed(*args):
        raise RuntimeError("Model unavailable")

    if failure == "empty_completion":

        async def create(**kwargs):
            return SimpleNamespace(stop_reason="end_turn", content=[])

        monkeypatch.setattr(curation, "run_scope", real_run_scope)
        monkeypatch.setattr(
            curation.llm,
            "_get_client",
            lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
        )
    else:
        monkeypatch.setattr(curation, "run_scope", failed)
    with pytest.raises(ExceptionGroup) as errors:
        await sprite_agent_service.run_scheduled(before, "chunk-two")
    if failure == "empty_completion":
        assert all(
            isinstance(error, ValueError) and "no completion summary" in str(error)
            for error in errors.value.exceptions
        )
    after = await agent_service.get_agent_by_id(UUID(agent["id"]))
    assert (after["curated_through"], after["curation_cursor"]) == (
        before["curated_through"],
        before["curation_cursor"],
    )


@pytest.mark.asyncio
async def test_same_timestamp_group_larger_than_event_limit_drains(dataset, pool, monkeypatch):
    from backend.services import curation_service, scoped_curation_inputs

    stamp = datetime.now(UTC) - timedelta(minutes=5)
    await pool.execute("DELETE FROM history_events WHERE owner_user_id=$1", dataset.owner)
    for index in range(7):
        await pool.execute(
            "INSERT INTO history_events (owner_user_id,created_by,agent_name,event_type,session_id,content,created_at) "
            "VALUES ($1,$1,'test','user_message','private-job',$2,$3)",
            dataset.owner,
            f"message-{index}",
            stamp,
        )
    monkeypatch.setattr(curation_service, "_MAX_EVENTS", 2)
    since, cursor, seen = stamp - timedelta(microseconds=1), {}, []
    for _ in range(4):
        batch = await scoped_curation_inputs.load_batch(
            dataset.owner,
            since,
            stamp,
            internal=False,
            generation=dataset.workspace["curation_generation"],
            cursor=cursor,
        )
        seen.extend(d["key"] for d in batch.documents)
        since, cursor = batch.through, batch.cursor
    assert len(seen) == len(set(seen)) == 7
    assert since == stamp and cursor == {}


@pytest.mark.asyncio
async def test_revised_large_document_restarts_its_partial_cursor(dataset, pool):
    from backend.services import scoped_curation_inputs

    stamp = datetime.now(UTC) - timedelta(minutes=5)
    await pool.execute("DELETE FROM history_events WHERE owner_user_id=$1", dataset.owner)
    await pool.execute(
        "UPDATE files SET extracted_text=$2,created_at=$3 WHERE id=$1",
        dataset.private_file,
        "old" * 3000,
        stamp,
    )
    batch = await scoped_curation_inputs.load_batch(
        dataset.owner,
        stamp - timedelta(microseconds=1),
        stamp,
        internal=False,
        generation=dataset.workspace["curation_generation"],
        max_chars=2048,
    )
    await pool.execute(
        "UPDATE files SET extracted_text=$2 WHERE id=$1", dataset.private_file, "new" * 3000
    )
    revised = await scoped_curation_inputs.load_batch(
        dataset.owner,
        batch.through,
        stamp,
        internal=False,
        generation=dataset.workspace["curation_generation"],
        cursor=batch.cursor,
        max_chars=2048,
    )
    assert revised.documents[0]["offset"] == 0
    assert revised.documents[0]["content"].startswith("newnew")


@pytest.mark.asyncio
async def test_scoped_wiki_output_does_not_trigger_staleness_or_catchup(dataset, pool, monkeypatch):
    from backend.services import agent_service, alert_service, scoped_curation_inputs
    from backend.tasks import agent_schedules

    old = datetime.now(UTC) - timedelta(days=4)
    await pool.execute(
        "UPDATE history_events SET created_at=$2 WHERE owner_user_id=$1", dataset.owner, old
    )
    await pool.execute("UPDATE files SET created_at=$2 WHERE owner_user_id=$1", dataset.owner, old)
    await pool.execute(
        "UPDATE drive_documents SET updated_at=$2 WHERE owner_user_id=$1", dataset.owner, old
    )
    agent = await agent_service.get_or_create_curator(dataset.owner, wiki="external")
    await pool.execute(
        "UPDATE agents SET curated_through=$2,last_run_outcome='ran' WHERE id=$1",
        UUID(agent["id"]),
        datetime.now(UTC) - timedelta(days=3),
    )
    await pool.execute("UPDATE pages SET updated_at=now() WHERE owner_user_id=$1", dataset.owner)
    current = await agent_service.get_agent_by_id(UUID(agent["id"]))
    assert not await scoped_curation_inputs.has_pending(current, dataset.workspace)

    async def forbidden(*args):
        pytest.fail("Curator's own wiki output must not page an operator")

    monkeypatch.setattr(alert_service, "send_alert", forbidden)
    assert await agent_schedules._alert_stale_curators() == 0


@pytest.mark.asyncio
async def test_truncated_full_replacement_retries_as_small_edit(
    dataset, pool, monkeypatch, sprite_exec
):
    from anthropic.types import TextBlock, ToolUseBlock

    text = "Keep all existing knowledge.\n" * 2000 + "Unique ending."
    await pool.execute("UPDATE pages SET content_markdown=$2 WHERE id=$1", dataset.shared, text)
    requests = []

    async def create(**kwargs):
        requests.append(json.loads(json.dumps(kwargs)))
        turn = len(requests)
        if turn <= 2:
            return SimpleNamespace(
                stop_reason="max_tokens" if turn == 1 else "tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id=f"write-{turn}",
                        name="write_page",
                        input={
                            "page_id": str(dataset.shared),
                            "title": "Index",
                            "content": "X" * 5000,
                        },
                    )
                ],
            )
        if turn == 3:
            result = kwargs["messages"][-1]["content"][0]
            assert result["is_error"] and "4000 characters" in result["content"]
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        type="tool_use",
                        id="edit",
                        name="edit_page",
                        input={
                            "page_id": str(dataset.shared),
                            "old_text": "Unique ending.",
                            "new_text": "Unique ending. New lesson.",
                        },
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
    await curation.run_scope(await scope(dataset, "shared"), None)
    assert str(dataset.shared) in requests[1]["messages"][-1]["content"]
    assert "X" * 5000 not in json.dumps(requests[1])
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", dataset.shared)
        == text + " New lesson."
    )
    assert (
        await pool.fetchval("SELECT count(*) FROM page_edits WHERE page_id=$1", dataset.shared) == 1
    )
