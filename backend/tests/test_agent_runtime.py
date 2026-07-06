"""Tests for the Claude Agent SDK wrapper.

We don't spawn the SDK subprocess in tests (Claude Code CLI is a heavy,
external dependency). Instead we verify:

- Each in-process tool reads scope context correctly and shapes the
  expected MCP response.
- The tool catalog matches prompts.STASH_TOOL_SET so a misnamed tool
  fails fast at runtime.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from backend.services import agent_runtime, prompts, shared_skill_service


def test_tool_catalog_matches_prompts_set():
    """`prompts.STASH_TOOL_SET` is the source of truth for what tools the
    ask-the-stash agent can use; agent_runtime must implement every name."""
    missing = [name for name in prompts.STASH_TOOL_SET if name not in agent_runtime._TOOLS_BY_NAME]
    assert missing == [], f"agent_runtime missing tool impls: {missing}"


@pytest.mark.asyncio
async def test_current_scope_raises_outside_context():
    """Tools refuse to run unless `_scope_ctx` is set — guards against
    a tool firing against the wrong scope if context binding regresses."""
    with pytest.raises(RuntimeError):
        agent_runtime._current_scope()


@pytest_asyncio.fixture
async def scope(_db_pool):
    """The user IS the scope: the returned id is the user's id (owner_user_id)."""
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    return user_id


@pytest.mark.asyncio
async def test_list_files_tool_scopes_by_owner(scope: UUID, _db_pool):
    """Verifies the scope-context plumbing end-to-end on one tool: the
    response should contain only this scope's files."""
    user_id = scope  # the scope id is the user id
    await _db_pool.execute(
        "INSERT INTO files (owner_user_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        scope,
        "scoped.txt",
        "text/plain",
        7,
        f"key_{scope.hex[:6]}",
        user_id,
    )

    scope_token = agent_runtime._scope_ctx.set(scope)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        result = await agent_runtime._list_files.handler({})
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)

    payload = json.loads(result["content"][0]["text"])
    names = [r["name"] for r in payload]
    assert "scoped.txt" in names


@pytest.mark.asyncio
async def test_skill_tools_create_publish_update_and_unpublish(scope: UUID, _db_pool):
    """The agent's skill lifecycle: create makes a SKILL.md folder, publish
    mints the share record (and a public URL), update edits the record, and
    unpublish removes only the record — the folder stays a skill."""
    user_id = scope  # the scope id is the user id

    scope_token = agent_runtime._scope_ctx.set(scope)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        created = json.loads(
            (
                await agent_runtime._create_skill.handler(
                    {
                        "name": "Launch bundle",
                        "skill_md": (
                            "---\nname: Launch bundle\ndescription: Launch context\n---\n\n# Go\n"
                        ),
                        "files": [{"name": "checklist.md", "content": "- ship it"}],
                    }
                )
            )["content"][0]["text"]
        )
        listed = json.loads((await agent_runtime._list_skills.handler({}))["content"][0]["text"])
        published = json.loads(
            (await agent_runtime._publish_skill.handler({"folder_id": created["folder_id"]}))[
                "content"
            ][0]["text"]
        )
        updated = json.loads(
            (
                await agent_runtime._update_skill.handler(
                    {"skill_id": published["id"], "description": "Edited"}
                )
            )["content"][0]["text"]
        )
        unpublished = json.loads(
            (await agent_runtime._unpublish_skill.handler({"skill_id": published["id"]}))[
                "content"
            ][0]["text"]
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)

    assert created["name"] == "Launch bundle"
    [skill] = [s for s in listed if s["folder_id"] == created["folder_id"]]
    assert skill["name"] == "Launch bundle"
    assert skill["files"] == 2  # SKILL.md + checklist.md
    assert skill["published"] is None  # creating a skill does not share it

    # Publishing alone makes the skill public but not Discover-listed.
    assert published["discoverable"] is False
    assert published["url"].endswith(f"/skills/{published['slug']}")
    assert updated["description"] == "Edited"
    assert unpublished == {"deleted": True, "skill_id": published["id"]}
    # The publish record is gone but the folder is still a skill.
    record = await _db_pool.fetchval(
        "SELECT 1 FROM skills WHERE folder_id = $1", UUID(created["folder_id"])
    )
    assert record is None
    skill_md = await _db_pool.fetchval(
        "SELECT 1 FROM pages WHERE folder_id = $1 AND name = 'SKILL.md' AND deleted_at IS NULL",
        UUID(created["folder_id"]),
    )
    assert skill_md == 1


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
async def test_create_and_update_page_round_trip(scope: UUID, _db_pool):
    """create_page persists markdown + html; update_page edits an existing page
    by id. Both must bind to the active scope context."""
    user_id = scope  # the scope id is the user id

    scope_token = agent_runtime._scope_ctx.set(scope)
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
        agent_runtime._scope_ctx.reset(scope_token)

    html_page = json.loads(html["content"][0]["text"])
    assert md_page["name"] == "Notes" and "id" in md_page
    assert html_page["name"] == "Dashboard"
    # Persisted to this scope, bound by context.
    stored = await _db_pool.fetchrow(
        "SELECT owner_user_id, content_html FROM pages WHERE id = $1", UUID(html_page["id"])
    )
    assert stored["owner_user_id"] == scope
    assert "<h1>Live</h1>" in (stored["content_html"] or "")
    # update_page edited the markdown body in place.
    assert "Hello again" in json.loads(read_back["content"][0]["text"])["content"]


