"""Memory and Clips can't be renamed, moved, or deleted.

Both are resolved by identity — Memory by its flag, Clips by name at the scope
root — and written into by code the user never sees. Renaming one doesn't fail
loudly; the next write recreates it and the user's saves start landing in a
folder they aren't looking at. Deleting Clips takes every clip with it.

Guarded in the service rather than the router, because the UI is not the only
caller: the CLI, the VFS, and the agent's own tools all reach these functions.
"""

from uuid import UUID

import pytest

from backend.services import clip_service, files_tree_service

from .conftest import unique_name


async def _user(client) -> dict:
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = response.json()
    # UUID, not the raw string: create_folder compares the parent's owner to
    # this value in Python, and a str never equals a UUID.
    return {"id": UUID(body["id"]), "headers": {"Authorization": f"Bearer {body['api_key']}"}}


async def test_memory_folder_refuses_rename_move_and_delete(client, pool):
    user = await _user(client)
    owner = user["id"]
    memory = await files_tree_service.get_or_create_memory_folder(owner, owner)

    with pytest.raises(ValueError, match="can't be renamed"):
        await files_tree_service.update_folder(memory["id"], owner, name="Notes")
    with pytest.raises(ValueError, match="can't be renamed"):
        await files_tree_service.delete_folder(memory["id"], owner, owner)

    assert await pool.fetchval("SELECT name FROM folders WHERE id = $1", memory["id"]) == "Memory"


async def test_clips_folder_refuses_rename_move_and_delete(client, pool):
    user = await _user(client)
    owner = user["id"]
    clips_id = await clip_service.clips_folder_id(owner, owner)

    with pytest.raises(ValueError, match="can't be renamed"):
        await files_tree_service.update_folder(clips_id, owner, name="Bookmarks")
    with pytest.raises(ValueError, match="can't be renamed"):
        await files_tree_service.delete_folder(clips_id, owner, owner)

    assert await pool.fetchval("SELECT name FROM folders WHERE id = $1", clips_id) == "Clips"


async def test_the_refusal_names_the_folder(client):
    """ "the Clips folder can't be renamed" — a message that says only "this
    folder is protected" leaves the user guessing which one they hit."""
    user = await _user(client)
    owner = user["id"]
    clips_id = await clip_service.clips_folder_id(owner, owner)

    with pytest.raises(ValueError, match="the Clips folder"):
        await files_tree_service.update_folder(clips_id, owner, name="Bookmarks")


async def test_moving_clips_under_another_folder_is_refused(client, pool):
    """A move is as damaging as a rename: clip_service finds Clips at the scope
    root, so a nested one is invisible to it and the next save makes a new one."""
    user = await _user(client)
    owner = user["id"]
    clips_id = await clip_service.clips_folder_id(owner, owner)
    parent = await files_tree_service.create_folder(owner, "Archive", owner)

    with pytest.raises(ValueError, match="can't be renamed"):
        await files_tree_service.update_folder(clips_id, owner, parent_folder_id=parent["id"])

    assert (
        await pool.fetchval("SELECT parent_folder_id FROM folders WHERE id = $1", clips_id) is None
    )


async def test_an_ordinary_folder_is_still_freely_editable(client, pool):
    """The guard must not creep: only the structural folders are protected."""
    user = await _user(client)
    owner = user["id"]
    folder = await files_tree_service.create_folder(owner, "Notes", owner)

    await files_tree_service.update_folder(folder["id"], owner, name="Renamed")
    assert await pool.fetchval("SELECT name FROM folders WHERE id = $1", folder["id"]) == "Renamed"

    assert await files_tree_service.delete_folder(folder["id"], owner, owner)


async def test_a_nested_folder_named_clips_is_not_protected(client, pool):
    """Protection follows the folder the product actually writes to, not the
    name — someone else's "Clips" inside their own tree is theirs."""
    user = await _user(client)
    owner = user["id"]
    parent = await files_tree_service.create_folder(owner, "Archive", owner)
    mine = await files_tree_service.create_folder(
        owner, "Clips", owner, parent_folder_id=parent["id"]
    )

    await files_tree_service.update_folder(mine["id"], owner, name="Old clips")

    assert await pool.fetchval("SELECT name FROM folders WHERE id = $1", mine["id"]) == "Old clips"


async def test_the_api_reports_which_folders_are_protected(client):
    """The client hides Rename/Delete on these, so the flag has to reach it —
    otherwise the UI offers an action whose only outcome is an error."""
    user = await _user(client)
    await clip_service.clips_folder_id(user["id"], user["id"])
    await files_tree_service.create_folder(user["id"], "Notes", user["id"])

    tree = await client.get("/api/v1/me/tree", headers=user["headers"])

    by_name = {f["name"]: f for f in tree.json()["folders"]}
    assert by_name["Clips"]["is_protected"] is True
    assert by_name["Notes"]["is_protected"] is False
