"""Stash-authored Skill drafts are docs, never per-user seeds."""

from pathlib import Path

from httpx import AsyncClient

from backend.services import skill_service

from .conftest import unique_name

SKILL_DOCS = Path(__file__).resolve().parents[2] / "docs" / "skills"
SKILL_NAMES = ("brief", "cleanup", "overview", "resurface", "slides")


def test_every_documented_skill_has_routing_metadata():
    assert {path.parent.name for path in SKILL_DOCS.glob("*/SKILL.md")} == set(SKILL_NAMES)
    for name in SKILL_NAMES:
        metadata, body = skill_service.parse_frontmatter(
            (SKILL_DOCS / name / "SKILL.md").read_text()
        )
        assert metadata["name"] == name
        assert metadata["description"]
        assert metadata["when_to_use"]
        assert body.strip()


async def test_new_accounts_do_not_receive_built_in_skills(client: AsyncClient):
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    headers = {"Authorization": f"Bearer {response.json()['api_key']}"}

    skills = await client.get("/api/v1/me/skills", headers=headers)

    assert skills.status_code == 200
    assert skills.json()["skills"] == []
