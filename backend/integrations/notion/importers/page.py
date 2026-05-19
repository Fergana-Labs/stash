"""Notion page → markdown page (recursive).

Covers the block types people actually have in knowledge bases —
paragraphs, headings, lists, to-do, quotes, callouts, code, dividers,
toggles, bookmarks, images. Anything fancier falls back to its
plain-text representation rather than failing the import.

Recursion: when a page contains `child_page` blocks, we create a
folder named after the parent, place the parent page inside it, and
recurse into each child (also into that folder). A flat Notion page
imports as a single Stash page; a tree-shaped Notion page imports as
a folder tree. Hard caps prevent runaway imports.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from ....database import get_pool
from ....services import files_tree_service

logger = logging.getLogger(__name__)

NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
NOTION_BLOCKS_URL = "https://api.notion.com/v1/blocks/{block_id}/children"

# Safety caps. Hit any of these → the import ends FAILURE with a clear
# error rather than silently truncating.
MAX_RECURSION_DEPTH = 4
MAX_PAGES_PER_IMPORT = 200
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
        resp = await client.get(
            NOTION_BLOCKS_URL.format(block_id=block_id), params=params
        )
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


async def _insert_page(
    workspace_id: UUID,
    folder_id: UUID | None,
    user_id: UUID,
    name: str,
    markdown: str,
) -> dict:
    pool = get_pool()
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO pages (
                workspace_id, folder_id, name, content_markdown,
                content_type, html_layout, created_by
            ) VALUES ($1, $2, $3, $4, 'markdown', 'responsive', $5)
            RETURNING id
            """,
            workspace_id,
            folder_id,
            name,
            markdown,
            user_id,
        )
    except asyncpg.UniqueViolationError:
        row = await pool.fetchrow(
            """
            INSERT INTO pages (
                workspace_id, folder_id, name, content_markdown,
                content_type, html_layout, created_by
            ) VALUES ($1, $2, $3 || ' (imported)', $4, 'markdown', 'responsive', $5)
            RETURNING id
            """,
            workspace_id,
            folder_id,
            name,
            markdown,
            user_id,
        )
    return dict(row)


async def _create_or_get_folder(
    workspace_id: UUID,
    parent_folder_id: UUID | None,
    name: str,
    created_by: UUID,
) -> UUID:
    """mkdir -p one level: create if missing, return existing on duplicate."""
    try:
        folder = await files_tree_service.create_folder(
            workspace_id=workspace_id,
            name=name,
            created_by=created_by,
            parent_folder_id=parent_folder_id,
        )
        return folder["id"]
    except files_tree_service.DuplicateFolderName:
        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT id FROM folders WHERE workspace_id = $1 AND name = $2 "
            "AND parent_folder_id IS NOT DISTINCT FROM $3",
            workspace_id,
            name,
            parent_folder_id,
        )
        if row is None:
            raise
        return row["id"]


async def import_page_recursive(
    client: httpx.AsyncClient,
    user_id: UUID,
    workspace_id: UUID,
    page_id: str,
    folder_id: UUID | None,
    *,
    depth: int = 0,
    visited: set[str] | None = None,
    results: list[dict] | None = None,
) -> list[dict]:
    """Import one Notion page and recurse into its child_page blocks.

    A page with no children → one Stash page in `folder_id`.
    A page with children → a folder named after the page, with the
    parent inside it and each child recursed in alongside.

    Hard caps:
      * recursion depth (MAX_RECURSION_DEPTH)
      * total pages per top-level import (MAX_PAGES_PER_IMPORT)
      * visited set prevents accidental cycles
    """
    visited = visited if visited is not None else set()
    results = results if results is not None else []

    if page_id in visited:
        return results
    if len(visited) >= MAX_PAGES_PER_IMPORT:
        raise RuntimeError(
            f"import exceeded {MAX_PAGES_PER_IMPORT}-page cap (top-level had too many child pages)"
        )
    if depth > MAX_RECURSION_DEPTH:
        # Don't recurse further, but don't fail — surface as a flat
        # page at the deepest allowed level with no children expanded.
        depth = MAX_RECURSION_DEPTH
    visited.add(page_id)

    meta_resp = await client.get(NOTION_PAGE_URL.format(page_id=page_id))
    if meta_resp.status_code == 404:
        raise RuntimeError(
            f"Notion page {page_id} not found — share it with the connected integration first"
        )
    meta_resp.raise_for_status()
    meta = meta_resp.json()
    title = _extract_title(meta)

    body_lines, child_page_ids = await fetch_block_tree(client, page_id)
    markdown = "\n".join(line for line in body_lines if line is not None).strip()

    if child_page_ids and depth < MAX_RECURSION_DEPTH:
        # Wrap the parent + its children in a new folder named after
        # the parent. This preserves the Notion hierarchy.
        target_folder_id = await _create_or_get_folder(
            workspace_id=workspace_id,
            parent_folder_id=folder_id,
            name=title,
            created_by=user_id,
        )
    elif child_page_ids:
        # At the recursion cap: surface a clear marker rather than
        # silently dropping the children. The user can re-import the
        # subtree from a deeper page if they need it.
        marker = (
            f"\n\n---\n\n_{len(child_page_ids)} sub-page(s) were not imported "
            f"(recursion depth limit of {MAX_RECURSION_DEPTH} reached). "
            "Re-import from a deeper page to get them.)_"
        )
        markdown = (markdown + marker).strip()
        target_folder_id = folder_id
        child_page_ids = []
    else:
        target_folder_id = folder_id

    page_row = await _insert_page(
        workspace_id, target_folder_id, user_id, title, markdown
    )
    results.append(
        {
            "kind": "page",
            "page_id": str(page_row["id"]),
            "name": title,
            "depth": depth,
        }
    )

    for child_id in child_page_ids:
        await import_page_recursive(
            client,
            user_id,
            workspace_id,
            child_id,
            target_folder_id,
            depth=depth + 1,
            visited=visited,
            results=results,
        )

    return results


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
    return f"{candidate[0:8]}-{candidate[8:12]}-{candidate[12:16]}-{candidate[16:20]}-{candidate[20:]}"
