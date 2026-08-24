"""The legacy session-folder lane coexists with the developer platform.

Migration 0201 converts an account's keyed session folders into end users
without dropping the folders, so the customer's old backend keeps writing
successfully while their new user_id-based code rolls out — the cutover has
no window where writes fail. The price is that legacy-lane sessions written
after conversion lack end_user_id until the sunset migration's sweep; these
tests pin the properties that make that sweep sound: the legacy write still
lands with its folder id, and folder → end user attribution stays derivable.
"""

import uuid

import pytest
from httpx import AsyncClient

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, prefix: str) -> tuple[str, str]:
    name = unique_name(prefix)
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1", "email": f"{name}@test.local"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"], resp.json()["id"]


async def _keyed_folder(client: AsyncClient, key: str, org: str) -> dict:
    resp = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": f"{org} Repair", "external_key": org},
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _convert_account(pool, user_id_str: str, folders: list[dict]) -> None:
    """The shape migration 0201 leaves behind: the account is an active
    developer workspace scope, and each keyed folder has an end_users row."""
    user_id = uuid.UUID(user_id_str)
    wiki_id = await pool.fetchval(
        "INSERT INTO folders (owner_user_id, name, created_by, is_protected) "
        "VALUES ($1, 'External Wiki', $1, true) RETURNING id",
        user_id,
    )
    wikis_id = await pool.fetchval(
        "INSERT INTO folders (owner_user_id, name, created_by, is_protected) "
        "VALUES ($1, 'User Wikis', $1, true) RETURNING id",
        user_id,
    )
    workspace_id = await pool.fetchval(
        "INSERT INTO workspaces (name, domain, scope_user_id, created_by, "
        "                        external_wiki_folder_id, end_user_wikis_folder_id) "
        "VALUES ('Converted', NULL, $1, $1, $2, $3) RETURNING id",
        user_id,
        wiki_id,
        wikis_id,
    )
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id) VALUES ($1, $2)",
        workspace_id,
        user_id,
    )
    for folder in folders:
        user_wiki_id = await pool.fetchval(
            "INSERT INTO folders (owner_user_id, parent_folder_id, name, created_by, "
            "                     is_protected) "
            "VALUES ($1, $2, $3, $1, true) RETURNING id",
            user_id,
            wikis_id,
            folder["external_key"],
        )
        await pool.execute(
            "INSERT INTO end_users (workspace_id, external_id, name, wiki_folder_id) "
            "VALUES ($1, $2, $3, $4)",
            workspace_id,
            folder["external_key"],
            folder["name"],
            user_wiki_id,
        )


def _event(session_id: str, folder_id: str) -> dict:
    return {
        "agent_name": "heavi-chat",
        "event_type": "user_message",
        "content": "hello",
        "session_id": session_id,
        "session_folder_id": folder_id,
    }


@pytest.mark.asyncio
async def test_legacy_keyed_writes_still_land_after_conversion(client: AsyncClient, pool):
    """Zero-downtime cutover: after the account is converted, the old
    backend's writes keep working unchanged — resolution and upload both —
    and the session keeps its folder id so the sunset sweep can attribute it."""
    key, user_id = await _register(client, "coexist")
    folder = await _keyed_folder(client, key, "org_legacy")

    await _convert_account(pool, user_id, [folder])

    resolved = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "org_legacy Repair", "external_key": "org_legacy"},
        headers=_auth(key),
    )
    assert resolved.status_code == 200
    assert resolved.json()["id"] == folder["id"]

    session_id = unique_name("sess")
    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event(session_id, folder["id"])]},
        headers=_auth(key),
    )
    assert resp.status_code == 201

    row = await pool.fetchrow(
        "SELECT session_folder_id, end_user_id FROM sessions "
        "WHERE owner_user_id = $1 AND session_id = $2",
        uuid.UUID(user_id),
        session_id,
    )
    assert str(row["session_folder_id"]) == folder["id"]
    assert row["end_user_id"] is None  # legacy lane: attributed by the sweep, below


@pytest.mark.asyncio
async def test_the_sunset_sweep_attributes_gap_sessions(client: AsyncClient, pool):
    """The sweep the sunset migration runs first: any session still pointing
    at a keyed folder is re-pointed to that folder's end user. This is what
    makes the no-window cutover safe — nothing written through the legacy
    lane can be left behind when the lane is dropped."""
    key, user_id = await _register(client, "sweep")
    folder = await _keyed_folder(client, key, "org_sweep")
    await _convert_account(pool, user_id, [folder])

    session_id = unique_name("sess")
    await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event(session_id, folder["id"])]},
        headers=_auth(key),
    )

    await pool.execute(
        """
        UPDATE sessions s
        SET end_user_id = eu.id
        FROM session_folders sf
        JOIN workspaces w ON w.scope_user_id = sf.owner_user_id
        JOIN end_users eu ON eu.workspace_id = w.id AND eu.external_id = sf.external_key
        WHERE s.session_folder_id = sf.id AND s.end_user_id IS NULL
        """
    )

    swept = await pool.fetchrow(
        "SELECT eu.external_id FROM sessions s JOIN end_users eu ON eu.id = s.end_user_id "
        "WHERE s.owner_user_id = $1 AND s.session_id = $2",
        uuid.UUID(user_id),
        session_id,
    )
    assert swept and swept["external_id"] == "org_sweep"


@pytest.mark.asyncio
async def test_plain_accounts_keep_the_legacy_lane(client: AsyncClient, pool):
    key, _ = await _register(client, "plain")
    folder = await _keyed_folder(client, key, "org_still_legacy")

    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event(unique_name("sess"), folder["id"])]},
        headers=_auth(key),
    )
    assert resp.status_code == 201
