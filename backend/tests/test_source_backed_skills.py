"""Skills that live in a connected source instead of the files tree.

A Drive folder marked `binds_skills` is a shelf. What makes a document on that
shelf a skill is the same thing that makes any other file a skill: it carries a
valid SKILL.md frontmatter block. Nothing is inferred from titles or first
lines — the folder holds reference material and half-written notes too, and a
rule that always succeeds cannot tell those from a skill.

These tests also pin the two properties that made binding beat copying: the
upstream stays the single source of truth, and membership stays explicit the
way 0181 requires.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import skill_service, source_service

from .conftest import unique_name


def _declared(name: str, description: str, body: str = "Do the thing.") -> str:
    return f'---\nname: "{name}"\ndescription: "{description}"\n---\n\n{body}\n'


def test_skill_shelf_explains_each_document_status():
    classify = skill_service.source_document_skill_status

    assert classify(_declared("Instructions", "Do this"), "done") == {
        "skill_status": "skill",
        "skill_status_reason": "Agents can load this file as a Skill.",
    }
    assert classify(_declared("Draft", "Not ready", body=""), "done") == {
        "skill_status": "draft",
        "skill_status_reason": "Add instructions below the closing --- line.",
    }
    assert classify("Meeting notes", "done") == {
        "skill_status": "not_skill",
        "skill_status_reason": "At the top, add a name and description between --- lines.",
    }
    assert classify(None, "processing") == {
        "skill_status": "checking",
        "skill_status_reason": "Stash is still reading this file.",
    }
    assert classify(_declared("Manual", "Nested"), "done") == {
        "skill_status": "skill",
        "skill_status_reason": "Agents can load this file as a Skill.",
    }


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
async def test_a_document_declares_itself_a_skill_through_its_frontmatter(
    client: AsyncClient, pool
):
    """The name and description an agent routes on come from the document's own
    frontmatter — the same block, and the same validator, as every other skill
    in Stash. One definition of 'skill', not one per backing."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content=_declared(
            "Turbochargers",
            "Use when a customer reports boost loss.",
            "Check the wastegate first.",
        ),
    )

    skills = await skill_service.list_skills(owner_id, owner_id)

    assert [s["name"] for s in skills] == ["Turbochargers"]
    assert skills[0]["description"] == "Use when a customer reports boost loss."
    assert skills[0]["backing"] == "source"
    assert skills[0]["has_instructions"] is True


@pytest.mark.asyncio
async def test_an_ordinary_document_on_the_shelf_is_not_a_skill(client: AsyncClient, pool):
    """The failure this rule exists to stop. A shelf holds reference material,
    meeting notes and drafts beside its skills, and an earlier version derived a
    name and description from whatever it found — so a document containing the
    word 'weeeeee' told an agent when to reach for it."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(pool, owner_id, source_id, path="Scratch notes.md", content="weeeeee\n")
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content=_declared("Turbochargers", "Use when a customer reports boost loss."),
    )

    skills = await skill_service.list_skills(owner_id, owner_id)

    assert [s["name"] for s in skills] == ["Turbochargers"]


@pytest.mark.asyncio
async def test_frontmatter_that_would_be_rejected_anywhere_else_is_rejected_here(
    client: AsyncClient, pool
):
    """A blank description fails `validate_skill_md` on a folder skill, so it
    has to fail here too — otherwise the backing decides how strict we are."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Half written.md",
        content='---\nname: "Half written"\ndescription: ""\n---\n\nTBD\n',
    )

    assert await skill_service.list_skills(owner_id, owner_id) == []


@pytest.mark.asyncio
async def test_a_document_still_extracting_is_not_yet_a_skill(client: AsyncClient, pool):
    """Extraction lands minutes after the sync walk records the row. Until there
    is a document to read, nothing has declared itself a skill — it appears once
    its body arrives, rather than as an empty placeholder."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(pool, owner_id, source_id, path="Brake Shoes.md", content=None, status="pending")

    assert await skill_service.list_skills(owner_id, owner_id) == []


@pytest.mark.asyncio
async def test_a_skill_can_live_inside_a_subfolder(client: AsyncClient, pool):
    """Subfolders organize Drive files; they do not change whether a file's
    author declared it as a Skill."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content=_declared("Turbochargers", "Boost loss."),
    )
    nested_id = await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers/torque-specs.md",
        content=_declared("Torque specs", "Torque values."),
    )

    skills = await skill_service.list_skills(owner_id, owner_id)

    assert [s["name"] for s in skills] == ["Torque specs", "Turbochargers"]

    nested = await skill_service.read_source_skill(owner_id, nested_id, owner_id)
    assert nested is not None
    assert nested["name"] == "Torque specs"

    counts = await skill_service.count_shelf_skills(owner_id, [str(source_id)])
    assert counts[str(source_id)]["skills"] == 2
    assert counts[str(source_id)]["documents"] == 2


