"""Skill lifecycle surfaces under the stored-membership model.

Publishing, forking, and deleting used to confer or revoke skill-ness as a
side effect of writing or removing a SKILL.md. These pin the behaviour now
that membership is a flag: each path carries it deliberately, protected
folders can never acquire it, and a deleted skill does not return when one of
its trashed pages is restored.
"""

from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import files_tree_service, shared_skill_service, skill_service


@pytest_asyncio.fixture
async def scope(_db_pool):
    uid = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)", uid, f"u_{uid.hex[:6]}"
    )
    return uid


async def _draft_skill(scope, pool, name):
    """A skill whose instructions are missing — the draft state the flag makes
    representable. Forced at the data layer, since the routes refuse it."""
    folder = await files_tree_service.create_skill(
        scope, scope, name, "Use when testing skill lifecycle surfaces."
    )
    await pool.execute(
        "UPDATE pages SET deleted_at = now() WHERE folder_id = $1 AND name = 'SKILL.md'",
        folder["id"],
    )
    return folder


@pytest.mark.asyncio
async def test_publishing_a_draft_gives_it_instructions(scope, _db_pool):
    folder = await _draft_skill(scope, _db_pool, "Draft to publish")

    await shared_skill_service.publish_folder(
        scope, scope, folder["id"], title="Draft to publish", description="d"
    )

    [published] = await skill_service.list_skills(scope, scope)
    assert published["has_instructions"] is True


@pytest.mark.asyncio
async def test_forking_carries_membership_into_the_new_scope(scope, _db_pool):
    folder = await _draft_skill(scope, _db_pool, "Draft to fork")
    pub = await shared_skill_service.publish_folder(
        scope, scope, folder["id"], title="Draft to fork", description="d"
    )
    other = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        other,
        f"o_{other.hex[:6]}",
    )

    forked = await shared_skill_service.fork_skill(other, pub["slug"], other)

    assert forked is not None
    listed = await skill_service.list_skills(other, other)
    assert [s["folder_id"] for s in listed] == [forked["folder_id"]]


@pytest.mark.asyncio
async def test_publishing_cannot_turn_memory_into_a_skill(scope, _db_pool):
    """Publish sets membership, so it is another door onto the protected
    folders — it must refuse them like every other promotion path."""
    memory = await files_tree_service.get_or_create_memory_folder(scope, scope)

    with pytest.raises(ValueError, match="can't be turned into a skill"):
        await shared_skill_service.publish_folder(
            scope, scope, memory["id"], title="Memory", description="d"
        )

    assert await skill_service.list_skills(scope, scope) == []


@pytest.mark.asyncio
async def test_restoring_a_page_does_not_resurrect_a_deleted_skill(scope, _db_pool):
    """Deleting a skill hard-deletes the folder row; its pages land in trash
    with a null folder. Restoring one must not bring the skill back."""
    folder = await files_tree_service.create_skill(
        scope, scope, "Doomed", "Use when testing skill deletion."
    )
    page_id = await _db_pool.fetchval(
        "SELECT id FROM pages WHERE folder_id = $1 AND name = 'SKILL.md'", folder["id"]
    )

    assert await files_tree_service.delete_folder(folder["id"], scope, scope) is True
    assert await files_tree_service.restore_page(page_id, scope, scope) is True

    assert await skill_service.list_skills(scope, scope) == []
