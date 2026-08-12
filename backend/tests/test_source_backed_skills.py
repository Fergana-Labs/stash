"""Skills that live in a connected source instead of the files tree.

A Drive folder marked `binds_skills` is a shelf: each document sitting directly
in it is one skill, read straight from `drive_documents`. These tests encode the
two properties that made us choose this over copying documents into the files
tree — the upstream stays the single source of truth, and membership stays
explicit the way 0181 requires.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import skill_service, source_service

from .conftest import unique_name


async def _register(client: AsyncClient, prefix: str = "srcskill") -> tuple[str, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(prefix), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], UUID(body["id"])


async def _skill_shelf(pool, owner_id: UUID, *, binds_skills: bool = True) -> UUID:
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive_folder",
        external_ref="drive-folder-skills",
        display_name="Heavi Skills",
        settings={},
    )
    source_id = UUID(source["id"])
    await pool.execute(
        "UPDATE user_sources SET binds_skills = $2 WHERE id = $1",
        source_id,
        binds_skills,
    )
    return source_id


async def _doc(
    pool,
    owner_id: UUID,
    source_id: UUID,
    *,
    path: str,
    content: str | None,
    status: str = "done",
) -> UUID:
    return await pool.fetchval(
        "INSERT INTO drive_documents "
        "  (owner_user_id, source_id, path, name, external_ref, content, extraction_status) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        owner_id,
        source_id,
        path,
        path.rpartition("/")[2],
        f"drive-{path}",
        content,
        status,
    )


@pytest.mark.asyncio
async def test_document_title_and_first_prose_line_become_the_skill_metadata(
    client: AsyncClient, pool
):
    """The authoring contract we ask a Drive-authoring team to follow.

    A Google Doc has no frontmatter, so the skill's two required fields have to
    come out of the document: its title names the skill, and its first prose
    line says when to reach for it. The exported Title style lands as an `#`
    heading that merely repeats the name, so it cannot be the description."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content="# Turbochargers\n\nUse when a customer reports boost loss.\n\nSteps: ...",
    )

    skills = await skill_service.list_skills(owner_id, owner_id)

    assert [s["name"] for s in skills] == ["Turbochargers"]
    assert skills[0]["description"] == "Use when a customer reports boost loss."
    assert skills[0]["backing"] == "source"
    assert skills[0]["has_instructions"] is True


@pytest.mark.asyncio
async def test_a_document_still_extracting_is_a_draft_not_an_invented_description(
    client: AsyncClient, pool
):
    """Extraction lands minutes after the sync walk records the row. Until it
    does there is no honest description to show, and guessing one would be a
    routing instruction we made up. It lists as a draft instead — the same
    shape a folder skill with no SKILL.md takes."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(pool, owner_id, source_id, path="Brake Shoes.md", content=None, status="pending")

    skills = await skill_service.list_skills(owner_id, owner_id)

    assert skills[0]["name"] == "Brake Shoes"
    assert skills[0]["description"] == ""
    assert skills[0]["has_instructions"] is False


@pytest.mark.asyncio
async def test_only_documents_sitting_directly_in_the_shelf_are_skills(client: AsyncClient, pool):
    """A nested document is reference material belonging to a shelf, not a
    shelf of its own — otherwise every attachment becomes a skill the agent
    has to route past."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(pool, owner_id, source_id, path="Turbochargers.md", content="Boost loss.")
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers/torque-specs.md",
        content="Torque specs.",
    )

    skills = await skill_service.list_skills(owner_id, owner_id)

    assert [s["name"] for s in skills] == ["Turbochargers"]


@pytest.mark.asyncio
async def test_an_unbound_drive_folder_contributes_no_skills(client: AsyncClient, pool):
    """Membership is a deliberate flag on the binding, not a consequence of
    having documents. Connecting a Drive folder must never quietly fill an
    agent's skill catalogue with whatever is in it."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id, binds_skills=False)
    await _doc(pool, owner_id, source_id, path="Notes.md", content="Some notes.")

    assert await skill_service.list_skills(owner_id, owner_id) == []


@pytest.mark.asyncio
async def test_a_document_vanishing_upstream_cannot_demote_the_shelf(client: AsyncClient, pool):
    """The failure 0181 was written to stop, reached through a new door: a
    document removed in Drive drops that one skill and leaves the binding and
    its siblings untouched. Tidying a Drive folder can never empty the shelf."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    gone = await _doc(pool, owner_id, source_id, path="Retired.md", content="Retired.")
    await _doc(pool, owner_id, source_id, path="Turbochargers.md", content="Boost loss.")

    await pool.execute("UPDATE drive_documents SET deleted_at = now() WHERE id = $1", gone)

    skills = await skill_service.list_skills(owner_id, owner_id)

    assert [s["name"] for s in skills] == ["Turbochargers"]
    assert await pool.fetchval("SELECT binds_skills FROM user_sources WHERE id = $1", source_id)


@pytest.mark.asyncio
async def test_reading_a_source_backed_skill_returns_the_upstream_document(
    client: AsyncClient, pool
):
    """The point of binding rather than copying: the agent loads what Drive
    holds right now, with no snapshot in between to drift."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content="Use on boost loss.\n\nCheck the wastegate first.",
    )

    skill = await skill_service.read_skill(owner_id, "Turbochargers", owner_id)

    assert skill is not None
    assert skill["backing"] == "source"
    assert "Check the wastegate first." in skill["body"]
    assert skill["has_instructions"] is True
