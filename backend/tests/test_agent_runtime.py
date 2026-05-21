"""Tests for the Claude Agent SDK wrapper.

We don't spawn the SDK subprocess in tests (Claude Code CLI is a heavy,
external dependency). Instead we verify:

- Each in-process tool reads workspace context correctly and shapes the
  expected MCP response.
- The tool catalog matches prompts.STASH_TOOL_SET so a misnamed tool
  fails fast at runtime.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from backend.models import StashItem
from backend.services import agent_runtime, prompts, stash_service


def test_tool_catalog_matches_prompts_set():
    """`prompts.STASH_TOOL_SET` is the source of truth for what tools the
    ask-the-workspace agent can use; agent_runtime must implement every name."""
    missing = [name for name in prompts.STASH_TOOL_SET if name not in agent_runtime._TOOLS_BY_NAME]
    assert missing == [], f"agent_runtime missing tool impls: {missing}"


@pytest.mark.asyncio
async def test_current_workspace_raises_outside_context():
    """Tools refuse to run unless `_workspace_ctx` is set — guards against
    a tool firing across the wrong workspace if context binding regresses."""
    with pytest.raises(RuntimeError):
        agent_runtime._current_workspace()


@pytest_asyncio.fixture
async def workspace(_db_pool):
    user_id = uuid4()
    ws_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    await _db_pool.execute(
        "INSERT INTO workspaces (id, name, creator_id, invite_code) " "VALUES ($1, $2, $3, $4)",
        ws_id,
        f"ws_{ws_id.hex[:6]}",
        user_id,
        ws_id.hex[:12],
    )
    await _db_pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
        ws_id,
        user_id,
    )
    return ws_id


@pytest.mark.asyncio
async def test_list_files_tool_scopes_by_workspace(workspace: UUID, _db_pool):
    """Verifies the workspace-context plumbing end-to-end on one tool: the
    response should contain only this workspace's files."""
    user_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    await _db_pool.execute(
        "INSERT INTO files (workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        workspace,
        "scoped.txt",
        "text/plain",
        7,
        f"key_{workspace.hex[:6]}",
        user_id,
    )

    workspace_token = agent_runtime._workspace_ctx.set(workspace)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        result = await agent_runtime._list_files.handler({})
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._workspace_ctx.reset(workspace_token)

    payload = json.loads(result["content"][0]["text"])
    names = [r["name"] for r in payload]
    assert "scoped.txt" in names


@pytest.mark.asyncio
async def test_file_tools_hide_private_stash_files(workspace: UUID, _db_pool):
    user_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    visible_file_id = await _db_pool.fetchval(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, extracted_text) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        workspace,
        "visible.txt",
        "text/plain",
        7,
        f"key_{workspace.hex[:6]}_visible",
        user_id,
        "visible text",
    )
    private_file_id = await _db_pool.fetchval(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, extracted_text) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        workspace,
        "private.txt",
        "text/plain",
        7,
        f"key_{workspace.hex[:6]}_private",
        user_id,
        "private text",
    )
    await stash_service.create_stash(
        workspace_id=workspace,
        owner_id=user_id,
        title="Private files",
        description="",
        workspace_permission="none",
        public_permission="none",
        discoverable=False,
        cover_image_url=None,
        items=[StashItem(object_type="file", object_id=private_file_id)],
    )

    workspace_token = agent_runtime._workspace_ctx.set(workspace)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        list_result = await agent_runtime._list_files.handler({})
        visible_result = await agent_runtime._read_file.handler({"file_id": str(visible_file_id)})
        private_result = await agent_runtime._read_file.handler({"file_id": str(private_file_id)})
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._workspace_ctx.reset(workspace_token)

    listed_files = json.loads(list_result["content"][0]["text"])
    listed_names = [file["name"] for file in listed_files]
    assert "visible.txt" in listed_names
    assert "private.txt" not in listed_names
    assert json.loads(visible_result["content"][0]["text"])["text"] == "visible text"
    assert json.loads(private_result["content"][0]["text"]) == {"error": "not found"}


@pytest.mark.asyncio
async def test_stash_tools_create_list_and_delete(workspace: UUID, _db_pool):
    user_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    folder_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO folders (id, workspace_id, name, created_by) VALUES ($1, $2, $3, $4)",
        folder_id,
        workspace,
        "Launch notes",
        user_id,
    )

    workspace_token = agent_runtime._workspace_ctx.set(workspace)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        create_result = await agent_runtime._create_stash.handler(
            {
                "title": "Launch bundle",
                "description": "Published launch context",
                "items": [{"object_type": "folder", "object_id": str(folder_id)}],
            }
        )
        list_result = await agent_runtime._list_stashes.handler({})
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._workspace_ctx.reset(workspace_token)

    created = json.loads(create_result["content"][0]["text"])
    listed = json.loads(list_result["content"][0]["text"])
    assert created["title"] == "Launch bundle"
    assert listed[0]["id"] == created["id"]
    assert listed[0]["items"][0]["object_type"] == "folder"

    workspace_token = agent_runtime._workspace_ctx.set(workspace)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        delete_result = await agent_runtime._delete_stash.handler({"stash_id": created["id"]})
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._workspace_ctx.reset(workspace_token)

    deleted = json.loads(delete_result["content"][0]["text"])
    assert deleted == {"deleted": True, "stash_id": created["id"]}


