"""Skill membership is stored and explicit, never derived from file contents.

A folder used to be a skill because it contained a live SKILL.md, so ordinary
file edits silently reclassified folders: deleting the file demoted a
customer's skill out of every agent's catalog three times in two weeks, and a
stray SKILL.md could promote Memory into a wipeable "skill". Membership now
changes only through deliberate verbs.
"""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from backend.services import files_tree_service, skill_service


@pytest_asyncio.fixture
async def scope(_db_pool):
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    return user_id


@pytest.mark.asyncio
async def test_dropping_a_skill_md_into_a_folder_does_not_promote_it(scope, _db_pool):
    folder = await files_tree_service.create_folder(scope, "Notes", scope)
    await files_tree_service.create_page(
        scope, "SKILL.md", scope, folder_id=folder["id"], content="# not a skill"
    )

    skills = await skill_service.list_skills(scope, scope)

    assert [s["folder_id"] for s in skills] == []


@pytest.mark.asyncio
async def test_convert_verbs_are_the_only_way_membership_changes(scope, _db_pool):
    folder = await files_tree_service.create_folder(scope, "Recipes", scope)

    promoted = await files_tree_service.set_folder_is_skill(folder["id"], scope, True)
    assert promoted["is_skill"] is True
    assert [s["folder_id"] for s in await skill_service.list_skills(scope, scope)] == [
        str(folder["id"])
    ]

    demoted = await files_tree_service.set_folder_is_skill(folder["id"], scope, False)
    assert demoted["is_skill"] is False
    assert await skill_service.list_skills(scope, scope) == []


@pytest.mark.asyncio
async def test_deleting_skill_md_leaves_a_draft_skill_not_a_silent_demotion(scope, _db_pool):
    """The customer's exact move. Before: the skill vanished from every
    surface with no warning. Now: the delete is refused outright, and even
    forced at the data layer the skill still lists — as a draft."""
    folder = await files_tree_service.create_skill(scope, scope, "Brake Shoes")
    page_id = await _db_pool.fetchval(
        "SELECT id FROM pages WHERE folder_id = $1 AND name = 'SKILL.md'", folder["id"]
    )

    with pytest.raises(ValueError, match="can't be deleted or renamed"):
        await files_tree_service.delete_page(page_id, scope, scope)
    with pytest.raises(ValueError, match="can't be deleted or renamed"):
        await files_tree_service.update_page(page_id, scope, scope, name="notes.md")

    await _db_pool.execute("UPDATE pages SET deleted_at = now() WHERE id = $1", page_id)
    [skill] = await skill_service.list_skills(scope, scope)
    assert skill["folder_id"] == str(folder["id"])
    assert skill["has_instructions"] is False


@pytest.mark.asyncio
async def test_memory_can_never_become_a_skill(scope, _db_pool):
    memory = await files_tree_service.get_or_create_memory_folder(scope, scope)

    with pytest.raises(ValueError, match="can't be turned into a skill"):
        await files_tree_service.set_folder_is_skill(memory["id"], scope, True)

    # And a stray SKILL.md inside it changes nothing.
    await files_tree_service.create_page(
        scope, "SKILL.md", scope, folder_id=memory["id"], content="# stray"
    )
    assert await skill_service.list_skills(scope, scope) == []


@pytest.mark.asyncio
async def test_bulk_write_carrying_a_skill_md_promotes_explicitly(scope, _db_pool):
    """Import/sync is a caller saying "this is a skill" — unlike a user
    editing files inside an existing folder."""
    folder = await files_tree_service.create_folder(scope, "imported-repo", scope)
    await files_tree_service.write_folder_files(
        scope, scope, folder["id"], [("SKILL.md", b"# imported"), ("notes.md", b"context")]
    )

    assert [s["folder_id"] for s in await skill_service.list_skills(scope, scope)] == [
        str(folder["id"])
    ]