def test_destructive_tools_withheld_from_untrusted_surfaces():
    """The Slack surface is untrusted (prompt-injectable), so destructive tools
    must never reach it; the ask surface must stay read-only."""
    for name in prompts.SLACK_DESTRUCTIVE_TOOLS:
        assert name in prompts.STASH_TOOL_SET
        assert name not in prompts.SLACK_TOOL_SET
    write_tools = (
        "create_page",
        "update_page",
        "create_folder",
        "move_page",
        "rename_page",
        "delete_page",
        "create_table",
        "insert_row",
        "update_row",
        "add_column",
        "delete_row",
    )
    for name in write_tools:
        assert name not in prompts.ASK_TOOL_SET


@pytest.mark.asyncio
async def test_edit_provenance_stamped_for_agent_and_null_for_human(scope: UUID, _db_pool):
    """Agent writes stamp the page + log who/which session; a plain service
    (human/REST) write logs an edit row but leaves the agent/session NULL."""
    from backend.services import files_tree_service

    user_id = scope  # the scope id is the user id

    # Human/REST path: no agent context → NULL stamp, but still logged.
    human = await files_tree_service.create_page(
        owner_user_id=scope, name="Human", created_by=user_id, content="hi"
    )
    h_cols = await _db_pool.fetchrow(
        "SELECT last_edit_session_id, last_edit_agent_name FROM pages WHERE id = $1", human["id"]
    )
    assert h_cols["last_edit_agent_name"] is None and h_cols["last_edit_session_id"] is None
    h_log = await _db_pool.fetchrow(
        "SELECT op, agent_name FROM page_edits WHERE page_id = $1", human["id"]
    )
    assert h_log["op"] == "create" and h_log["agent_name"] is None

    # Agent path: session + agent name bound in context → stamped + logged.
    session_token = agent_runtime._session_ctx.set("chat-123")
    agent_token = agent_runtime._agent_name_ctx.set("Stash Agent")
    scope_token = agent_runtime._scope_ctx.set(scope)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        created = json.loads(
            (await agent_runtime._create_page.handler({"name": "Agent doc", "content": "a b"}))[
                "content"
            ][0]["text"]
        )
        await agent_runtime._edit_page.handler(
            {"page_id": created["id"], "old_string": "a b", "new_string": "a c"}
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)
        agent_runtime._agent_name_ctx.reset(agent_token)
        agent_runtime._session_ctx.reset(session_token)

    page_id = UUID(created["id"])
    cols = await _db_pool.fetchrow(
        "SELECT last_edit_session_id, last_edit_agent_name FROM pages WHERE id = $1", page_id
    )
    assert cols["last_edit_session_id"] == "chat-123"
    assert cols["last_edit_agent_name"] == "Stash Agent"
    ops = [
        r["op"]
        for r in await _db_pool.fetch(
            "SELECT op FROM page_edits WHERE page_id = $1 ORDER BY created_at", page_id
        )
    ]
    assert ops == ["create", "edit"]  # the edit_page call logged op='edit'


