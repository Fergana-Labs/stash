"""Notion block → markdown renderer + id helpers.

Covers the block types people actually have in knowledge bases —
paragraphs, headings, lists, to-do, quotes, callouts, code, dividers,
toggles, bookmarks, images. Anything fancier falls back to its
plain-text representation rather than failing.

Reused by backend/integrations/notion/indexer.py to render connected Notion
pages into source_documents. (Formerly also held the import-into-the-file-system
walk; that path was removed when Notion became a connected, indexed source.)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
NOTION_BLOCKS_URL = "https://api.notion.com/v1/blocks/{block_id}/children"

# Cap block nesting so a pathological page can't recurse forever.
MAX_BLOCK_NESTING = 6


def _rich_text_to_md(rt: list[dict]) -> str:
    """Convert Notion rich_text array → markdown inline string."""
    out: list[str] = []
    for run in rt or []:
        text = run.get("plain_text", "")
        if not text:
            continue
        anno = run.get("annotations", {}) or {}
        if anno.get("code"):
            text = f"`{text}`"
        if anno.get("bold"):
            text = f"**{text}**"
        if anno.get("italic"):
            text = f"*{text}*"
        if anno.get("strikethrough"):
            text = f"~~{text}~~"
        href = run.get("href")
        if href:
            text = f"[{text}]({href})"
        out.append(text)
    return "".join(out)


def _render_block(block: dict, depth: int = 0) -> tuple[list[str], list[str]]:
    """Render one block.

    Returns (markdown_lines, child_page_ids_to_recurse). child_page
    blocks contribute their id to the recurse list and emit no marker
    — the outer importer turns them into real sibling pages in a folder.
    """
    btype = block.get("type")
    body = block.get(btype, {}) or {}
    rt = body.get("rich_text", []) or []
    text = _rich_text_to_md(rt)
    indent = "  " * depth
    lines: list[str] = []
    child_pages: list[str] = []

    if btype == "paragraph":
        lines.append(f"{indent}{text}" if text else "")
    elif btype == "heading_1":
        lines.append(f"{indent}# {text}")
    elif btype == "heading_2":
        lines.append(f"{indent}## {text}")
    elif btype == "heading_3":
        lines.append(f"{indent}### {text}")
    elif btype == "bulleted_list_item":
        lines.append(f"{indent}- {text}")
    elif btype == "numbered_list_item":
        lines.append(f"{indent}1. {text}")
    elif btype == "to_do":
        mark = "x" if body.get("checked") else " "
        lines.append(f"{indent}- [{mark}] {text}")
    elif btype == "quote":
        lines.append(f"{indent}> {text}")
    elif btype == "callout":
        emoji = (body.get("icon") or {}).get("emoji", "")
        lines.append(f"{indent}> {emoji} {text}".rstrip())
    elif btype == "code":
        lang = body.get("language", "")
        lines.append(f"{indent}```{lang}")
        lines.append(text or "")
        lines.append(f"{indent}```")
    elif btype == "divider":
        lines.append(f"{indent}---")
    elif btype == "toggle":
        lines.append(f"{indent}<details><summary>{text}</summary>")
        lines.append("")
    elif btype == "bookmark":
        url = body.get("url", "")
        caption = _rich_text_to_md(body.get("caption", []) or [])
        lines.append(f"{indent}[{caption or url}]({url})")
    elif btype == "image":
        file = body.get("file") or body.get("external") or {}
        url = file.get("url", "")
        caption = _rich_text_to_md(body.get("caption", []) or [])
        lines.append(f"{indent}![{caption}]({url})")
    elif btype == "child_page":
        # Emit nothing here — child pages are surfaced as separate
        # Stash pages by the recursive importer. The block id is the
        # page id we need to fetch.
        child_pages.append(block["id"])
    elif btype == "child_database":
        # Same idea, but for databases. Not auto-recursed today; surface
        # as a marker the user can re-import explicitly if they want it.
        title = body.get("title", "Untitled database")
        lines.append(f"{indent}- _(database)_ {title}")
    else:
        # Unknown block types fall back to whatever text we can extract.
        if text:
            lines.append(f"{indent}{text}")

    return lines, child_pages


async def fetch_block_tree(
    client: httpx.AsyncClient,
    block_id: str,
    depth: int = 0,
    max_depth: int = MAX_BLOCK_NESTING,
) -> tuple[list[str], list[str]]:
    """Recursively render a block and its children into markdown lines.

    Returns (lines, child_page_ids). child_page_ids accumulates every
    child_page block id seen at any nesting level — the outer importer
    consumes that list to recurse into separate Stash pages.
    """
    if depth > max_depth:
        return [f"{'  ' * depth}_(nesting depth exceeded)_"], []

    lines: list[str] = []
    child_pages: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = await client.get(NOTION_BLOCKS_URL.format(block_id=block_id), params=params)
        if resp.status_code == 404:
            raise RuntimeError(
                "Notion block not found — make sure the page is shared with the integration"
            )
        resp.raise_for_status()
        payload = resp.json()
        for block in payload.get("results", []):
            block_lines, block_children = _render_block(block, depth)
            lines.extend(block_lines)
            child_pages.extend(block_children)
            if block.get("has_children"):
                child_lines, nested_children = await fetch_block_tree(
                    client, block["id"], depth + 1, max_depth
                )
                lines.extend(child_lines)
                child_pages.extend(nested_children)
            if block.get("type") == "toggle":
                lines.append(f"{'  ' * depth}</details>")
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
    return lines, child_pages


def _extract_title(page_meta: dict) -> str:
    props = page_meta.get("properties") or {}
    for value in props.values():
        if (value or {}).get("type") == "title":
            title_runs = value.get("title", []) or []
            text = "".join(r.get("plain_text", "") for r in title_runs).strip()
            if text:
                return text
    return "Imported from Notion"


def normalize_resource_id(raw: str) -> str:
    """Accept a notion.so URL, dashed UUID, or bare 32-char hex; return canonical
    dashed form. Works for both page and database ids (they share format)."""
    candidate = raw.strip()
    if "notion.so" in candidate:
        # Strip any query string (e.g. `?v=...` on database views).
        candidate = candidate.split("?", 1)[0]
        candidate = candidate.rstrip("/").rsplit("/", 1)[-1]
        if "-" in candidate:
            candidate = candidate.split("-")[-1]
    candidate = candidate.replace("-", "").strip()
    if len(candidate) != 32:
        raise RuntimeError(f"could not parse Notion id from {raw!r}")
    return (
        f"{candidate[0:8]}-{candidate[8:12]}-{candidate[12:16]}-{candidate[16:20]}-{candidate[20:]}"
    )
