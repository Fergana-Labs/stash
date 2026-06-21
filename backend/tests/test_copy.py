"""Copy / duplicate: pages, deep folders, and agent-facing copy tools.

File copy needs S3, which the test environment doesn't configure, so these
exercise pages/folders/tables only (the file path is covered by the S3 guard in
the router)."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import agent_runtime, files_tree_service, table_service


@pytest_asyncio.fixture
async def scope(_db_pool):
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    # The scope is the user; content is keyed by owner_user_id = user_id.
    return user_id, user_id


@pytest.mark.asyncio
async def test_copy_page_uses_copy_of_name_and_increments(scope, _db_pool):
    scope_id, user_id = scope
    src = await files_tree_service.create_page(
        owner_user_id=scope_id, name="Spec", created_by=user_id, content="body"
    )
    first = await files_tree_service.copy_page(src["id"], scope_id, user_id)
    second = await files_tree_service.copy_page(src["id"], scope_id, user_id)
    assert first["name"] == "Copy of Spec"
    assert second["name"] == "Copy of Spec (2)"  # collision → numbered
    assert first["content_markdown"] == "body"
    assert first["id"] != src["id"]


@pytest.mark.asyncio
async def test_copy_folder_is_deep(scope, _db_pool):
    scope_id, user_id = scope
    root = await files_tree_service.create_folder(scope_id, "Project", user_id)
    sub = await files_tree_service.create_folder(scope_id, "Sub", user_id, parent_folder_id=root["id"])
    await files_tree_service.create_page(
        owner_user_id=scope_id, name="Top page", created_by=user_id, folder_id=root["id"], content="t"
    )
    await files_tree_service.create_page(
        owner_user_id=scope_id, name="Nested page", created_by=user_id, folder_id=sub["id"], content="n"
    )
    table = await table_service.create_table(
        scope_id, "Data", "", [{"name": "Col", "type": "text"}], user_id, folder_id=root["id"]
    )
    await table_service.create_row(table["id"], {"Col": "v"}, user_id)

    copy = await files_tree_service.copy_folder(root["id"], scope_id, user_id)
    assert copy["name"] == "Copy of Project"

    # New top folder has the page + table + the subfolder; subfolder has its page.
    new_pages = await _db_pool.fetch(
        "SELECT name FROM pages WHERE folder_id = $1 ORDER BY name", copy["id"]
    )
    assert [p["name"] for p in new_pages] == ["Top page"]  # descendants keep names
    new_sub = await _db_pool.fetchrow(
        "SELECT id, name FROM folders WHERE parent_folder_id = $1", copy["id"]
    )
    assert new_sub["name"] == "Sub"
    nested = await _db_pool.fetchval("SELECT name FROM pages WHERE folder_id = $1", new_sub["id"])
    assert nested == "Nested page"
    new_table = await _db_pool.fetchrow(
        "SELECT id, name FROM tables WHERE folder_id = $1", copy["id"]
    )
    assert new_table["name"] == "Data"
    row_count = await _db_pool.fetchval(
        "SELECT count(*) FROM table_rows WHERE table_id = $1", new_table["id"]
    )
    assert row_count == 1  # rows copied, column ids preserved


@pytest.mark.asyncio
async def test_agent_copy_page_tool(scope, _db_pool):
    scope_id, user_id = scope
    src = await files_tree_service.create_page(
        owner_user_id=scope_id, name="Doc", created_by=user_id, content="x"
    )
    scope_token = agent_runtime._scope_ctx.set(scope_id)
    user_token = agent_runtime._user_ctx.set(user_id)
    try:
        out = json.loads(
            (await agent_runtime._copy_page.handler({"page_id": str(src["id"])}))["content"][0][
                "text"
            ]
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)
    assert out["name"] == "Copy of Doc"