@pytest.mark.asyncio
async def test_external_stash_is_workspace_fork(workspace: UUID, _db_pool, monkeypatch):
    copied_files = []
    deleted_files = []

    async def fake_copy_file(source_key, workspace_id, filename, content_type):
        copied_key = f"{workspace_id}/copied/{filename}"
        copied_files.append(
            {
                "source_key": source_key,
                "workspace_id": workspace_id,
                "filename": filename,
                "content_type": content_type,
                "copied_key": copied_key,
            }
        )
        return copied_key

    async def fake_delete_file(storage_key):
        deleted_files.append(storage_key)

    monkeypatch.setattr(stash_service.storage_service, "copy_file", fake_copy_file)
    monkeypatch.setattr(stash_service.storage_service, "delete_file", fake_delete_file)

    owner_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    target_workspace = uuid4()
    page_id = uuid4()
    file_id = uuid4()
    session_row_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO workspaces (id, name, creator_id, invite_code) VALUES ($1, $2, $3, $4)",
        target_workspace,
        f"target_{target_workspace.hex[:6]}",
        owner_id,
        target_workspace.hex[:12],
    )
    await _db_pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
        target_workspace,
        owner_id,
    )
    await _db_pool.execute(
        "INSERT INTO pages (id, workspace_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, $3, $4, $5)",
        page_id,
        workspace,
        "Public source page",
        "External Stash source",
        owner_id,
    )
    await _db_pool.execute(
        "INSERT INTO files "
        "(id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, 12, $5, $6)",
        file_id,
        workspace,
        "source.txt",
        "text/plain",
        "source/file-key",
        owner_id,
    )
    await _db_pool.execute(
        "INSERT INTO sessions (id, workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, $3, $4, $5)",
        session_row_id,
        workspace,
        "session-external-source",
        "assistant",
        owner_id,
    )
    await _db_pool.execute(
        "INSERT INTO history_events "
        "(workspace_id, created_by, agent_name, event_type, content, session_id) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        workspace,
        owner_id,
        "assistant",
        "assistant",
        "Copied session event",
        "session-external-source",
    )
    await _db_pool.execute(
        "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, $2, $3, 42)",
        session_row_id,
        "logs/source.log",
        "source/artifact-key",
    )
    source = await stash_service.create_stash(
        workspace_id=workspace,
        owner_id=owner_id,
        title="Fork source Stash",
        description="",
        workspace_permission="view",
        public_permission="view",
        discoverable=False,
        cover_image_url=None,
        items=[
            StashItem(object_type="page", object_id=page_id, position=0),
            StashItem(object_type="session", object_id=session_row_id, position=1),
            StashItem(object_type="file", object_id=file_id, position=2),
        ],
    )

    attached = await stash_service.add_external_stash(
        target_workspace, source["slug"], added_by=owner_id
    )
    target_stashes = await stash_service.list_workspace_stashes(target_workspace, owner_id)

    assert attached is not None
    assert attached["id"] != source["id"]
    assert attached["is_external"] is True
    assert attached["added_to_workspace_id"] == target_workspace
    assert attached["forked_from_stash_id"] == source["id"]
    assert [stash["id"] for stash in target_stashes] == [attached["id"]]
    assert target_stashes[0]["workspace_id"] == target_workspace

    fork_page_id = attached["items"][0]["object_id"]
    assert fork_page_id != page_id
    fork_page = await _db_pool.fetchrow(
        "SELECT workspace_id, name, content_markdown FROM pages WHERE id = $1",
        fork_page_id,
    )
    assert fork_page["workspace_id"] == target_workspace
    assert fork_page["name"] == "Public source page"
    assert fork_page["content_markdown"] == "External Stash source"

    await _db_pool.execute(
        "UPDATE pages SET content_markdown = $1 WHERE id = $2",
        "Edited source",
        page_id,
    )
    fork_content = await _db_pool.fetchval(
        "SELECT content_markdown FROM pages WHERE id = $1",
        fork_page_id,
    )
    assert fork_content == "External Stash source"

    fork_session_id = attached["items"][1]["object_id"]
    assert fork_session_id != session_row_id
    fork_session = await _db_pool.fetchrow(
        "SELECT workspace_id, session_id FROM sessions WHERE id = $1",
        fork_session_id,
    )
    assert fork_session["workspace_id"] == target_workspace
    assert fork_session["session_id"] == f"session-external-source-fork-{session_row_id.hex[:8]}"
    fork_event = await _db_pool.fetchrow(
        "SELECT workspace_id, session_id, content FROM history_events WHERE workspace_id = $1",
        target_workspace,
    )
    assert fork_event["session_id"] == fork_session["session_id"]
    assert fork_event["content"] == "Copied session event"

    fork_artifact_key = await _db_pool.fetchval(
        "SELECT storage_key FROM session_artifacts WHERE session_id = $1",
        fork_session_id,
    )
    assert fork_artifact_key == f"{target_workspace}/copied/source.log"

    fork_file_id = attached["items"][2]["object_id"]
    fork_file_key = await _db_pool.fetchval(
        "SELECT storage_key FROM files WHERE id = $1",
        fork_file_id,
    )
    assert fork_file_key == f"{target_workspace}/copied/source.txt"
    assert {copy["source_key"] for copy in copied_files} == {
        "source/file-key",
        "source/artifact-key",
    }

    removed = await stash_service.remove_external_stash(
        target_workspace,
        attached["id"],
        owner_id,
    )

    assert removed is True
    assert "source/file-key" not in deleted_files
    assert "source/artifact-key" not in deleted_files
    assert set(deleted_files) == {fork_file_key, fork_artifact_key}
