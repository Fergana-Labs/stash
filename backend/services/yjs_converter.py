"""
Native Python Yjs ↔ Markdown converter.

Builds pycrdt XmlFragment structures that match TipTap's ProseMirror schema,
eliminating the need for a Node.js collaboration server for conversion.

Supported nodes: paragraph, heading (1-3), bulletList, orderedList, listItem,
                 hardBreak, horizontalRule, image, wikiLinkNode
Supported marks: bold, italic, underline, code, strike, link, subscript, superscript
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from markdown_it import MarkdownIt
from pycrdt import Doc, XmlElement, XmlFragment, XmlText


# ---------------------------------------------------------------------------
# Markdown → Yjs
# ---------------------------------------------------------------------------

# markdown-it token type → TipTap node name
_BLOCK_TAG_MAP = {
    "paragraph": "paragraph",
    "heading": "heading",
    "bullet_list": "bulletList",
    "ordered_list": "orderedList",
    "list_item": "listItem",
}

# markdown-it inline token type → TipTap mark name + attr extractor
_MARK_MAP: dict[str, tuple[str, Any]] = {
    "strong": ("bold", True),
    "em": ("italic", True),
    "s": ("strike", True),
    "code_inline": ("code", True),
}

# HTML tags that map to TipTap marks (not handled by markdown-it natively)
_HTML_MARK_MAP = {
    "u": "underline",
    "sub": "subscript",
    "sup": "superscript",
}

# Wiki link pattern: [[Page Name]]
_WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# Characters to escape in plain text to prevent round-trip reinterpretation
_ESCAPE_RE = re.compile(r"(\\|^#{1,6}\s|`|~~)", re.MULTILINE)


def _get_md_parser() -> MarkdownIt:
    """Create a markdown-it parser with strikethrough enabled."""
    return MarkdownIt().enable("strikethrough")


def _parse_inline_tokens(
    parent: XmlElement,
    children: list,
) -> None:
    """Walk markdown-it inline tokens and append XmlText/XmlElement children to parent.

    Must be called after parent is integrated into a Doc.
    """
    marks: list[dict[str, Any]] = []
    current_text = XmlText()
    parent.children.append(current_text)
    pos = 0

    i = 0
    while i < len(children):
        tok = children[i]

        if tok.type == "text":
            # Split on wiki links
            text = tok.content
            last_end = 0
            for m in _WIKI_LINK_RE.finditer(text):
                # Text before the wiki link
                before = text[last_end : m.start()]
                if before:
                    attrs = _marks_to_attrs(marks) if marks else None
                    current_text.insert(pos, before, attrs)
                    pos += len(before)

                # Wiki link as inline node — need a new XmlText after it
                wl = XmlElement("wikiLinkNode")
                parent.children.append(wl)
                wl.attributes["pageName"] = m.group(1)

                # Start a new XmlText for content after the wiki link
                current_text = XmlText()
                parent.children.append(current_text)
                pos = 0

                last_end = m.end()

            # Remaining text after last wiki link (or all text if no wiki links)
            remaining = text[last_end:]
            if remaining:
                attrs = _marks_to_attrs(marks) if marks else None
                current_text.insert(pos, remaining, attrs)
                pos += len(remaining)

        elif tok.type == "code_inline":
            attrs = {"code": True}
            if marks:
                attrs.update(_marks_to_attrs(marks))
            current_text.insert(pos, tok.content, attrs)
            pos += len(tok.content)

        elif tok.type == "softbreak" or tok.type == "hardbreak":
            # Insert a hardBreak element
            hb = XmlElement("hardBreak")
            parent.children.append(hb)
            current_text = XmlText()
            parent.children.append(current_text)
            pos = 0

        elif tok.type == "image":
            # Image is an inline node
            img = XmlElement("image")
            parent.children.append(img)
            img.attributes["src"] = tok.attrs.get("src", "")
            alt = tok.content or tok.attrs.get("alt", "")
            if alt:
                img.attributes["alt"] = alt
            # New text node after image
            current_text = XmlText()
            parent.children.append(current_text)
            pos = 0

        elif tok.type == "link_open":
            marks.append({"link": {"href": tok.attrs.get("href", "")}})

        elif tok.type == "link_close":
            marks = [m for m in marks if "link" not in m]

        elif tok.type == "html_inline":
            # Handle HTML tags for underline, subscript, superscript
            content = tok.content.strip()
            for html_tag, mark_name in _HTML_MARK_MAP.items():
                if content == f"<{html_tag}>":
                    marks.append({mark_name: True})
                    break
                elif content == f"</{html_tag}>":
                    marks = [m for m in marks if mark_name not in m]
                    break

        elif tok.type.endswith("_open"):
            # Map to TipTap mark
            base = tok.type[: -len("_open")]
            if base in _MARK_MAP:
                mark_name, mark_val = _MARK_MAP[base]
                marks.append({mark_name: mark_val})

        elif tok.type.endswith("_close"):
            base = tok.type[: -len("_close")]
            if base in _MARK_MAP:
                mark_name, _ = _MARK_MAP[base]
                marks = [m for m in marks if mark_name not in m]

        i += 1


def _marks_to_attrs(marks: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge a list of mark dicts into a single attrs dict for XmlText.insert()."""
    result: dict[str, Any] = {}
    for m in marks:
        result.update(m)
    return result


