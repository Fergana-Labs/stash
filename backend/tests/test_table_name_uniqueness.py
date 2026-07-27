"""Table names are unique per folder, like pages and folders.

Tables were the one thing in the VFS whose names could collide: 0001 gave
them UNIQUE(created_by, name) WHERE workspace_id IS NULL — narrower than the
per-folder uniqueness pages and folders got — and removing workspaces left
that predicate matching nothing.

The visible consequence was in agent_runtime.query_table, which resolved a
table by name and took the first match ordered by updated_at DESC. Two tables
called "Notes" meant an agent silently read a different one week to week.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import table_service

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[dict, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, UUID(body["id"])


async def test_second_table_with_the_same_name_is_rejected(client: AsyncClient):
    """The database, not just the router, is what enforces this — a second
    writer racing the first must lose too."""
    _, owner_id = await _register(client)
    await table_service.create_table(owner_id, "Notes", "", [], owner_id)

    with pytest.raises(table_service.DuplicateTableName):
        await table_service.create_table(owner_id, "Notes", "", [], owner_id)


async def test_interactive_create_reports_the_collision(client: AsyncClient):
    """A person naming a table should hear that it's taken rather than be
    handed 'Notes (2)' they didn't ask for."""
    headers, _ = await _register(client)
    payload = {"name": "Notes", "description": "", "columns": []}

    first = await client.post("/api/v1/me/tables", json=payload, headers=headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/me/tables", json=payload, headers=headers)
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


async def test_side_effect_creates_pick_the_next_free_name(client: AsyncClient):
    """Uploading the same spreadsheet twice shouldn't fail — it should behave
    like uploading the same document twice does for pages."""
    _, owner_id = await _register(client)

    first = await table_service.create_table_unique(owner_id, "sales", "", [], owner_id)
    second = await table_service.create_table_unique(owner_id, "sales", "", [], owner_id)
    third = await table_service.create_table_unique(owner_id, "sales", "", [], owner_id)

    assert [first["name"], second["name"], third["name"]] == ["sales", "sales (2)", "sales (3)"]


async def test_same_name_in_different_folders_is_allowed(client: AsyncClient):
    """Uniqueness is per folder, not global — the same shape as pages."""
    from backend.services import files_tree_service

    _, owner_id = await _register(client)
    a = await files_tree_service.create_folder(owner_id, "A", owner_id)
    b = await files_tree_service.create_folder(owner_id, "B", owner_id)

    in_a = await table_service.create_table(owner_id, "Notes", "", [], owner_id, folder_id=a["id"])
    in_b = await table_service.create_table(owner_id, "Notes", "", [], owner_id, folder_id=b["id"])
    assert in_a["id"] != in_b["id"]