@pytest.mark.asyncio
async def test_edit_page_surgical_edits(scope: UUID, _db_pool):
    """edit_page does a unique str-replace / append on the active body, and fails
    loud (writing nothing) when the anchor isn't unique."""
    from backend.services import files_tree_service

    user_id = scope  # the scope id is the user id

    md = await files_tree_service.create_page(
        owner_user_id=scope, name="Doc", created_by=user_id, content="alpha beta gamma"
    )
    html = await files_tree_service.create_page(
        owner_user_id=scope,
        name="Page",
        created_by=user_id,
        content_type="html",
        content_html="<p>one</p>",
    )

    scope_token = agent_runtime._scope_ctx.set(scope)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        # Unique replace on markdown.
        await agent_runtime._edit_page.handler(
            {"page_id": str(md["id"]), "old_string": "beta", "new_string": "BETA"}
        )
        # Append on markdown.
        await agent_runtime._edit_page.handler(
            {"page_id": str(md["id"]), "new_string": " delta", "mode": "append"}
        )
        # Unique replace on the html body.
        await agent_runtime._edit_page.handler(
            {"page_id": str(html["id"]), "old_string": "<p>one</p>", "new_string": "<p>two</p>"}
        )
        # Zero matches → fail loud, no write.
        zero = json.loads(
            (
                await agent_runtime._edit_page.handler(
                    {"page_id": str(md["id"]), "old_string": "nope", "new_string": "x"}
                )
            )["content"][0]["text"]
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)

    md_body = await _db_pool.fetchval("SELECT content_markdown FROM pages WHERE id = $1", md["id"])
    html_body = await _db_pool.fetchval("SELECT content_html FROM pages WHERE id = $1", html["id"])
    assert md_body == "alpha BETA gamma delta"
    assert html_body == "<p>two</p>"
    assert zero["error"] == "no-unique-match"


@pytest.mark.asyncio
async def test_edit_page_multi_match_writes_nothing(scope: UUID, _db_pool):
    """A >1 match must not partially write — the body is untouched."""
    from backend.services import files_tree_service

    user_id = scope  # the scope id is the user id
    page = await files_tree_service.create_page(
        owner_user_id=scope, name="Dup", created_by=user_id, content="x x x"
    )

    with pytest.raises(files_tree_service.EditMatchError):
        await files_tree_service.edit_page(
            page["id"], scope, user_id, old_string="x", new_string="y"
        )
    body = await _db_pool.fetchval("SELECT content_markdown FROM pages WHERE id = $1", page["id"])
    assert body == "x x x"


@pytest.mark.asyncio
async def test_tree_mutation_tools_round_trip(scope: UUID, _db_pool):
    """create_folder + the page move/rename/delete tools let the agent organize
    the scope, all bound to the active scope context."""
    user_id = scope  # the scope id is the user id

    scope_token = agent_runtime._scope_ctx.set(scope)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        folder = json.loads(
            (await agent_runtime._create_folder.handler({"name": "Specs"}))["content"][0]["text"]
        )
        page = json.loads(
            (
                await agent_runtime._create_page.handler(
                    {"name": "Draft", "content": "# Draft", "folder_id": folder["id"]}
                )
            )["content"][0]["text"]
        )
        await agent_runtime._rename_page.handler({"page_id": page["id"], "name": "Final"})
        await agent_runtime._move_page.handler({"page_id": page["id"], "move_to_root": True})
        deleted = json.loads(
            (await agent_runtime._delete_page.handler({"page_id": page["id"]}))["content"][0][
                "text"
            ]
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)

    assert deleted == {"deleted": True, "page_id": page["id"]}
    stored = await _db_pool.fetchrow(
        "SELECT name, folder_id, deleted_at FROM pages WHERE id = $1", UUID(page["id"])
    )
    assert stored["name"] == "Final"  # rename took
    assert stored["folder_id"] is None  # moved to root
    assert stored["deleted_at"] is not None  # soft-deleted


