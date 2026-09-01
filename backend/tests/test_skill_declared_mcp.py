"""A skill's `mcp:` frontmatter line becomes a server in the sprite's
.mcp.json, authenticated with the key the turn env carries. Why it matters:
this is how a hosted skill's tools reach the cloud agent without anyone
registering anything, and how they disappear when the skill does."""

from __future__ import annotations

from uuid import UUID

from httpx import AsyncClient

from backend.config import settings
from backend.services import files_tree_service, mcp_server_service, sprite_service

from .conftest import unique_name


async def _register(client: AsyncClient) -> UUID:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("mcpskill"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


async def _skill(user_id: UUID, name: str, mcp_line: str) -> None:
    folder = await files_tree_service.create_folder(user_id, name, user_id)
    await files_tree_service.set_folder_is_skill(folder["id"], user_id, True)
    await files_tree_service.create_page(
        user_id,
        "SKILL.md",
        user_id,
        folder_id=folder["id"],
        content=f"---\nname: {name}\ndescription: d\n{mcp_line}\n---\nbody\n",
    )


def test_parse_declaration():
    assert mcp_server_service.parse_declaration("stylewriter https://api.x/mcp/stylewriter") == (
        "stylewriter",
        "https://api.x/mcp/stylewriter",
    )
    assert mcp_server_service.parse_declaration("") is None
    assert mcp_server_service.parse_declaration("bad name https://x") is None
    assert mcp_server_service.parse_declaration("name ftp://x") is None


async def test_installed_skill_server_lands_in_sprite_config(client):
    user_id = await _register(client)
    await _skill(user_id, "stylewriter", "mcp: stylewriter https://api.x/mcp/stylewriter")
    await _skill(user_id, "brief", 'version: "1"')
    await _skill(user_id, "broken", "mcp: nonsense")

    config = await mcp_server_service.sprite_config(user_id)
    assert set(config["mcpServers"]) == {"stylewriter"}
    entry = config["mcpServers"]["stylewriter"]
    assert entry == {
        "type": "http",
        "url": "https://api.x/mcp/stylewriter",
        "headers": {"Authorization": "Bearer ${STASH_API_KEY}"},
    }


async def test_registry_row_wins_a_name_collision(client):
    user_id = await _register(client)
    await _skill(user_id, "stylewriter", "mcp: stylewriter https://api.x/mcp/stylewriter")
    await mcp_server_service.create_server(
        user_id, "stylewriter", "stdio", "my-own-server", None, {}, {}
    )
    config = await mcp_server_service.sprite_config(user_id)
    assert config["mcpServers"]["stylewriter"]["type"] == "stdio"


async def test_turn_env_carries_a_key_for_the_header(client, monkeypatch):
    user_id = await _register(client)
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")
    env = await sprite_service.agent_env(user_id)
    assert env["STASH_API_KEY"].startswith(("mc_", "st_")) and "STASH_URL" not in env
    # One key per user per process, not one per turn.
    assert (await sprite_service.agent_env(user_id))["STASH_API_KEY"] == env["STASH_API_KEY"]
