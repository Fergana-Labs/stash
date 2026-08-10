"""Every way to create a skill must produce a skill with instructions.

Skill membership is a stored flag (folders.is_skill) and the instructions are
a page named SKILL.md. Those are two separate writes, so every creation path
has to remember both — and on 2026-08-07 six of them silently forgot: the
three CLI commands, the MCP server tool, the folder-convert button, and the
skill-view demote button all kept writing a SKILL.md into a folder that was
never marked a skill. Each produced an invisible folder instead of a skill,
and each was found by hand, hours apart.

This enumerates the paths so the next one that forgets fails the build
instead of a customer. Adding a way to create a skill means adding it here.
"""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from backend.services import (
    agent_runtime,
    files_tree_service,
    shared_skill_service,
    skill_service,
)


@pytest_asyncio.fixture
async def scope(_db_pool):
    uid = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)", uid, f"u_{uid.hex[:6]}"
    )
    return uid


async def _assert_is_a_usable_skill(scope, folder_id, _db_pool, *, via: str):
    """The two halves of a skill: marked as one, and holding instructions."""
    flagged = await _db_pool.fetchval("SELECT is_skill FROM folders WHERE id = $1", folder_id)
    assert flagged is True, f"{via}: folder was not marked a skill"

    listed = [
        s for s in await skill_service.list_skills(scope, scope) if s["folder_id"] == str(folder_id)
    ]
    assert listed, f"{via}: skill does not appear in the skills listing"
    assert listed[0]["has_instructions"] is True, f"{via}: skill has no SKILL.md"


@pytest.mark.asyncio
async def test_service_create_skill(scope, _db_pool):
    """What the web New-skill button and POST /me/skills/new call."""
    folder = await files_tree_service.create_skill(
        scope, scope, "Via create_skill", "Use when testing the service create path."
    )
    await _assert_is_a_usable_skill(scope, folder["id"], _db_pool, via="create_skill")


@pytest.mark.asyncio
async def test_convert_a_plain_folder(scope, _db_pool):
    """The Convert-to-Skill button on a folder page."""
    folder = await files_tree_service.create_folder(scope, "Plain", scope)
    await files_tree_service.set_folder_is_skill(folder["id"], scope, True)
    await shared_skill_service.ensure_skill_md(
        scope, folder["id"], scope, "Plain", "Use when testing folder conversion."
    )
    await _assert_is_a_usable_skill(scope, folder["id"], _db_pool, via="convert-to-skill")


@pytest.mark.asyncio
async def test_publishing_a_folder(scope, _db_pool):
    """Publishing is also a promotion path — it makes a folder a shared skill."""
    folder = await files_tree_service.create_folder(scope, "To publish", scope)
    await shared_skill_service.publish_folder(
        scope, scope, folder["id"], title="To publish", description="d"
    )
    await _assert_is_a_usable_skill(scope, folder["id"], _db_pool, via="publish_folder")


@pytest.mark.asyncio
async def test_forking_into_another_scope(scope, _db_pool):
    """`stash skills install` and the Discover fork button land here."""
    source = await files_tree_service.create_skill(
        scope, scope, "Forkable", "Use when testing skill forking."
    )
    published = await shared_skill_service.publish_folder(
        scope, scope, source["id"], title="Forkable", description="d"
    )
    other = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        other,
        f"o_{other.hex[:6]}",
    )

    forked = await shared_skill_service.fork_skill(other, published["slug"], other)

    assert forked is not None
    await _assert_is_a_usable_skill(other, UUID(forked["folder_id"]), _db_pool, via="fork_skill")


@pytest.mark.asyncio
async def test_bulk_file_write(scope, _db_pool):
    """GitHub import and `stash skills sync` push both write a file set that
    carries a SKILL.md — the folder must come out marked."""
    folder = await files_tree_service.create_folder(scope, "imported", scope)
    await files_tree_service.write_folder_files(
        scope, scope, folder["id"], [("SKILL.md", b"---\nname: imported\n---\n"), ("ref.md", b"x")]
    )
    await _assert_is_a_usable_skill(scope, folder["id"], _db_pool, via="write_folder_files")


@pytest.mark.asyncio
async def test_agent_create_skill_tool(scope, _db_pool):
    """The tool the ask-the-stash loop calls."""
    import json

    scope_token = agent_runtime._scope_ctx.set(scope)
    user_token = agent_runtime._user_ctx.set(scope)
    try:
        created = json.loads(
            (
                await agent_runtime._create_skill.handler(
                    {"name": "Via agent", "skill_md": "---\nname: Via agent\n---\n\n# go\n"}
                )
            )["content"][0]["text"]
        )
    finally:
        agent_runtime._user_ctx.reset(user_token)
        agent_runtime._scope_ctx.reset(scope_token)

    assert "error" not in created, created
    await _assert_is_a_usable_skill(
        scope, UUID(created["folder_id"]), _db_pool, via="agent create_skill"
    )


def test_the_client_side_paths_all_call_the_convert_verb():
    """The CLI (three commands) and the MCP server create skills over HTTP, so
    they can't be exercised here — but each must call the convert verb after
    writing SKILL.md, because writing the file confers nothing. Missing this
    is exactly how all four broke. Asserted by source inspection."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for rel, expected in (("cli/main.py", 3), ("cli/mcp_server.py", 1)):
        source = (root / rel).read_text()
        found = source.count("convert_folder_to_skill(")
        assert found >= expected, (
            f"{rel}: expected at least {expected} convert_folder_to_skill call(s), found {found}. "
            "A path that writes SKILL.md without converting creates a folder, not a skill."
        )