@pytest.mark.asyncio
async def test_table_mutation_tools_round_trip(scope: UUID, _db_pool):
    """create_table + row/column tools wrap table_service, guarded so an agent
    can only touch tables in its own scope."""
    user_id = scope  # the scope id is the user id

    scope_token = agent_runtime._scope_ctx.set(scope)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        table = json.loads(
            (
                await agent_runtime._create_table.handler(
                    {"name": "Leads", "columns": [{"name": "Company", "type": "text"}]}
                )
            )["content"][0]["text"]
        )
        row = json.loads(
            (
                await agent_runtime._insert_row.handler(
                    {"table_id": table["id"], "data": {"Company": "Acme"}}
                )
            )["content"][0]["text"]
        )
        await agent_runtime._add_column.handler(
            {"table_id": table["id"], "column": {"name": "Stage", "type": "text"}}
        )
        await agent_runtime._update_row.handler(
            {"table_id": table["id"], "row_id": row["id"], "data": {"Stage": "Won"}}
        )
        stored_data = await _db_pool.fetchval(
            "SELECT data FROM table_rows WHERE id = $1", UUID(row["id"])
        )
        deleted = json.loads(
            (
                await agent_runtime._delete_row.handler(
                    {"table_id": table["id"], "row_id": row["id"]}
                )
            )["content"][0]["text"]
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)

    assert "Acme" in json.dumps(stored_data)
    assert "Won" in json.dumps(stored_data)
    assert deleted == {"deleted": True, "row_id": row["id"]}
    remaining = await _db_pool.fetchval(
        "SELECT count(*) FROM table_rows WHERE id = $1", UUID(row["id"])
    )
    assert remaining == 0


@pytest.mark.asyncio
async def test_table_tools_reject_cross_scope(scope: UUID, _db_pool):
    """A table id from another scope must be invisible to the agent's
    write tools — the scope guard returns 'table not found'."""
    user_id = scope  # the scope id is the user id
    other_scope = uuid4()  # a different user's scope
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        other_scope,
        f"u_{other_scope.hex[:6]}",
    )
    other_table = uuid4()
    await _db_pool.execute(
        "INSERT INTO tables (id, owner_user_id, name, description, columns, created_by, updated_by) "
        "VALUES ($1, $2, 'Secret', '', '[]'::jsonb, $3, $3)",
        other_table,
        other_scope,
        user_id,
    )

    scope_token = agent_runtime._scope_ctx.set(scope)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        result = json.loads(
            (await agent_runtime._insert_row.handler({"table_id": str(other_table), "data": {}}))[
                "content"
            ][0]["text"]
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)

    assert result == {"error": "table not found"}


@pytest.mark.asyncio
async def test_fork_skill_deep_copies_folder_without_publish_record(scope: UUID, _db_pool):
    """Forking deep-copies the skill folder into the target scope as a
    private (unpublished) skill: contents are point-in-time copies, not live
    references, and no skills row is minted for the fork."""
    owner_id = scope  # the scope id is the user id
    target_scope = uuid4()  # the fork target is another user's scope
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        target_scope,
        f"u_{target_scope.hex[:6]}",
    )
    folder_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO folders (id, owner_user_id, name, created_by) VALUES ($1, $2, $3, $4)",
        folder_id,
        scope,
        "Fork source",
        owner_id,
    )
    page_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO pages (id, owner_user_id, folder_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        page_id,
        scope,
        folder_id,
        "Public source page",
        "External Stash source",
        owner_id,
    )
    source = await shared_skill_service.publish_folder(
        scope,
        owner_id,
        folder_id,
        title="Fork source Stash",
    )

    attached = await shared_skill_service.fork_skill(
        target_scope, source["slug"], added_by=owner_id
    )

    assert attached is not None
    assert attached["name"] == "Fork source"
    fork_folder_id = UUID(attached["folder_id"])
    assert fork_folder_id != folder_id
    fork_folder_owner = await _db_pool.fetchval(
        "SELECT owner_user_id FROM folders WHERE id = $1", fork_folder_id
    )
    assert fork_folder_owner == target_scope

    # The fork has no publish record of its own — it's a private skill folder.
    record = await _db_pool.fetchval("SELECT 1 FROM skills WHERE owner_user_id = $1", target_scope)
    assert record is None

    # The page travelled as a copy (SKILL.md too, minted at publish time).
    fork_page = await _db_pool.fetchrow(
        "SELECT id, content_markdown FROM pages "
        "WHERE folder_id = $1 AND name = 'Public source page'",
        fork_folder_id,
    )
    assert fork_page is not None
    assert fork_page["content_markdown"] == "External Stash source"
    fork_skill_md = await _db_pool.fetchval(
        "SELECT 1 FROM pages WHERE folder_id = $1 AND name = 'SKILL.md'", fork_folder_id
    )
    assert fork_skill_md == 1

    # Editing the source afterwards does not leak into the fork.
    await _db_pool.execute(
        "UPDATE pages SET content_markdown = $1 WHERE id = $2",
        "Edited source",
        page_id,
    )
    fork_content = await _db_pool.fetchval(
        "SELECT content_markdown FROM pages WHERE id = $1",
        fork_page["id"],
    )
    assert fork_content == "External Stash source"