def _walk_tokens(
    tokens: list,
    frag_or_elem: XmlFragment | XmlElement,
    start: int = 0,
) -> int:
    """Walk top-level markdown-it tokens, appending XmlElements to frag_or_elem.

    Returns the index after the last consumed token.
    """
    i = start
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "hr":
            hr = XmlElement("horizontalRule")
            frag_or_elem.children.append(hr)
            i += 1
            continue

        # Block open tokens
        if tok.type.endswith("_open"):
            base = tok.type[: -len("_open")]
            node_name = _BLOCK_TAG_MAP.get(base, base)
            elem = XmlElement(node_name)
            frag_or_elem.children.append(elem)

            # Set heading level — must be string to match TipTap/y-prosemirror
            if base == "heading" and tok.markup:
                elem.attributes["level"] = str(len(tok.markup))

            # Set ordered list start
            if base == "ordered_list" and tok.attrs and tok.attrs.get("start"):
                elem.attributes["start"] = str(tok.attrs["start"])

            # Find matching close and recurse into children
            close_type = base + "_close"
            i += 1
            i = _walk_tokens(tokens, elem, i)
            # Skip the close token
            if i < len(tokens) and tokens[i].type == close_type:
                i += 1
            continue

        # Inline content
        if tok.type == "inline" and tok.children:
            _parse_inline_tokens(frag_or_elem, tok.children)
            i += 1
            continue

        # Block close — return to parent
        if tok.type.endswith("_close"):
            return i

        i += 1

    return i


def build_fragment_from_markdown(doc: Doc, markdown: str) -> None:
    """Populate the 'default' XmlFragment of doc from markdown.

    Clears any existing content first. Doc must already exist.
    """
    frag = doc.get("default", type=XmlFragment)

    # Clear existing content
    n = len(frag.children)
    if n > 0:
        for _ in range(n):
            del frag.children[0]

    if not markdown or not markdown.strip():
        # Empty doc — add one empty paragraph
        p = XmlElement("paragraph")
        frag.children.append(p)
        return

    md = _get_md_parser()
    tokens = md.parse(markdown)
    _walk_tokens(tokens, frag)


def markdown_to_yjs_state(markdown: str) -> bytes:
    """Convert markdown to Yjs binary state (create)."""
    doc = Doc()
    build_fragment_from_markdown(doc, markdown)
    return doc.get_update()


# ---------------------------------------------------------------------------
# Yjs → Markdown
# ---------------------------------------------------------------------------


def _escape_markdown_text(text: str) -> str:
    """Escape characters in plain text that could be misinterpreted as markdown."""
    # Escape backslashes first
    text = text.replace("\\", "\\\\")
    # Escape leading # that looks like a heading
    text = re.sub(r"^(#{1,6})\s", r"\\\1 ", text, flags=re.MULTILINE)
    # Escape backticks
    text = text.replace("`", "\\`")
    # Escape [text](url) patterns
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\[\1\]\(\2\)", text)
    return text


def _render_marks(text: str, attrs: dict[str, Any] | None) -> str:
    """Wrap text with markdown mark syntax based on Yjs text attributes."""
    if not attrs:
        return _escape_markdown_text(text)

    result = _escape_markdown_text(text)

    # Apply marks in a consistent order (innermost first)
    if attrs.get("code"):
        return f"`{text}`"  # No escaping inside code

    if attrs.get("bold"):
        result = f"**{result}**"
    if attrs.get("italic"):
        result = f"*{result}*"
    if attrs.get("strike"):
        result = f"~~{result}~~"
    if attrs.get("underline"):
        result = f"<u>{result}</u>"
    if attrs.get("subscript"):
        result = f"<sub>{result}</sub>"
    if attrs.get("superscript"):
        result = f"<sup>{result}</sup>"

    link = attrs.get("link")
    if link and isinstance(link, dict) and link.get("href"):
        result = f"[{result}]({link['href']})"

    return result


