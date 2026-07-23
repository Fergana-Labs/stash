"""The home feed: one flat stream — community skills + public pages for
everyone, resurfaced items from the caller's own stash when signed in.
Resurfacing must be deterministic within a day and only ever offer old
saves; the feed re-encounters the archive, it doesn't echo this week."""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import feed_service, source_service

from .conftest import unique_name

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("feed"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body["id"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _publish_skill(client: AsyncClient, api_key: str, title: str) -> None:
    folder = await client.post("/api/v1/me/folders", json={"name": title}, headers=_auth(api_key))
    assert folder.status_code == 201
    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": f"{title} brief", "content": f"# {title}", "folder_id": folder.json()["id"]},
        headers=_auth(api_key),
    )
    assert page.status_code == 201
    published = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder.json()["id"], "title": title, "discoverable": True},
        headers=_auth(api_key),
    )
    assert published.status_code == 201


async def _old_x_save(pool, owner_id: str, tweet_id: str, text: str, days_old: int) -> None:
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="x_saves",
        external_ref=f"acct-{unique_name('x')}",
        display_name="X",
    )
    await pool.execute(
        "INSERT INTO x_save_docs (owner_user_id, source_id, path, name, kind, external_ref, "
        "content, hydration_status, created_at) "
        f"VALUES ($1, $2, $3, $4, 'Bookmark', $3, $5, 'done', now() - interval '{int(days_old)} days')",
        UUID(owner_id),
        UUID(source["id"]),
        tweet_id,
        f"@someone - {tweet_id}",
        text,
    )


async def _old_clip_page(client: AsyncClient, api_key: str, pool, name: str, days_old: int) -> str:
    clips = await client.post("/api/v1/me/folders", json={"name": "Clips"}, headers=_auth(api_key))
    assert clips.status_code == 201
    raw = await client.post(
        "/api/v1/me/folders",
        json={"name": "raw", "parent_folder_id": clips.json()["id"]},
        headers=_auth(api_key),
    )
    assert raw.status_code == 201
    page = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": name,
            "content": "<p>a saved article body</p>",
            "folder_id": raw.json()["id"],
        },
        headers=_auth(api_key),
    )
    assert page.status_code == 201
    page_id = page.json()["id"]
    await pool.execute(
        f"UPDATE pages SET created_at = now() - interval '{int(days_old)} days' WHERE id = $1",
        UUID(page_id),
    )
    return page_id


async def test_signed_out_feed_is_community_only(client: AsyncClient):
    api_key, _ = await _register(client)
    await _publish_skill(client, api_key, unique_name("Skillful"))
    paste = await client.post(
        "/api/v1/pastes", json={"content": "# hello", "content_type": "markdown"}
    )
    assert paste.status_code == 201

    resp = await client.get("/api/v1/feed")

    assert resp.status_code == 200
    body = resp.json()
    kinds = {item["kind"] for item in body["items"]}
    assert "skill" in kinds
    assert "public_page" in kinds
    assert "resurface" not in kinds
    skill = next(i for i in body["items"] if i["kind"] == "skill")
    assert "install_count" in skill["data"]


async def test_resurfaces_only_old_saves_and_is_deterministic(client: AsyncClient, pool):
    api_key, owner_id = await _register(client)
    await _old_x_save(pool, owner_id, "9001", "an old banger about memory systems", days_old=30)
    await _old_x_save(pool, owner_id, "9002", "saved five minutes ago", days_old=0)
    page_id = await _old_clip_page(client, api_key, pool, "Why wikis compound", days_old=30)

    first = await client.get("/api/v1/feed", headers=_auth(api_key))
    second = await client.get("/api/v1/feed", headers=_auth(api_key))

    assert first.status_code == 200
    resurfaced = [i["data"] for i in first.json()["items"] if i["kind"] == "resurface"]
    titles = {r["title"] for r in resurfaced}
    assert "@someone - 9001" in titles
    assert "Why wikis compound" in titles
    assert not any("9002" in r["title"] for r in resurfaced)  # this week never resurfaces

    x_item = next(r for r in resurfaced if r["source"] == "x")
    assert x_item["external_url"] == "https://x.com/i/status/9001"
    assert x_item["preview"] == "an old banger about memory systems"
    clip_item = next(r for r in resurfaced if r["source"] == "clip")
    assert clip_item["app_url"] == f"/p/{page_id}"
    assert "a saved article body" in clip_item["preview"]  # tags stripped

    # Same day, same feed — the sample must not churn between requests.
    assert first.json()["items"] == second.json()["items"]


async def test_interleave_lands_a_resurface_card_every_fourth_slot():
    skills = [{"slug": f"s{i}"} for i in range(6)]
    pages = [{"slug": f"p{i}"} for i in range(3)]
    resurfaced = [{"title": f"r{i}"} for i in range(3)]

    items = feed_service._interleave(skills, pages, resurfaced)

    assert len(items) == 12
    assert [items[i]["kind"] for i in (3, 7, 11)] == ["resurface"] * 3
    # Community keeps its own rhythm: two skills, then a public page.
    assert [i["kind"] for i in items[:3]] == ["skill", "skill", "public_page"]
