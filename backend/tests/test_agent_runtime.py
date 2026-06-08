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


async def _create_user(_db_pool, prefix: str) -> UUID:
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"{prefix}_{user_id.hex[:6]}",
    )
    return user_id


async def _add_workspace_member(_db_pool, workspace_id: UUID, user_id: UUID, role: str) -> None:
    await _db_pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, $3)",
        workspace_id,
        user_id,
        role,
    )


async def _create_folder(_db_pool, workspace_id: UUID, created_by: UUID, name: str) -> UUID:
    folder_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO folders (id, workspace_id, name, created_by) VALUES ($1, $2, $3, $4)",
        folder_id,
        workspace_id,
        name,
        created_by,
    )
    return folder_id


async def _run_tool(handler, workspace_id: UUID, user_id: UUID, args: dict) -> dict | list:
    workspace_token = agent_runtime._workspace_ctx.set(workspace_id)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        result = await handler(args)
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._workspace_ctx.reset(workspace_token)
    return json.loads(result["content"][0]["text"])


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


@pytest.mark.asyncio
async def test_cartridge_tool_item_validation_redacts_raw_inputs(workspace: UUID, _db_pool):
    user_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    sensitive_ref = "token=secret-token Webflow confidential page id"
    sensitive_label = "Webflow board transcript"

    result = await _run_tool(
        agent_runtime._create_cartridge.handler,
        workspace,
        user_id,
        {
            "title": "Sensitive bundle",
            "items": [
                {
                    "object_type": "page",
                    "object_id": sensitive_ref,
                    "label_override": sensitive_label,
                }
            ],
        },
    )

    assert result == {"error": "Invalid Stash item list"}
    result_json = json.dumps(result)
    assert "secret-token" not in result_json
    assert "Webflow confidential page id" not in result_json
    assert sensitive_label not in result_json


@pytest.mark.asyncio
async def test_cartridge_tool_id_validation_redacts_raw_inputs(workspace: UUID, _db_pool):
    user_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    sensitive_id = "token=secret-token Webflow confidential Stash id"

    updated = await _run_tool(
        agent_runtime._update_cartridge.handler,
        workspace,
        user_id,
        {"cartridge_id": sensitive_id, "title": "ignored"},
    )
    deleted = await _run_tool(
        agent_runtime._delete_cartridge.handler,
        workspace,
        user_id,
        {"cartridge_id": sensitive_id},
    )

    assert updated == {"error": "invalid cartridge id"}
    assert deleted == {"error": "invalid cartridge id"}
    result_json = json.dumps([updated, deleted])
    assert "secret-token" not in result_json
    assert "Webflow confidential Stash id" not in result_json


@pytest.mark.asyncio
async def test_create_cartridge_tool_limits_workspace_visibility_to_owners(
    workspace: UUID, _db_pool
):
    owner_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    editor_id = await _create_user(_db_pool, "agent_editor")
    await _add_workspace_member(_db_pool, workspace, editor_id, "editor")
    folder_id = await _create_folder(_db_pool, workspace, owner_id, "Private launch notes")

    workspace_visible = await _run_tool(
        agent_runtime._create_cartridge.handler,
        workspace,
        editor_id,
        {
            "title": "Workspace-visible launch bundle",
            "items": [{"object_type": "folder", "object_id": str(folder_id)}],
        },
    )
    private = await _run_tool(
        agent_runtime._create_cartridge.handler,
        workspace,
        editor_id,
        {
            "title": "Private launch bundle",
            "workspace_permission": "none",
            "public_permission": "none",
            "items": [{"object_type": "folder", "object_id": str(folder_id)}],
        },
    )

    assert workspace_visible == {
        "error": "Only workspace owners can create workspace or public Stashes"
    }
    assert private["title"] == "Private launch bundle"
    assert private["workspace_permission"] == "none"
    assert private["public_permission"] == "none"
    assert private["items"][0]["object_type"] == "folder"


@pytest.mark.asyncio
async def test_create_cartridge_tool_rejects_viewers(workspace: UUID, _db_pool):
    owner_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    viewer_id = await _create_user(_db_pool, "agent_viewer")
    await _add_workspace_member(_db_pool, workspace, viewer_id, "viewer")
    folder_id = await _create_folder(_db_pool, workspace, owner_id, "Viewer-visible notes")

    result = await _run_tool(
        agent_runtime._create_cartridge.handler,
        workspace,
        viewer_id,
        {
            "title": "Viewer private bundle",
            "workspace_permission": "none",
            "public_permission": "none",
            "items": [{"object_type": "folder", "object_id": str(folder_id)}],
        },
    )

    assert result == {"error": "Viewers can read but not create Stashes"}


@pytest.mark.asyncio
async def test_update_cartridge_tool_limits_public_changes_to_owners(workspace: UUID, _db_pool):
    owner_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    editor_id = await _create_user(_db_pool, "agent_stash_admin")
    await _add_workspace_member(_db_pool, workspace, editor_id, "editor")
    folder_id = await _create_folder(_db_pool, workspace, owner_id, "Admin-only source")
    stash = await cartridge_service.create_cartridge(
        workspace_id=workspace,
        owner_id=owner_id,
        title="Private admin-managed Stash",
        description="",
        workspace_permission="none",
        public_permission="none",
        discoverable=False,
        cover_image_url=None,
        items=[CartridgeItem(object_type="folder", object_id=folder_id, position=0)],
    )
    await _db_pool.execute(
        "INSERT INTO cartridge_members (cartridge_id, user_id, permission, granted_by) "
        "VALUES ($1, $2, 'admin', $3)",
        stash["id"],
        editor_id,
        owner_id,
    )

    result = await _run_tool(
        agent_runtime._update_cartridge.handler,
        workspace,
        editor_id,
        {"cartridge_id": str(stash["id"]), "public_permission": "read"},
    )

    public_permission = await _db_pool.fetchval(
        "SELECT public_permission FROM cartridges WHERE id = $1",
        stash["id"],
    )
    assert result == {"error": "Only workspace owners can make a Stash workspace or public"}
    assert public_permission == "none"


@pytest.mark.asyncio
async def test_cartridge_mutation_tools_stay_in_active_workspace(workspace: UUID, _db_pool):
    owner_id = await _db_pool.fetchval("SELECT creator_id FROM workspaces WHERE id = $1", workspace)
    other_workspace = uuid4()
    await _db_pool.execute(
        "INSERT INTO workspaces (id, name, creator_id, invite_code) VALUES ($1, $2, $3, $4)",
        other_workspace,
        f"other_{other_workspace.hex[:6]}",
        owner_id,
        other_workspace.hex[:12],
    )
    await _add_workspace_member(_db_pool, other_workspace, owner_id, "owner")
    other_stash = await cartridge_service.create_cartridge(
        workspace_id=other_workspace,
        owner_id=owner_id,
        title="Other workspace Stash",
        description="",
        workspace_permission="none",
        public_permission="none",
        discoverable=False,
        cover_image_url=None,
        items=[],
    )

    update_result = await _run_tool(
        agent_runtime._update_cartridge.handler,
        workspace,
        owner_id,
        {"cartridge_id": str(other_stash["id"]), "title": "Mutated from wrong workspace"},
    )
    delete_result = await _run_tool(
        agent_runtime._delete_cartridge.handler,
        workspace,
        owner_id,
        {"cartridge_id": str(other_stash["id"])},
    )

    title = await _db_pool.fetchval(
        "SELECT title FROM cartridges WHERE id = $1",
        other_stash["id"],
    )
    assert update_result == {"error": "not found"}
    assert delete_result == {"error": "not found"}
    assert title == "Other workspace Stash"


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
