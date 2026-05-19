"""Notion page importer.

Pulls a Notion page + its block tree and renders to markdown. Covers
the block types people actually have in knowledge bases — paragraphs,
headings (h1-h3), lists (numbered + bulleted), code, quotes, dividers,
callouts, todo items, and toggle blocks. Anything fancier falls back
to its plain-text representation rather than failing the import.

The page's `parent` (database or workspace) is ignored — we always
emit a single Stash page. Importing a database is a follow-up
(register a second resource_type).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from ....celery_app import celery
from ....database import get_pool
from ....tasks._celery_helpers import run_async
from ...storage import get_valid_token
from ..provider import NOTION_API_VERSION

logger = logging.getLogger(__name__)

NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
NOTION_BLOCKS_URL = "https://api.notion.com/v1/blocks/{block_id}/children"


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


def _render_block(block: dict, depth: int = 0) -> list[str]:
    """Return markdown lines for one block (children rendered recursively)."""
    btype = block.get("type")
    body = block.get(btype, {}) or {}
    rt = body.get("rich_text", []) or []
    text = _rich_text_to_md(rt)
    indent = "  " * depth
    lines: list[str] = []

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
        # We don't recurse into child pages — surface them as a link-like marker.
        title = body.get("title", "Untitled subpage")
        lines.append(f"{indent}- _(subpage)_ {title}")
    else:
        # Unknown block types fall back to whatever text we can extract.
        if text:
            lines.append(f"{indent}{text}")

    return lines


async def _fetch_block_tree(
    client: httpx.AsyncClient, block_id: str, depth: int = 0, max_depth: int = 6
) -> list[str]:
    """Recursively render a block and its children into markdown lines."""
    if depth > max_depth:
        return [f"{'  ' * depth}_(nesting depth exceeded)_"]

    lines: list[str] = []
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
            lines.extend(_render_block(block, depth))
            if block.get("has_children"):
                child_lines = await _fetch_block_tree(
                    client, block["id"], depth + 1, max_depth
                )
                lines.extend(child_lines)
            if block.get("type") == "toggle":
                lines.append(f"{'  ' * depth}</details>")
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
    return lines


def _extract_title(page_meta: dict) -> str:
    props = page_meta.get("properties") or {}
    for value in props.values():
        if (value or {}).get("type") == "title":
            title_runs = value.get("title", []) or []
            text = "".join(r.get("plain_text", "") for r in title_runs).strip()
            if text:
                return text
    return "Imported from Notion"


async def _import(
    user_id: UUID,
    workspace_id: UUID,
    page_id: str,
    folder_id: UUID | None,
) -> dict:
    access_token = await get_valid_token(user_id, "notion")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
    }
    async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
        meta_resp = await client.get(NOTION_PAGE_URL.format(page_id=page_id))
        if meta_resp.status_code == 404:
            raise RuntimeError(
                "Notion page not found — share it with the connected integration first"
            )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        title = _extract_title(meta)
        body_lines = await _fetch_block_tree(client, page_id)

    markdown = "\n".join(line for line in body_lines if line is not None).strip()

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
            title,
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
            title,
            markdown,
            user_id,
        )
    return {"kind": "page", "page_id": str(row["id"]), "name": title}


def _normalize_page_id(raw: str) -> str:
    """Accept either a bare UUID, a dashed UUID, or a notion.so URL.

    Notion URLs look like https://www.notion.so/Workspace/Title-32hexchars or
    https://www.notion.so/Title-32hexchars — the last 32 chars are the
    page id (no dashes). We restore the canonical 8-4-4-4-12 dashed form.
    """
    candidate = raw.strip()
    if "notion.so" in candidate:
        # Take the last path segment.
        candidate = candidate.rstrip("/").rsplit("/", 1)[-1]
        # Strip any title prefix joined by '-' before the hex id.
        if "-" in candidate:
            candidate = candidate.split("-")[-1]
    candidate = candidate.replace("-", "").strip()
    if len(candidate) != 32:
        raise RuntimeError(f"could not parse Notion page id from {raw!r}")
    return f"{candidate[0:8]}-{candidate[8:12]}-{candidate[12:16]}-{candidate[16:20]}-{candidate[20:]}"


@celery.task(name="backend.integrations.notion.importers.page.import_notion_page")
def import_notion_page(
    user_id: str,
    workspace_id: str,
    page_id: str,
    folder_id: str | None = None,
) -> dict:
    return run_async(
        _import(
            user_id=UUID(user_id),
            workspace_id=UUID(workspace_id),
            page_id=_normalize_page_id(page_id),
            folder_id=UUID(folder_id) if folder_id else None,
        )
    )
