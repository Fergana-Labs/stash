"""Tests for the anonymous public pastes API (joinstash.ai/pages pastebin)."""

from httpx import AsyncClient


async def _create(client: AsyncClient, **overrides) -> dict:
    body = {"content": "# Hello\n\nworld", "content_type": "markdown", **overrides}
    resp = await client.post("/api/v1/pastes", json=body)
    assert resp.status_code == 201
    return resp.json()


async def test_create_returns_edit_token_once(client: AsyncClient):
    paste = await _create(client)
    assert paste["edit_token"]
    assert paste["slug"].startswith("hello-")

    read = await client.get(f"/api/v1/pastes/{paste['slug']}")
    assert read.status_code == 200
    assert "edit_token" not in read.json()


async def test_title_derived_from_markdown_heading(client: AsyncClient):
    paste = await _create(client, content="# My Cool Page\n\nbody")
    assert paste["title"] == "My Cool Page"


async def test_title_derived_from_html_title_tag(client: AsyncClient):
    paste = await _create(
        client,
        content="<html><head><title>Mini Site</title></head><body>hi</body></html>",
        content_type="html",
    )
    assert paste["title"] == "Mini Site"


async def test_explicit_title_wins(client: AsyncClient):
    paste = await _create(client, title="Named")
    assert paste["title"] == "Named"


async def test_get_increments_view_count(client: AsyncClient):
    paste = await _create(client)
    first = await client.get(f"/api/v1/pastes/{paste['slug']}")
    second = await client.get(f"/api/v1/pastes/{paste['slug']}")
    assert second.json()["view_count"] == first.json()["view_count"] + 1


async def test_get_unknown_slug_404(client: AsyncClient):
    resp = await client.get("/api/v1/pastes/nope-000000")
    assert resp.status_code == 404


async def test_raw_format_returns_source(client: AsyncClient):
    paste = await _create(client, content="# Raw me")
    resp = await client.get(f"/api/v1/pastes/{paste['slug']}?format=raw")
    assert resp.status_code == 200
    assert resp.text == "# Raw me"
    assert resp.headers["content-type"].startswith("text/markdown")

    html = await _create(client, content="<html><body>hi</body></html>", content_type="html")
    resp = await client.get(f"/api/v1/pastes/{html['slug']}?format=raw")
    assert resp.headers["content-type"].startswith("text/plain")


async def test_feed_lists_recent_without_content(client: AsyncClient):
    paste = await _create(client, title="Feed Item")
    resp = await client.get("/api/v1/pastes")
    assert resp.status_code == 200
    entry = next(p for p in resp.json()["pastes"] if p["slug"] == paste["slug"])
    assert entry["title"] == "Feed Item"
    assert "content" not in entry
    assert "edit_token" not in entry


async def test_patch_with_token_updates(client: AsyncClient):
    paste = await _create(client)
    resp = await client.patch(
        f"/api/v1/pastes/{paste['slug']}?token={paste['edit_token']}",
        json={"content": "# Edited", "title": "New Title"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "# Edited"
    assert body["title"] == "New Title"


async def test_patch_keeps_title_when_blank(client: AsyncClient):
    paste = await _create(client, title="Keep Me")
    resp = await client.patch(
        f"/api/v1/pastes/{paste['slug']}?token={paste['edit_token']}",
        json={"content": "# Edited"},
    )
    assert resp.json()["title"] == "Keep Me"


async def test_patch_with_wrong_token_404(client: AsyncClient):
    paste = await _create(client)
    resp = await client.patch(
        f"/api/v1/pastes/{paste['slug']}?token=wrong",
        json={"content": "# Hijacked"},
    )
    assert resp.status_code == 404


async def test_invalid_content_type_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/pastes",
        json={"content": "x", "content_type": "javascript"},
    )
    assert resp.status_code == 422


async def test_unlisted_paste_hidden_from_feed(client: AsyncClient):
    paste = await _create(client, title="Hidden Gem", visibility="unlisted")
    feed = await client.get("/api/v1/pastes")
    assert all(p["slug"] != paste["slug"] for p in feed.json()["pastes"])

    # Still readable by anyone with the link.
    read = await client.get(f"/api/v1/pastes/{paste['slug']}")
    assert read.status_code == 200
    assert read.json()["visibility"] == "unlisted"


async def test_private_visibility_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/pastes",
        json={"content": "x", "content_type": "markdown", "visibility": "private"},
    )
    assert resp.status_code == 422


async def test_public_edit_allows_tokenless_patch(client: AsyncClient):
    paste = await _create(client, public_edit=True)
    resp = await client.patch(
        f"/api/v1/pastes/{paste['slug']}",
        json={"content": "# Edited by a stranger"},
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "# Edited by a stranger"


async def test_tokenless_patch_404s_without_public_edit(client: AsyncClient):
    paste = await _create(client)
    resp = await client.patch(
        f"/api/v1/pastes/{paste['slug']}",
        json={"content": "# Hijacked"},
    )
    assert resp.status_code == 404