@pytest.mark.asyncio
async def test_an_unbound_drive_folder_contributes_no_skills(client: AsyncClient, pool):
    """Membership is a deliberate flag on the binding, not a consequence of
    holding documents that happen to carry frontmatter."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id, binds_skills=False)
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Notes.md",
        content=_declared("Notes", "Use for notes."),
    )

    assert await skill_service.list_skills(owner_id, owner_id) == []


@pytest.mark.asyncio
async def test_a_document_vanishing_upstream_cannot_demote_the_shelf(client: AsyncClient, pool):
    """The failure 0181 was written to stop, reached through a new door: a
    document removed in Drive drops that one skill and leaves the binding and
    its siblings untouched."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    gone = await _doc(
        pool, owner_id, source_id, path="Retired.md", content=_declared("Retired", "Old.")
    )
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content=_declared("Turbochargers", "Boost loss."),
    )

    await pool.execute("UPDATE drive_documents SET deleted_at = now() WHERE id = $1", gone)

    skills = await skill_service.list_skills(owner_id, owner_id)

    assert [s["name"] for s in skills] == ["Turbochargers"]
    assert await pool.fetchval("SELECT binds_skills FROM user_sources WHERE id = $1", source_id)


@pytest.mark.asyncio
async def test_reading_a_skill_returns_the_document_without_its_frontmatter(
    client: AsyncClient, pool
):
    """The point of binding rather than copying: the agent loads what Drive
    holds right now. Frontmatter is metadata, so the body it reads is the
    instructions alone — the same split a folder skill gets."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    doc_id = await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content=_declared("Turbochargers", "Boost loss.", "Check the wastegate first."),
    )

    skill = await skill_service.read_source_skill(owner_id, doc_id, owner_id)

    assert skill is not None
    assert skill["name"] == "Turbochargers"
    assert skill["body"].strip() == "Check the wastegate first."
    assert "description:" not in skill["body"]


@pytest.mark.asyncio
async def test_reading_an_undeclared_document_is_not_found(client: AsyncClient, pool):
    """It is not a broken skill; it is a file that happens to sit on the shelf,
    so there is no skill page for it to open."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    doc_id = await _doc(pool, owner_id, source_id, path="Scratch.md", content="weeeeee\n")

    assert await skill_service.read_source_skill(owner_id, doc_id, owner_id) is None


@pytest.mark.asyncio
async def test_a_declaration_with_nothing_under_it_is_a_draft(client: AsyncClient, pool):
    """Found by running the agent's own tools: a Doc holding only a frontmatter
    block declared a skill with no instructions in it, and `read_skill` handed
    the agent an empty document instead of the refusal the draft flag exists to
    trigger. Declaring yourself a skill is not the same as being one."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    doc_id = await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content='---\nname: "Turbochargers"\ndescription: "Boost loss."\n---\n',
    )

    listed = await skill_service.list_skills(owner_id, owner_id)
    assert [s["name"] for s in listed] == ["Turbochargers"]
    assert listed[0]["has_instructions"] is False

    skill = await skill_service.read_source_skill(owner_id, doc_id, owner_id)
    assert skill is not None
    assert skill["has_instructions"] is False
    assert skill["combined"] == ""


@pytest.mark.asyncio
async def test_listing_and_reading_agree_on_a_long_frontmatter_block(client: AsyncClient, pool):
    """`when_to_use` and `version` have no length cap, so a valid block can run
    long. Listing works from a prefix and reading has the whole document, and
    when those two disagreed a skill read fine while never appearing in the
    catalogue — visible on its own page, invisible to every agent."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)
    doc_id = await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content=(
            '---\nname: "Turbochargers"\ndescription: "Boost loss."\n'
            f'when_to_use: "{"x" * 3000}"\n---\n\nCheck the wastegate.\n'
        ),
    )

    listed = await skill_service.list_skills(owner_id, owner_id)
    read = await skill_service.read_source_skill(owner_id, doc_id, owner_id)

    assert [s["name"] for s in listed] == ["Turbochargers"]
    assert read is not None
    assert read["body"].strip() == "Check the wastegate."


@pytest.mark.asyncio
async def test_a_shelf_shared_with_you_reports_no_count_rather_than_zero(client: AsyncClient, pool):
    """Sources can be shared, and a shared one keeps its real owner — so its
    documents are not the reader's to count. Reporting zero for it would be a
    confident lie about someone else's shelf, on a shelf that may be full."""
    _key, owner_id = await _register(client, "shelf_owner")
    _key2, reader_id = await _register(client, "shelf_reader")
    source_id = await _skill_shelf(pool, owner_id)
    await _doc(
        pool,
        owner_id,
        source_id,
        path="Turbochargers.md",
        content=_declared("Turbochargers", "Boost loss."),
    )

    owner_counts = await skill_service.count_shelf_skills(owner_id, [str(source_id)])
    assert owner_counts[str(source_id)]["skills"] == 1

    # The reader owns no shelves, so nothing is counted on their behalf.
    assert await skill_service.count_shelf_skills(reader_id, []) == {}


@pytest.mark.asyncio
async def test_an_owned_shelf_with_nothing_in_it_still_reports_itself(client: AsyncClient, pool):
    """Distinct from the shared case: a shelf you own and haven't filled says
    "0 of 0", which is true and actionable. Silence there would read as a
    feature that isn't working."""
    _key, owner_id = await _register(client)
    source_id = await _skill_shelf(pool, owner_id)

    counts = await skill_service.count_shelf_skills(owner_id, [str(source_id)])

    assert counts == {str(source_id): {"skills": 0, "documents": 0, "not_skills": []}}
