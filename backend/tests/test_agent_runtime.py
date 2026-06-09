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

from backend.models import CartridgeItem
from backend.services import agent_runtime, cartridge_service, prompts


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
async def test_cartridge_tools_create_list_and_delete(workspace: UUID, _db_pool):
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
        create_result = await agent_runtime._create_cartridge.handler(
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
        delete_result = await agent_runtime._delete_cartridge.handler(
            {"cartridge_id": created["id"]}
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._workspace_ctx.reset(workspace_token)

    deleted = json.loads(delete_result["content"][0]["text"])
    assert deleted == {"deleted": True, "cartridge_id": created["id"]}


def test_page_tools_are_writable_surfaces_only():
    """create_page/update_page are mutations: offered to the agent + Slack
    surfaces (STASH_TOOL_SET), but withheld from the read-only ask surface so a
    prompt-injected ask can't author pages."""
    for name in ("create_page", "update_page"):
        assert name in agent_runtime._TOOLS_BY_NAME
        assert name in prompts.STASH_TOOL_SET
        assert name in prompts.SLACK_TOOL_SET
        assert name not in prompts.ASK_TOOL_SET


@pytest.mark.asyncio
async def test_create_and_update_page_round_trip(workspace: UUID, _db_pool):
    """create_page persists markdown + html; update_page edits an existing page
    by id. Both must bind to the active workspace context."""
    user_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)

    workspace_token = agent_runtime._workspace_ctx.set(workspace)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        md = await agent_runtime._create_page.handler(
            {"name": "Notes", "content_type": "markdown", "content": "# Hello"}
        )
        html = await agent_runtime._create_page.handler(
            {"name": "Dashboard", "content_type": "html", "content_html": "<h1>Live</h1>"}
        )
        md_page = json.loads(md["content"][0]["text"])
        await agent_runtime._update_page.handler(
            {"page_id": md_page["id"], "content": "# Hello again"}
        )
        read_back = await agent_runtime._read_page.handler({"page_id": md_page["id"]})
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._workspace_ctx.reset(workspace_token)

    html_page = json.loads(html["content"][0]["text"])
    assert md_page["name"] == "Notes" and "id" in md_page
    assert html_page["name"] == "Dashboard"
    # Persisted to this workspace, scoped by context.
    stored = await _db_pool.fetchrow(
        "SELECT workspace_id, content_html FROM pages WHERE id = $1", UUID(html_page["id"])
    )
    assert stored["workspace_id"] == workspace
    assert "<h1>Live</h1>" in (stored["content_html"] or "")
    # update_page edited the markdown body in place.
    assert "Hello again" in json.loads(read_back["content"][0]["text"])["content"]


@pytest.mark.asyncio
async def test_external_cartridge_is_workspace_fork(workspace: UUID, _db_pool):
    owner_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    target_workspace = uuid4()
    page_id = uuid4()
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
    source = await cartridge_service.create_cartridge(
        workspace_id=workspace,
        owner_id=owner_id,
        title="Fork source Stash",
        description="",
        workspace_permission="read",
        public_permission="read",
        discoverable=False,
        cover_image_url=None,
        items=[
            CartridgeItem(object_type="page", object_id=page_id, position=0),
            CartridgeItem(object_type="session", object_id=session_row_id, position=1),
        ],
    )

    attached = await cartridge_service.add_external_cartridge(
        target_workspace, source["slug"], added_by=owner_id
    )
    target_stashes = await cartridge_service.list_workspace_stashes(target_workspace, owner_id)

    assert attached is not None
    assert attached["id"] != source["id"]
    assert attached["is_external"] is True
    assert attached["added_to_workspace_id"] == target_workspace
    assert attached["forked_from_cartridge_id"] == source["id"]
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