def _render_inline(elem: XmlElement) -> str:
    """Render the inline content of an XmlElement to markdown."""
    parts: list[str] = []

    for i in range(len(elem.children)):
        child = elem.children[i]
        if isinstance(child, XmlText):
            for text, attrs in child.diff():
                parts.append(_render_marks(text, attrs))
        elif isinstance(child, XmlElement):
            if child.tag == "wikiLinkNode":
                page_name = child.attributes.get("pageName") or ""
                parts.append(f"[[{page_name}]]")
            elif child.tag == "hardBreak":
                parts.append("\n")
            elif child.tag == "image":
                src = child.attributes.get("src") or ""
                alt = child.attributes.get("alt") or ""
                parts.append(f"![{alt}]({src})")

    return "".join(parts)


def _render_element(elem: XmlElement, indent: int = 0, list_index: int | None = None) -> str:
    """Render an XmlElement to markdown."""
    tag = elem.tag

    if tag == "paragraph":
        content = _render_inline(elem)
        return f"{content}\n\n"

    if tag == "heading":
        level = int(elem.attributes.get("level") or 1)
        content = _render_inline(elem)
        return f"{'#' * level} {content}\n\n"

    if tag == "bulletList":
        lines: list[str] = []
        for i in range(len(elem.children)):
            child = elem.children[i]
            if isinstance(child, XmlElement) and child.tag == "listItem":
                lines.append(_render_list_item(child, indent, bullet=True, index=None))
        return "".join(lines) + ("\n" if indent == 0 else "")

    if tag == "orderedList":
        lines = []
        for i in range(len(elem.children)):
            child = elem.children[i]
            if isinstance(child, XmlElement) and child.tag == "listItem":
                lines.append(_render_list_item(child, indent, bullet=False, index=i + 1))
        return "".join(lines) + ("\n" if indent == 0 else "")

    if tag == "horizontalRule":
        return "---\n\n"

    if tag == "listItem":
        return _render_list_item(elem, indent, bullet=True, index=None)

    # Fallback: render inline content
    return _render_inline(elem) + "\n\n"


def _render_list_item(
    elem: XmlElement,
    indent: int,
    bullet: bool,
    index: int | None,
) -> str:
    """Render a listItem to markdown."""
    prefix = "  " * indent
    marker = "- " if bullet else f"{index}. "
    parts: list[str] = []

    for i in range(len(elem.children)):
        child = elem.children[i]
        if isinstance(child, XmlElement):
            if child.tag == "paragraph":
                content = _render_inline(child)
                if not parts:
                    parts.append(f"{prefix}{marker}{content}\n")
                else:
                    parts.append(f"{prefix}  {content}\n")
            elif child.tag in ("bulletList", "orderedList"):
                # Nested list
                parts.append(_render_element(child, indent + 1))

    return "".join(parts)


def yjs_state_to_markdown(state: bytes) -> str:
    """Convert Yjs binary state to markdown (read)."""
    doc = Doc()
    doc.apply_update(state)
    frag = doc.get("default", type=XmlFragment)

    parts: list[str] = []
    for i in range(len(frag.children)):
        child = frag.children[i]
        if isinstance(child, XmlElement):
            parts.append(_render_element(child))

    return "".join(parts).strip()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def apply_markdown_update(doc: Doc, new_markdown: str) -> bytes:
    """Apply a markdown update to an existing doc.

    Rebuilds the XmlFragment content from the new markdown. The CRDT
    layer computes the minimal diff automatically — Yjs only transmits
    the actual changes to connected clients, not the full document.

    Returns the incremental update bytes for broadcasting.
    """
    # Capture state vector before changes
    sv_before = doc.get_state()

    # Rebuild the fragment with new content
    build_fragment_from_markdown(doc, new_markdown)

    # Return only the incremental update (what changed)
    return doc.get_update(sv_before)


# ---------------------------------------------------------------------------
# Markdown cache
# ---------------------------------------------------------------------------

_markdown_cache: dict[str, tuple[str, str]] = {}  # file_id → (state_hash, markdown)


def _hash_state(state: bytes) -> str:
    return hashlib.md5(state).hexdigest()


def cached_yjs_to_markdown(file_id: str, state: bytes) -> str:
    """Convert Yjs state to markdown with caching based on state hash."""
    state_hash = _hash_state(state)
    cached = _markdown_cache.get(file_id)
    if cached and cached[0] == state_hash:
        return cached[1]

    markdown = yjs_state_to_markdown(state)
    _markdown_cache[file_id] = (state_hash, markdown)
    return markdown


def invalidate_cache(file_id: str) -> None:
    """Remove a file from the markdown cache."""
    _markdown_cache.pop(file_id, None)
