"""Skill lifecycle surfaces under the stored-membership model.

Publishing, forking, and deleting used to confer or revoke skill-ness as a
side effect of writing or removing a SKILL.md. These pin the behaviour now
that membership is a flag: each path carries it deliberately, and a deleted
skill does not return when one of
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


async def _corrupt_skill(scope, pool, name):
    """Simulate pre-migration storage so recovery paths remain covered."""
    folder = await files_tree_service.create_skill(
        scope,
        scope,
        name,
        "Use when testing skill lifecycle surfaces.",
        "Follow this skill's steps.",
    )
    await pool.execute(
        "UPDATE pages SET deleted_at = now() WHERE folder_id = $1 AND name = 'SKILL.md'",
        folder["id"],
    )
    return folder


@pytest.mark.asyncio
async def test_publishing_a_draft_gives_it_instructions(scope, _db_pool):
    folder = await _corrupt_skill(scope, _db_pool, "Draft to publish")

    await shared_skill_service.publish_folder(
        scope, scope, folder["id"], title="Draft to publish", description="d"
    )

    [published] = await skill_service.list_skills(scope, scope)
    assert published["name"] == "Draft to publish"


@pytest.mark.asyncio
async def test_forking_carries_membership_into_the_new_scope(scope, _db_pool):
    folder = await _corrupt_skill(scope, _db_pool, "Draft to fork")
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
async def test_curated_knowledge_uses_the_normal_skill_lifecycle(scope, _db_pool):
    knowledge = await files_tree_service.get_or_create_curated_skill(scope, scope)
    listed = await skill_service.list_skills(scope, scope)
    assert [s["folder_id"] for s in listed] == [str(knowledge["id"])]
    assert listed[0]["published"] is None
    nested = await files_tree_service.create_folder(scope, "Projects", scope, knowledge["id"])
    page = await files_tree_service.create_page(
        scope, "Decision", scope, folder_id=nested["id"], content="Keep the original context."
    )
    await files_tree_service.create_page(
        scope,
        "Reference",
        scope,
        folder_id=nested["id"],
        content_type="html",
        content_html="<p>Retain rich text.</p>",
    )
    read = await skill_service.read_skill(scope, str(knowledge["id"]), scope)
    assert any(
        f["name"] == "Projects/Decision" and f["id"] == str(page["id"]) for f in read["files"]
    )
    assert "Keep the original context." in read["combined"]
    assert "<p>Retain rich text.</p>" in read["combined"]
    contents = await shared_skill_service.folder_contents({"folder_id": knowledge["id"]})
    assert any(
        p["name"] == "Decision" and p["folder_path"] == ["Projects"] for p in contents["pages"]
    )
    await _db_pool.execute("UPDATE folders SET agent_enabled=false WHERE id=$1", knowledge["id"])
    assert await skill_service.list_skills(scope, scope) == []
    assert len(await skill_service.list_skills(scope, scope, include_disabled=True)) == 1
    await _db_pool.execute("UPDATE folders SET agent_enabled=true WHERE id=$1", knowledge["id"])
    published = await shared_skill_service.publish_folder(
        scope, scope, knowledge["id"], title="Learned knowledge", description="d"
    )
    assert published["folder_id"] == knowledge["id"]


@pytest.mark.asyncio
async def test_restoring_a_page_does_not_resurrect_a_deleted_skill(scope, _db_pool):
    """Deleting a skill hard-deletes the folder row; its pages land in trash
    with a null folder. Restoring one must not bring the skill back."""
    folder = await files_tree_service.create_skill(
        scope, scope, "Doomed", "Use when testing skill deletion.", "Follow this skill's steps."
    )
    page_id = await _db_pool.fetchval(
        "SELECT id FROM pages WHERE folder_id = $1 AND name = 'SKILL.md'", folder["id"]
    )

    assert await files_tree_service.delete_folder(folder["id"], scope, scope) is True
    assert await files_tree_service.restore_page(page_id, scope, scope) is True

    assert await skill_service.list_skills(scope, scope) == []
