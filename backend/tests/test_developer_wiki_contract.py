"""Heavi's deployed calls keep working without widening any customer's reads."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.services import curation_service, files_tree_service, transcript_usage_service

from .test_developer_platform import _auth, _developer, _event, _mint_workspace_key, _push


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [True, False])
async def test_customer_paths_and_global_skill_catalog(client, pool, legacy):
    key, _, workspace = await _developer(client)
    owner = UUID(workspace["scope_user_id"])
    await pool.execute(
        "UPDATE workspaces SET legacy_wiki_enabled=$1 WHERE id=$2",
        legacy,
        UUID(workspace["id"]),
    )
    internal = await files_tree_service.get_or_create_curated_skill(owner, owner)
    assert internal["is_skill"] is not legacy
    assert internal["name"] == ("Memory" if legacy else "Learned knowledge")
    machine = await _mint_workspace_key(client, key, workspace)
    await _push(
        client,
        machine,
        [_event("acme", "org_a", "Acme"), _event("beta", "org_b", "Beta")],
    )
    feed, more = await curation_service._feed_events(owner, None, datetime.now(UTC), 500)
    assert {event["content"] for event in feed} == {"hello from acme", "hello from beta"}
    assert not more
    users = await pool.fetch(
        "SELECT external_id,skill_folder_id FROM end_users WHERE workspace_id=$1",
        UUID(workspace["id"]),
    )
    for user in users:
        await pool.execute(
            "INSERT INTO pages(owner_user_id,folder_id,name,content_markdown,created_by) "
            "VALUES($1,$2,'Private notes',$3,$1)",
            owner,
            user["skill_folder_id"],
            f"PRIVATE_{user['external_id']}",
        )
    await pool.execute(
        "INSERT INTO pages(owner_user_id,folder_id,name,content_markdown,created_by) "
        "VALUES($1,$2,'Shared notes','SHARED_FACT',$1)",
        owner,
        UUID(workspace["external_skill_folder_id"]),
    )

    private_child = await files_tree_service.create_folder(
        owner, "Private workflow", owner, parent_folder_id=users[0]["skill_folder_id"]
    )
    team = await files_tree_service.create_folder(owner, "Parts cheat sheet", owner)
    async with pool.acquire() as conn:
        for folder in [private_child, team]:
            await files_tree_service.initialize_curated_skill(
                conn, folder["id"], owner, folder["name"]
            )

    root = "/memory" if legacy else "/skills/shared"
    private = "/files/wiki" if legacy else "/skills/personal"
    response = await client.post(
        "/api/v1/me/vfs",
        headers=_auth(machine),
        json={
            "script": f"cat '{root}/Shared notes.md' '{private}/Private notes.md'",
            "user_id": "org_a",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["exit_code"] == 0, response.text
    assert "SHARED_FACT" in response.json()["stdout"]
    assert "PRIVATE_org_a" in response.json()["stdout"]
    assert "PRIVATE_org_b" not in response.json()["stdout"]
    if not legacy:
        old = await client.post(
            "/api/v1/me/vfs", headers=_auth(machine), json={"script": "ls /memory"}
        )
        assert old.json()["exit_code"] != 0

    catalog = await client.get("/api/v1/me/skills", headers=_auth(machine))
    assert catalog.status_code == 200
    listed = {s["folder_id"] for s in catalog.json()["skills"]}
    assert str(team["id"]) in listed
    assert str(private_child["id"]) not in listed
    assert not listed.intersection(str(u["skill_folder_id"]) for u in users)
    assert (workspace["external_skill_folder_id"] in listed) is not legacy
    for user in users:
        document = await client.get(
            f"/api/v1/me/skills/{user['skill_folder_id']}", headers=_auth(machine)
        )
        assert document.status_code == 404


@pytest.mark.asyncio
async def test_wiki_contract_keeps_existing_unmetered_curation(client, pool):
    _, _, workspace = await _developer(client)
    owner = UUID(workspace["scope_user_id"])
    await pool.execute(
        "UPDATE workspaces SET legacy_wiki_enabled=true WHERE scope_user_id=$1", owner
    )
    await pool.execute("UPDATE users SET plan='free' WHERE id=$1", owner)
    now = datetime.now(UTC)
    assert await curation_service.curation_allowance(owner, now) is None
    async with pool.acquire() as conn, conn.transaction():
        await transcript_usage_service.record(
            conn, owner, [{"content_key": "test", "content": "some transcript"}], now
        )
    assert (
        await pool.fetchval("SELECT count(*) FROM transcript_usage WHERE owner_user_id=$1", owner)
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM transcript_meter_events WHERE owner_user_id=$1", owner
        )
        == 0
    )


@pytest.mark.asyncio
async def test_old_console_contract_is_workspace_gated(client, pool):
    key, _, workspace = await _developer(client)
    machine = await _mint_workspace_key(client, key, workspace)
    await _push(client, machine, [_event("acme", "org_a", "Acme")])
    owner = UUID(workspace["scope_user_id"])
    headers = {**_auth(key), "X-Stash-Scope": str(owner)}
    user = await pool.fetchrow(
        "SELECT id,share_skill FROM end_users WHERE workspace_id=$1", UUID(workspace["id"])
    )
    graph = await client.get("/api/v1/me/developer/wiki-graph", headers=headers)
    assert graph.status_code == 404
    patch = await client.patch(
        f"/api/v1/me/users/{user['id']}", json={"share_wiki": False}, headers=headers
    )
    assert patch.status_code == 422
    await pool.execute(
        "UPDATE workspaces SET legacy_wiki_enabled=true WHERE scope_user_id=$1", owner
    )
    listed = await client.get("/api/v1/me/users", headers=headers)
    assert (
        listed.json()["workspace"]["external_wiki_folder_id"]
        == workspace["external_skill_folder_id"]
    )
    assert listed.json()["users"][0]["share_wiki"] is True
    graph = await client.get("/api/v1/me/developer/wiki-graph", headers=headers)
    assert graph.status_code == 200
    graph = await client.get(f"/api/v1/me/users/{user['id']}/wiki-graph", headers=headers)
    assert graph.status_code == 200
    patch = await client.patch(
        f"/api/v1/me/users/{user['id']}", json={"share_wiki": False}, headers=headers
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["share_wiki"] is False
