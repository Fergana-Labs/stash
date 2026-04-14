"""Unit tests for backend/services/yjs_converter.py.

These are pure unit tests — no database or network required.
"""

import pytest
from pycrdt import Doc

from backend.services.yjs_converter import (
    apply_markdown_update,
    build_fragment_from_markdown,
    cached_yjs_to_markdown,
    invalidate_cache,
    markdown_to_yjs_state,
    yjs_state_to_markdown,
)


def _roundtrip(md: str) -> str:
    """Helper: markdown → yjs → markdown."""
    state = markdown_to_yjs_state(md)
    return yjs_state_to_markdown(state)


# ---------------------------------------------------------------------------
# Round-trip tests per node type
# ---------------------------------------------------------------------------


class TestParagraph:
    def test_simple(self):
        assert _roundtrip("Hello world") == "Hello world"

    def test_multiple(self):
        md = "Para 1\n\nPara 2\n\nPara 3"
        assert _roundtrip(md) == md

    def test_empty(self):
        assert _roundtrip("") == ""


class TestHeadings:
    def test_h1(self):
        assert _roundtrip("# Heading 1") == "# Heading 1"

    def test_h2(self):
        assert _roundtrip("## Heading 2") == "## Heading 2"

    def test_h3(self):
        assert _roundtrip("### Heading 3") == "### Heading 3"

    def test_heading_with_inline(self):
        assert _roundtrip("## **Bold** heading") == "## **Bold** heading"


class TestLists:
    def test_bullet(self):
        md = "- item 1\n- item 2\n- item 3"
        assert _roundtrip(md) == md

    def test_ordered(self):
        md = "1. first\n2. second\n3. third"
        assert _roundtrip(md) == md

    def test_nested_bullet(self):
        md = "- item 1\n  - nested a\n  - nested b\n- item 2"
        assert _roundtrip(md) == md


class TestHorizontalRule:
    def test_hr(self):
        md = "Before\n\n---\n\nAfter"
        assert _roundtrip(md) == md


class TestImage:
    def test_image(self):
        md = "![alt text](image.png)"
        assert _roundtrip(md) == md


class TestWikiLink:
    def test_simple(self):
        md = "See [[My Page]] for details"
        assert _roundtrip(md) == md

    def test_multiple(self):
        md = "See [[Page A]] and [[Page B]] here"
        assert _roundtrip(md) == md

    def test_standalone(self):
        md = "[[Wiki Page]]"
        assert _roundtrip(md) == md


# ---------------------------------------------------------------------------
# Round-trip tests per mark type
# ---------------------------------------------------------------------------


class TestMarks:
    def test_bold(self):
        assert _roundtrip("Some **bold** text") == "Some **bold** text"

    def test_italic(self):
        assert _roundtrip("Some *italic* text") == "Some *italic* text"

    def test_code(self):
        assert _roundtrip("Use `print()` here") == "Use `print()` here"

    def test_strike(self):
        assert _roundtrip("Some ~~struck~~ text") == "Some ~~struck~~ text"

    def test_underline(self):
        assert _roundtrip("Some <u>underlined</u> text") == "Some <u>underlined</u> text"

    def test_subscript(self):
        assert _roundtrip("H<sub>2</sub>O") == "H<sub>2</sub>O"

    def test_superscript(self):
        assert _roundtrip("E=mc<sup>2</sup>") == "E=mc<sup>2</sup>"

    def test_link(self):
        assert _roundtrip("Visit [example](https://example.com) now") == "Visit [example](https://example.com) now"

    def test_stacked_bold_italic(self):
        assert _roundtrip("Some ***bold italic*** text") == "Some ***bold italic*** text"

    def test_bold_link(self):
        md = "Visit [**bold link**](https://example.com)"
        assert _roundtrip(md) == md


# ---------------------------------------------------------------------------
# Create / Read
# ---------------------------------------------------------------------------


class TestCreateRead:
    def test_create_produces_bytes(self):
        state = markdown_to_yjs_state("# Hello")
        assert isinstance(state, bytes)
        assert len(state) > 0

    def test_read_matches_input(self):
        md = "# Title\n\nSome content with **bold**."
        state = markdown_to_yjs_state(md)
        assert yjs_state_to_markdown(state) == md

    def test_empty_creates_valid_state(self):
        state = markdown_to_yjs_state("")
        assert isinstance(state, bytes)
        assert yjs_state_to_markdown(state) == ""


# ---------------------------------------------------------------------------
# Update (apply_markdown_update)
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_update_changes_content(self):
        doc = Doc()
        build_fragment_from_markdown(doc, "# Title\n\nOld content")
        apply_markdown_update(doc, "# Title\n\nNew content")
        result = yjs_state_to_markdown(doc.get_update())
        assert result == "# Title\n\nNew content"

    def test_update_returns_bytes(self):
        doc = Doc()
        build_fragment_from_markdown(doc, "# Title\n\nContent")
        update = apply_markdown_update(doc, "# Title\n\nUpdated")
        assert isinstance(update, bytes)
        assert len(update) > 0

    def test_update_preserves_unchanged(self):
        doc = Doc()
        build_fragment_from_markdown(doc, "# Title\n\nPara 1\n\nPara 2\n\nPara 3")
        apply_markdown_update(doc, "# Title\n\nPara 1\n\n**Changed** para 2\n\nPara 3")
        result = yjs_state_to_markdown(doc.get_update())
        assert "# Title" in result
        assert "Para 1" in result
        assert "**Changed** para 2" in result
        assert "Para 3" in result

    def test_update_add_blocks(self):
        doc = Doc()
        build_fragment_from_markdown(doc, "Para 1")
        apply_markdown_update(doc, "Para 1\n\nPara 2\n\nPara 3")
        result = yjs_state_to_markdown(doc.get_update())
        assert "Para 1" in result
        assert "Para 2" in result
        assert "Para 3" in result

    def test_update_remove_blocks(self):
        doc = Doc()
        build_fragment_from_markdown(doc, "Para 1\n\nPara 2\n\nPara 3")
        apply_markdown_update(doc, "Para 1\n\nPara 3")
        result = yjs_state_to_markdown(doc.get_update())
        assert "Para 1" in result
        assert "Para 2" not in result
        assert "Para 3" in result


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestCache:
    def test_cache_returns_same_result(self):
        state = markdown_to_yjs_state("# Cached")
        r1 = cached_yjs_to_markdown("test-file", state)
        r2 = cached_yjs_to_markdown("test-file", state)
        assert r1 == r2 == "# Cached"

    def test_cache_invalidation(self):
        state = markdown_to_yjs_state("# Original")
        cached_yjs_to_markdown("test-file-2", state)
        invalidate_cache("test-file-2")
        # After invalidation, should still work (just recomputes)
        result = cached_yjs_to_markdown("test-file-2", state)
        assert result == "# Original"


# ---------------------------------------------------------------------------
# Full document test
# ---------------------------------------------------------------------------


class TestFullDocument:
    def test_comprehensive_roundtrip(self):
        md = """# Main Title

## Section 1

A paragraph with **bold**, *italic*, `code`, and ~~strike~~.

A [link](https://example.com) and <u>underline</u>.

H<sub>2</sub>O and E=mc<sup>2</sup>.

- bullet 1
- bullet 2

1. ordered 1
2. ordered 2

Check [[Wiki Page]] here.

---

![image](pic.png)"""
        assert _roundtrip(md) == md
