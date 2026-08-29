"""Two ways a user gets a Skill without waiting for curation: installing one
from the bootstrap catalog, and asking for one in plain language. Both must
produce a real, valid, listed Skill — the catalog is only useful if every
entry installs cleanly, and a request is only useful if the draft becomes
something the user can open and edit."""

import pytest
from httpx import AsyncClient

from backend.services import llm, skill_service, suggested_skills
from backend.tests.conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("skills"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def test_every_catalog_entry_is_a_valid_skill():
    keys = [entry["key"] for entry in suggested_skills.catalog()]
    assert len(keys) == len(set(keys))
    for entry in suggested_skills.catalog():
        skill_service.validate_skill_md(
            skill_service.skill_md(entry["name"], entry["description"], entry["instructions"])
        )


@pytest.mark.asyncio
async def test_installing_a_suggestion_creates_the_skill_and_marks_it_installed(client):
    key = await _register(client)

    listed = await client.get("/api/v1/me/skills/suggestions", headers=_auth(key))
    assert listed.status_code == 200
    glossary = next(s for s in listed.json()["suggestions"] if s["key"] == "company-glossary")
    assert glossary["installed"] is False

    created = await client.post(
        "/api/v1/me/skills/suggestions/company-glossary", headers=_auth(key)
    )
    assert created.status_code == 201
    folder_id = created.json()["folder_id"]

    skills = (await client.get("/api/v1/me/skills", headers=_auth(key))).json()["skills"]
    [installed] = [s for s in skills if s["folder_id"] == folder_id]
    assert installed["name"] == "Glossary of your company"
    assert installed["agent_enabled"] is True

    contents = await client.get(f"/api/v1/me/skills/{folder_id}/contents", headers=_auth(key))
    skill_md = next(
        p["content_markdown"]
        for p in contents.json()["contents"]["pages"]
        if p["name"] == "SKILL.md"
    )
    assert "glossary.md" in skill_md

    listed_again = await client.get("/api/v1/me/skills/suggestions", headers=_auth(key))
    glossary = next(s for s in listed_again.json()["suggestions"] if s["key"] == "company-glossary")
    assert glossary["installed"] is True


@pytest.mark.asyncio
async def test_unknown_suggestion_is_404(client):
    key = await _register(client)
    resp = await client.post("/api/v1/me/skills/suggestions/nope", headers=_auth(key))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_requesting_a_skill_creates_it_from_the_draft(client, monkeypatch):
    key = await _register(client)
    seen: dict = {}

    async def fake_complete_json(*, prompt, system, tier, max_tokens):
        seen["prompt"] = prompt
        return {
            "name": "Changelog writer",
            "description": "Write a changelog entry from merged PRs. Use when releasing.",
            "instructions": "## Steps\n1. List merged PRs.\n2. Group by area.\n3. Write one line each.",
        }

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)

    resp = await client.post(
        "/api/v1/me/skills/request",
        json={"request": "I want a skill that writes my changelog from merged PRs"},
        headers=_auth(key),
    )
    assert resp.status_code == 201, resp.text
    assert "changelog from merged PRs" in seen["prompt"]
    folder_id = resp.json()["folder_id"]

    skills = (await client.get("/api/v1/me/skills", headers=_auth(key))).json()["skills"]
    [created] = [s for s in skills if s["folder_id"] == folder_id]
    assert created["name"] == "Changelog writer"
    assert created["description"].startswith("Write a changelog entry")


@pytest.mark.asyncio
async def test_a_draft_without_instructions_is_rejected(client, monkeypatch):
    key = await _register(client)

    async def fake_complete_json(**_):
        return {"name": "Half a skill", "description": "d"}

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)

    resp = await client.post(
        "/api/v1/me/skills/request",
        json={"request": "anything"},
        headers=_auth(key),
    )
    assert resp.status_code == 502
    assert "instructions" in resp.json()["detail"]