@pytest.mark.asyncio
async def test_convert_endpoint_leaves_a_loadable_skill(client, _db_pool):
    """The Convert-to-Skill button's contract: one call promotes the folder
    AND leaves instructions, so the user lands on a skill an agent can load —
    not a draft, and not (as before) a SKILL.md write that no longer promotes
    anything."""
    reg = await client.post(
        "/api/v1/users/register",
        json={"name": f"conv_{uuid4().hex[:8]}", "password": "securepassword1"},
    )
    body = reg.json()
    headers = {"Authorization": f"Bearer {body['api_key']}"}
    owner = UUID(body["id"])

    folder = await client.post("/api/v1/me/folders", json={"name": "Runbooks"}, headers=headers)
    folder_id = folder.json()["id"]

    resp = await client.post(f"/api/v1/me/folders/{folder_id}/convert-to-skill", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_skill"] is True

    listed = (await client.get("/api/v1/me/skills", headers=headers)).json()["skills"]
    [skill] = [s for s in listed if s["folder_id"] == folder_id]
    assert skill["has_instructions"] is True

    # And back again: demotion is equally explicit, contents untouched.
    back = await client.post(f"/api/v1/me/folders/{folder_id}/convert-to-folder", headers=headers)
    assert back.status_code == 200
    assert (await client.get("/api/v1/me/skills", headers=headers)).json()["skills"] == []
    kept = await _db_pool.fetchval(
        "SELECT count(*) FROM pages WHERE folder_id = $1 AND deleted_at IS NULL", UUID(folder_id)
    )
    assert kept == 1
    assert owner


@pytest.mark.asyncio
async def test_folder_plus_skill_md_plus_convert_is_the_cli_recipe(client, _db_pool):
    """What every CLI skill-creating command does: make a folder, write its
    SKILL.md, then say "this is a skill". The middle step alone used to be
    enough, which is why `stash skills create` broke silently when membership
    became a flag — this pins the sequence the CLI depends on."""
    reg = await client.post(
        "/api/v1/users/register",
        json={"name": f"cli_{uuid4().hex[:8]}", "password": "securepassword1"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['api_key']}"}

    folder_id = (
        await client.post("/api/v1/me/folders", json={"name": "cli-skill"}, headers=headers)
    ).json()["id"]
    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "SKILL.md", "folder_id": folder_id, "content": "---\nname: cli-skill\n---\n"},
        headers=headers,
    )

    # Writing the file is not enough — that is the whole point of the flag.
    assert (await client.get("/api/v1/me/skills", headers=headers)).json()["skills"] == []

    convert = await client.post(f"/api/v1/me/folders/{folder_id}/convert-to-skill", headers=headers)
    assert convert.status_code == 200
    listed = (await client.get("/api/v1/me/skills", headers=headers)).json()["skills"]
    assert [s["folder_id"] for s in listed] == [folder_id]
    # Converting did not clobber the instructions the caller just wrote.
    kept = await _db_pool.fetchval(
        "SELECT content_markdown FROM pages WHERE folder_id = $1 AND name = 'SKILL.md'",
        UUID(folder_id),
    )
    assert "name: cli-skill" in kept


@pytest.mark.asyncio
async def test_shared_skill_without_instructions_still_lists(client, _db_pool):
    """A skill shared with you shows up even as a draft. The listing used to
    inner-join SKILL.md, so a shared skill missing instructions vanished
    instead of appearing with has_instructions false."""
    owner = await client.post(
        "/api/v1/users/register",
        json={"name": f"own_{uuid4().hex[:8]}", "password": "securepassword1"},
    )
    owner_h = {"Authorization": f"Bearer {owner.json()['api_key']}"}
    friend = await client.post(
        "/api/v1/users/register",
        json={"name": f"fr_{uuid4().hex[:8]}", "password": "securepassword1"},
    )
    friend_h = {"Authorization": f"Bearer {friend.json()['api_key']}"}

    made = await client.post(
        "/api/v1/me/skills/new", json={"name": "Shared draft"}, headers=owner_h
    )
    folder_id = made.json()["folder_id"]
    # Force the draft state (the delete route refuses, by design).
    await _db_pool.execute(
        "UPDATE pages SET deleted_at = now() WHERE folder_id = $1 AND name = 'SKILL.md'",
        UUID(folder_id),
    )
    await _db_pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "                    principal_id, permission, created_by) "
        "VALUES ($1, 'folder', $2, 'user', $3, 'read', $1)",
        UUID(owner.json()["id"]),
        UUID(folder_id),
        UUID(friend.json()["id"]),
    )

    listed = (await client.get("/api/v1/me/shared-skills", headers=friend_h)).json()
    assert folder_id in [s["folder_id"] for s in listed["skills"]]
