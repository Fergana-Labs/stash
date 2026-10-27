"""Candidate retrieval must preserve customer and publication boundaries."""

import importlib.util
import json
from pathlib import Path

import pytest

from backend.services import customer_wiki_search as search
from backend.services import shared_wiki_privacy as privacy

from .test_developer_platform import _developer, _mint_workspace_key
from .test_permissions import _auth
from .test_scoped_curation import dataset as dataset

pytestmark = pytest.mark.asyncio


async def _page(pool, dataset, name, body, *, shared=False, other=False, approve=False):
    folder = (
        dataset.workspace["external_wiki_folder_id"]
        if shared
        else dataset.users["public" if other else "private"]["wiki_folder_id"]
    )
    page = dict(
        await pool.fetchrow(
            "INSERT INTO pages(owner_user_id,created_by,folder_id,name,content_markdown) "
            "VALUES($1,$1,$2,$3,$4) RETURNING *",
            dataset.owner,
            folder,
            name,
            body,
        )
    )
    if approve:
        async with pool.acquire() as conn:
            await privacy.record_approval(conn, dataset.workspace["id"], page)
    return page


async def _search(client, dataset, query, **kwargs):
    response = await client.get(
        "/api/v1/me/vfs/wiki-search",
        params={"query": query, "user_id": "private", **kwargs},
        headers=_auth(dataset.key),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_search_matches_only_approved_shared_and_selected_private(dataset, pool, client):
    own = await _page(pool, dataset, "Fan hub private", "Mack fan hub needs a diagram")
    shared = await _page(
        pool,
        dataset,
        "Fan hub lesson",
        "Fan hub is separate from the clutch",
        shared=True,
        approve=True,
    )
    await _page(
        pool, dataset, "Fan hub other customer", "Fan hub OTHER_CUSTOMER_SECRET", other=True
    )
    await _page(pool, dataset, "Fan hub quarantine", "Fan hub UNREVIEWED_SECRET", shared=True)
    data = await _search(client, dataset, "fan hub")
    assert {p["id"] for p in data["results"]} == {str(own["id"]), str(shared["id"])}
    assert "SECRET" not in json.dumps(data)
    assert data["results"][0]["scope"] == "private"
    assert data["has_more"] is False
    shared_only = await _search(client, dataset, "fan hub", scope="shared")
    assert [p["id"] for p in shared_only["results"]] == [str(shared["id"])]
    unknown = await _search(client, dataset, "fan hub", user_id="not-yet-created")
    assert [p["id"] for p in unknown["results"]] == [str(shared["id"])]


@pytest.mark.parametrize("change", ["body", "name", "folder", "end_user", "deleted"])
async def test_search_rechecks_publication_after_changes(dataset, pool, client, change):
    page = await _page(
        pool, dataset, "Hubometer guide", "Hubometer tire revolutions", shared=True, approve=True
    )
    assert (await _search(client, dataset, "hubometer"))["results"]
    updates = {
        "body": ("content_markdown=$2", "Hubometer changed text"),
        "name": ("name=$2", "Hubometer changed title"),
        "folder": ("folder_id=$2", dataset.users["public"]["wiki_folder_id"]),
        "end_user": ("end_user_id=$2", dataset.users["public"]["id"]),
        "deleted": ("deleted_at=now()", None),
    }
    sql, value = updates[change]
    await pool.execute(
        f"UPDATE pages SET {sql} WHERE id=$1", page["id"], *([value] if value is not None else [])
    )
    assert (await _search(client, dataset, "hubometer"))["results"] == []


async def test_unreviewed_metadata_never_matches_or_ranks(dataset, pool, client):
    page = await _page(
        pool, dataset, "Filter guidance", "A general maintenance lesson", shared=True, approve=True
    )
    await pool.execute(
        "UPDATE pages SET metadata=$2::jsonb WHERE id=$1",
        page["id"],
        {"keywords": "HIDDEN_CUSTOMER_IDENTIFIER"},
    )
    assert (await _search(client, dataset, "HIDDEN_CUSTOMER_IDENTIFIER"))["results"] == []
    data = await _search(client, dataset, "filter")
    assert len(data["results"]) == 1
    assert "metadata" not in data["results"][0]
    assert "HIDDEN" not in json.dumps(data)


async def test_limit_applies_after_authorization_and_reports_more(dataset, pool, client):
    for i in range(5):
        await _page(pool, dataset, f"Compressor {i}", "Compressor exact part", other=True)
    for i in range(2):
        await _page(pool, dataset, f"Compressor own {i}", "Compressor head gasket")
    data = await _search(client, dataset, "compressor", limit=1)
    assert len(data["results"]) == 1
    assert data["has_more"] is True
    assert "own" in data["results"][0]["name"]


async def test_part_number_match_does_not_accept_lookalikes(dataset, pool, client):
    exact = await _page(
        pool, dataset, "Oil filter", "Fleetguard LF17537 fits the verified application"
    )
    await _page(pool, dataset, "Unrelated filter", "Fleetguard LF175370 is a different identifier")
    data = await _search(client, dataset, "lf17537")
    assert [p["id"] for p in data["results"]] == [str(exact["id"])]
    assert "LF17537" in data["results"][0]["excerpt"]


async def test_indexed_command_finds_page_beyond_scan_budget(dataset, pool, client, monkeypatch):
    await pool.executemany(
        "INSERT INTO pages(owner_user_id,created_by,folder_id,name,content_markdown) "
        "VALUES($1,$1,$2,$3,$4)",
        [
            (
                dataset.owner,
                dataset.users["private"]["wiki_folder_id"],
                f"Catalog {i:04}",
                "NeedleGasket" if i == 404 else "Unrelated text",
            )
            for i in range(405)
        ],
    )
    # Indexed candidate search must work without using a broad document-read sweep.
    monkeypatch.setattr("backend.services.vfs_service.MAX_DOCUMENT_READS", 1)
    response = await client.post(
        "/api/v1/me/vfs",
        headers=_auth(dataset.key),
        json={"script": "search 'NeedleGasket'", "user_id": "private"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["exit_code"] == 0
    hits = json.loads(body["stdout"])["results"]
    assert len(hits) == 1
    assert hits[0]["name"] == "Catalog 0404"
    assert hits[0]["path"].startswith("/files/wiki/")
    read = await client.post(
        "/api/v1/me/vfs",
        headers=_auth(dataset.key),
        json={"script": f"cat '{hits[0]['path']}'", "user_id": "private"},
    )
    assert "NeedleGasket" in read.json()["stdout"]
    # A private page moved after candidate retrieval cannot keep its previous access.
    await pool.execute(
        "UPDATE pages SET folder_id=$2 WHERE id=$1::uuid",
        hits[0]["id"],
        dataset.users["public"]["wiki_folder_id"],
    )
    denied = await client.get(
        f"/api/v1/me/vfs/pages/{hits[0]['id']}",
        headers=_auth(dataset.key),
        params={"user_id": "private"},
    )
    assert denied.status_code == 404


async def test_customer_search_requires_auth_and_valid_inputs(dataset, client):
    missing = await client.get("/api/v1/me/vfs/wiki-search", params={"query": "filter"})
    assert missing.status_code in (401, 403)
    for params in ({"query": " "}, {"query": "x", "limit": 51}, {"query": "x", "scope": "all"}):
        bad = await client.get(
            "/api/v1/me/vfs/wiki-search", headers=_auth(dataset.key), params=params
        )
        assert bad.status_code == 422


async def test_other_workspace_cannot_search_customer_wiki(dataset, pool, client):
    await _page(pool, dataset, "Foreign lookup", "ForeignLookupSecret", shared=True, approve=True)
    key, _, workspace = await _developer(client)
    other_key = await _mint_workspace_key(client, key, workspace)
    response = await client.get(
        "/api/v1/me/vfs/wiki-search",
        headers=_auth(other_key),
        params={"query": "ForeignLookupSecret", "user_id": "private"},
    )
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_private_and_title_only_query_filters(dataset, pool, client):
    own = await _page(pool, dataset, "TitleOnlyZXQ", "Plain maintenance guidance")
    await _page(pool, dataset, "TitleOnlyZXQ shared", "Plain guidance", shared=True, approve=True)
    data = await _search(client, dataset, "TitleOnlyZXQ", scope="private")
    assert [p["id"] for p in data["results"]] == [str(own["id"])]


async def test_search_vector_matches_valid_database_index(pool):
    path = Path(__file__).parents[1] / "migrations/versions/0256_customer_wiki_search_index.py"
    spec = importlib.util.spec_from_file_location("search_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SEARCH_VECTOR == search.SEARCH_VECTOR
    assert (
        await pool.fetchval(
            "SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass('idx_pages_customer_search')"
        )
        is True
    )
