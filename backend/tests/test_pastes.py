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


async def test_feed_paginates(client: AsyncClient):
    # More than one page (page size is 20).
    for i in range(23):
        await _create(client, title=f"Page {i}")

    first = await client.get("/api/v1/pastes")
    body = first.json()
    assert len(body["pastes"]) == 20
    assert body["has_more"] is True

    second = await client.get("/api/v1/pastes?offset=20")
    body2 = second.json()
    assert len(body2["pastes"]) == 3
    assert body2["has_more"] is False

    # No overlap between the two pages.
    slugs1 = {p["slug"] for p in body["pastes"]}
    slugs2 = {p["slug"] for p in body2["pastes"]}
    assert slugs1.isdisjoint(slugs2)


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


async def test_toggle_comments_enabled(client: AsyncClient):
    paste = await _create(client)
    assert paste["comments_enabled"] is True

    resp = await client.patch(
        f"/api/v1/pastes/{paste['slug']}?token={paste['edit_token']}",
        json={"comments_enabled": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["comments_enabled"] is False
    # The toggle-only PATCH must not touch the content.
    assert body["content"] == "# Hello\n\nworld"


async def test_comments_roundtrip(client: AsyncClient):
    paste = await _create(client)
    resp = await client.post(
        f"/api/v1/pastes/{paste['slug']}/comments",
        json={
            "author_name": "Sam",
            "body": "Love this part",
            "quoted_text": "world",
            "prefix": "# Hello\n\n",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["body"] == "Love this part"

    listed = await client.get(f"/api/v1/pastes/{paste['slug']}/comments")
    comments = listed.json()["comments"]
    assert len(comments) == 1
    assert comments[0]["author_name"] == "Sam"
    assert comments[0]["quoted_text"] == "world"


async def test_comment_on_unknown_paste_404(client: AsyncClient):
    resp = await client.post(
        "/api/v1/pastes/nope-000000/comments",
        json={"body": "hello?"},
    )
    assert resp.status_code == 404


async def test_comment_requires_body(client: AsyncClient):
    paste = await _create(client)
    resp = await client.post(f"/api/v1/pastes/{paste['slug']}/comments", json={"body": ""})
    assert resp.status_code == 422


async def _add_comment(client: AsyncClient, slug: str, **overrides) -> dict:
    body = {"body": "a comment", **overrides}
    resp = await client.post(f"/api/v1/pastes/{slug}/comments", json=body)
    assert resp.status_code == 201
    return resp.json()


async def test_add_comment_returns_edit_token_once(client: AsyncClient):
    paste = await _create(client)
    comment = await _add_comment(client, paste["slug"])
    assert comment["edit_token"]
    # The token never comes back out of the list endpoint.
    listed = await client.get(f"/api/v1/pastes/{paste['slug']}/comments")
    assert "edit_token" not in listed.json()["comments"][0]


async def test_edit_comment_with_author_token(client: AsyncClient):
    paste = await _create(client)
    comment = await _add_comment(client, paste["slug"], body="original")
    resp = await client.patch(
        f"/api/v1/pastes/{paste['slug']}/comments/{comment['id']}?token={comment['edit_token']}",
        json={"body": "edited"},
    )
    assert resp.status_code == 200
    assert resp.json()["body"] == "edited"


async def test_edit_comment_wrong_token_404(client: AsyncClient):
    paste = await _create(client)
    comment = await _add_comment(client, paste["slug"])
    resp = await client.patch(
        f"/api/v1/pastes/{paste['slug']}/comments/{comment['id']}?token=wrong",
        json={"body": "edited"},
    )
    assert resp.status_code == 404


async def test_delete_comment_by_author(client: AsyncClient):
    paste = await _create(client)
    comment = await _add_comment(client, paste["slug"])
    resp = await client.delete(
        f"/api/v1/pastes/{paste['slug']}/comments/{comment['id']}?token={comment['edit_token']}"
    )
    assert resp.status_code == 204
    listed = await client.get(f"/api/v1/pastes/{paste['slug']}/comments")
    assert listed.json()["comments"] == []


async def test_delete_comment_by_page_owner(client: AsyncClient):
    paste = await _create(client)
    comment = await _add_comment(client, paste["slug"])
    # The page's edit_token moderates any comment on the page.
    resp = await client.delete(
        f"/api/v1/pastes/{paste['slug']}/comments/{comment['id']}?token={paste['edit_token']}"
    )
    assert resp.status_code == 204


async def test_delete_comment_wrong_token_404(client: AsyncClient):
    paste = await _create(client)
    comment = await _add_comment(client, paste["slug"])
    resp = await client.delete(
        f"/api/v1/pastes/{paste['slug']}/comments/{comment['id']}?token=nope"
    )
    assert resp.status_code == 404
    assert (
        len((await client.get(f"/api/v1/pastes/{paste['slug']}/comments")).json()["comments"]) == 1
    )


async def test_reply_to_comment(client: AsyncClient):
    paste = await _create(client)
    top = await _add_comment(client, paste["slug"], body="top-level")
    assert top["parent_id"] is None
    reply = await _add_comment(client, paste["slug"], body="a reply", parent_id=top["id"])
    assert reply["parent_id"] == top["id"]

    listed = (await client.get(f"/api/v1/pastes/{paste['slug']}/comments")).json()["comments"]
    assert len(listed) == 2
    by_id = {c["id"]: c for c in listed}
    assert by_id[reply["id"]]["parent_id"] == top["id"]


async def test_deleting_comment_cascades_replies(client: AsyncClient):
    paste = await _create(client)
    top = await _add_comment(client, paste["slug"], body="top")
    await _add_comment(client, paste["slug"], body="reply", parent_id=top["id"])
    await client.delete(
        f"/api/v1/pastes/{paste['slug']}/comments/{top['id']}?token={top['edit_token']}"
    )
    listed = (await client.get(f"/api/v1/pastes/{paste['slug']}/comments")).json()["comments"]
    assert listed == []


async def test_reply_parent_on_other_page_rejected(client: AsyncClient):
    page_a = await _create(client)
    page_b = await _create(client)
    other = await _add_comment(client, page_b["slug"], body="on page B")
    # Replying on page A with page B's comment as parent must not insert.
    resp = await client.post(
        f"/api/v1/pastes/{page_a['slug']}/comments",
        json={"body": "cross-page reply", "parent_id": other["id"]},
    )
    assert resp.status_code == 404


async def test_comment_token_empty_rejected(client: AsyncClient):
    paste = await _create(client)
    comment = await _add_comment(client, paste["slug"])
    # An empty token must not match the column's '' default on legacy rows.
    resp = await client.delete(f"/api/v1/pastes/{paste['slug']}/comments/{comment['id']}?token=")
    assert resp.status_code == 404


async def test_delete_paste_with_token(client: AsyncClient):
    paste = await _create(client)
    resp = await client.delete(f"/api/v1/pastes/{paste['slug']}?token={paste['edit_token']}")
    assert resp.status_code == 204
    gone = await client.get(f"/api/v1/pastes/{paste['slug']}")
    assert gone.status_code == 404


async def test_delete_paste_wrong_token_404(client: AsyncClient):
    paste = await _create(client)
    resp = await client.delete(f"/api/v1/pastes/{paste['slug']}?token=wrong")
    assert resp.status_code == 404
    # Still readable — the bad-token delete didn't go through.
    still = await client.get(f"/api/v1/pastes/{paste['slug']}")
    assert still.status_code == 200


async def test_delete_cascades_comments(client: AsyncClient):
    paste = await _create(client)
    await client.post(f"/api/v1/pastes/{paste['slug']}/comments", json={"body": "doomed comment"})
    await client.delete(f"/api/v1/pastes/{paste['slug']}?token={paste['edit_token']}")
    # Comments endpoint on a deleted paste returns an empty list, not the orphan.
    listed = await client.get(f"/api/v1/pastes/{paste['slug']}/comments")
    assert listed.json()["comments"] == []


async def test_collab_authorize_paste(client: AsyncClient):
    paste = await _create(client)
    resp = await client.post(
        "/api/v1/collab/authorize-paste",
        json={"document_name": f"paste:{paste['slug']}"},
        headers={"Authorization": f"Bearer {paste['edit_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["can_write"] is True


async def test_collab_authorize_paste_bad_token_404(client: AsyncClient):
    paste = await _create(client)
    resp = await client.post(
        "/api/v1/collab/authorize-paste",
        json={"document_name": f"paste:{paste['slug']}"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 404


async def test_collab_authorize_paste_html_rejected(client: AsyncClient):
    paste = await _create(client, content="<html><body>hi</body></html>", content_type="html")
    resp = await client.post(
        "/api/v1/collab/authorize-paste",
        json={"document_name": f"paste:{paste['slug']}"},
        headers={"Authorization": f"Bearer {paste['edit_token']}"},
    )
    assert resp.status_code == 404
