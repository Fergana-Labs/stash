"""Default skills: loaded from disk, seeded per scope, backfilled later.

Two properties matter and are easy to lose:

  - the seed content is the markdown on disk, not a copy that can drift from
    it (the landing-page demo embeds the slides skill and must not fork it);
  - adding a skill directory reaches existing users, not just new signups —
    seeding runs at signup, so without a backfill every skill added after
    launch would only ever exist for people who joined afterwards.
"""

from pathlib import Path
from uuid import UUID

from httpx import AsyncClient

from backend.services import skill_seeds
from backend.tasks import skill_backfill

from .conftest import unique_name


async def _register(client: AsyncClient) -> UUID:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    return UUID(resp.json()["id"])


def test_skills_are_read_from_disk():
    """The directory is the source of truth — a skill is added by adding a
    folder, with no code change."""
    names = [name for name, _ in skill_seeds.default_skills()]
    assert {"brief", "resurface", "overview", "cleanup"} <= set(names)
    assert {"slides", "briefing", "study-guide", "timeline"} <= set(names)

    on_disk = {p.parent.name for p in Path(skill_seeds.SKILLS_DIR).glob("*/SKILL.md")}
    assert set(names) == on_disk


def test_every_skill_declares_its_frontmatter():
    """`when_to_use` is what an agent routes on; a skill without it is
    invisible in practice even though it seeds fine."""
    for name, body in skill_seeds.default_skills():
        assert body.startswith("---\n"), f"{name} has no frontmatter"
        head = body.split("---", 2)[1]
        for field in ("name:", "description:", "when_to_use:"):
            assert field in head, f"{name} is missing {field}"


def test_demo_embeds_the_same_slides_bytes():
    """The landing-page demo ships the slides skill inline. It must be the
    same bytes users get, or the demo teaches a format we don't seed."""
    from backend.services import demo_content

    assert demo_content.SLIDES_SKILL_MARKDOWN == skill_seeds.skill_markdown("slides")


async def test_new_scope_gets_every_default_skill(client: AsyncClient, pool, monkeypatch):
    monkeypatch.delenv(skill_seeds.DISABLE_ENV_VAR, raising=False)
    owner_id = await _register(client)
    await skill_seeds.seed_default_skills(owner_id, owner_id)

    folders = await pool.fetch(
        "SELECT DISTINCT lower(f.name) AS name FROM folders f JOIN pages p ON p.folder_id = f.id "
        "WHERE f.owner_user_id = $1 AND p.name = 'SKILL.md' AND p.deleted_at IS NULL",
        owner_id,
    )
    got = {r["name"] for r in folders}
    assert {name for name, _ in skill_seeds.default_skills()} <= got


async def test_backfill_reaches_a_scope_that_predates_a_skill(
    client: AsyncClient, pool, monkeypatch
):
    """The regression this guards: a skill added after launch must reach
    people who signed up before it, not only new accounts."""
    monkeypatch.delenv(skill_seeds.DISABLE_ENV_VAR, raising=False)
    owner_id = await _register(client)
    await skill_seeds.seed_default_skills(owner_id, owner_id)

    # Simulate a scope created before `cleanup` existed.
    await pool.execute(
        "DELETE FROM pages WHERE folder_id IN "
        "  (SELECT id FROM folders WHERE owner_user_id = $1 AND lower(name) = 'cleanup')",
        owner_id,
    )
    await pool.execute(
        "DELETE FROM folders WHERE owner_user_id = $1 AND lower(name) = 'cleanup'", owner_id
    )

    assert await skill_backfill._reconcile() >= 1

    restored = await pool.fetchval(
        "SELECT count(*) FROM folders f JOIN pages p ON p.folder_id = f.id "
        "WHERE f.owner_user_id = $1 AND lower(f.name) = 'cleanup' AND p.name = 'SKILL.md'",
        owner_id,
    )
    assert restored == 1


async def test_backfill_is_a_no_op_for_a_complete_scope(client: AsyncClient, monkeypatch):
    """It runs hourly, so a scope that already has everything must cost one
    query and no writes."""
    monkeypatch.delenv(skill_seeds.DISABLE_ENV_VAR, raising=False)
    owner_id = await _register(client)
    await skill_seeds.seed_default_skills(owner_id, owner_id)

    assert await skill_seeds.seed_default_skills(owner_id, owner_id) == 0
