"""Notion block → markdown renderer + id helpers.

Covers the block types people actually have in knowledge bases —
paragraphs, headings, lists, to-do, quotes, callouts, code, dividers,
toggles, bookmarks, images, tables, child databases. Anything fancier
falls back to its plain-text representation rather than failing.

Reused by backend/integrations/notion/indexer.py to render connected Notion
pages into notion_index. (Formerly also held the import-into-the-file-system
walk; that path was removed when Notion became a connected, indexed source.)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
NOTION_BLOCKS_URL = "https://api.notion.com/v1/blocks/{block_id}/children"
NOTION_DATABASE_URL = "https://api.notion.com/v1/databases/{database_id}"
NOTION_DATABASE_QUERY_URL = "https://api.notion.com/v1/databases/{database_id}/query"

# Cap block nesting so a pathological page can't recurse forever.
MAX_BLOCK_NESTING = 6
# Cap child_database inline rendering to keep big tables from blowing up a page.
CHILD_DATABASE_ROW_LIMIT = 50


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
    elif btype in ("table", "child_database"):
        # Handled inline by fetch_block_tree (needs async children fetch).
        pass
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
            btype = block.get("type")

            # Tables and child databases need their own async children
            # fetch, so they short-circuit the generic walk below.
            if btype == "table":
                lines.extend(await _render_table_block(client, block, depth))
                continue
            if btype == "child_database":
                lines.extend(await _render_child_database_block(client, block, depth))
                continue

            block_lines, block_children = _render_block(block, depth)
            lines.extend(block_lines)
            child_pages.extend(block_children)
            if block.get("has_children"):
                child_lines, nested_children = await fetch_block_tree(
                    client, block["id"], depth + 1, max_depth
                )
                lines.extend(child_lines)
                child_pages.extend(nested_children)
            if btype == "toggle":
                lines.append(f"{'  ' * depth}</details>")
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
    return lines, child_pages


def _cell_to_md(cell: list[dict]) -> str:
    """Render one table_row cell (a rich_text array) to markdown, escaping
    the pipe character so it doesn't break the table syntax."""
    text = _rich_text_to_md(cell)
    return text.replace("|", "\\|").replace("\n", " ")


async def _render_table_block(client: httpx.AsyncClient, block: dict, depth: int) -> list[str]:
    """Render a Notion `table` block as a markdown table.

    Notion's `table` block has `table_width` + `has_column_header`. The rows
    are its children (`table_row` blocks with `cells: list[list[rich_text]]`).
    A `table_row` outside a table context would render as plain rich text,
    but here we fetch them and assemble proper markdown table syntax.
    """
    body = block.get("table", {}) or {}
    width = int(body.get("table_width") or 0)
    has_header = bool(body.get("has_column_header"))
    indent = "  " * depth

    rows: list[list[str]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = await client.get(NOTION_BLOCKS_URL.format(block_id=block["id"]), params=params)
        resp.raise_for_status()
        payload = resp.json()
        for child in payload.get("results", []):
            if child.get("type") != "table_row":
                continue
            cells = child.get("table_row", {}).get("cells") or []
            rendered = [_cell_to_md(c) for c in cells]
            # Pad short rows so every output row has `width` columns.
            while width and len(rendered) < width:
                rendered.append("")
            rows.append(rendered)
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")

    if not rows:
        return []

    col_count = width or max(len(r) for r in rows)
    out: list[str] = []
    if has_header:
        out.append(f"{indent}| {' | '.join(rows[0])} |")
        out.append(f"{indent}| {' | '.join(['---'] * col_count)} |")
        body_rows = rows[1:]
    else:
        # No header → emit a blank header so the markdown parser still
        # treats it as a table.
        out.append(f"{indent}| {' | '.join([''] * col_count)} |")
        out.append(f"{indent}| {' | '.join(['---'] * col_count)} |")
        body_rows = rows
    for row in body_rows:
        out.append(f"{indent}| {' | '.join(row)} |")
    return out


def _row_title_from_props(props: dict) -> str:
    """First title-typed property in a database row → plain string."""
    for value in props.values():
        if (value or {}).get("type") == "title":
            runs = value.get("title", []) or []
            text = "".join(r.get("plain_text", "") for r in runs).strip()
            if text:
                return text
    return "Untitled"


def _scalar_prop_to_str(value: dict) -> str:
    """Render a single property value as a one-line markdown-cell string.

    Handles the common Notion property types we'd want visible in a
    summary table; falls back to the JSON-y `type` marker for the rest.
    """
    if not value:
        return ""
    ptype = value.get("type")
    inner = value.get(ptype) if ptype else None
    if ptype in ("title", "rich_text"):
        return _rich_text_to_md(inner or [])
    if ptype == "number":
        return "" if inner is None else str(inner)
    if ptype == "checkbox":
        return "x" if inner else " "
    if ptype == "url":
        return str(inner or "")
    if ptype == "email":
        return str(inner or "")
    if ptype == "phone_number":
        return str(inner or "")
    if ptype == "select":
        return (inner or {}).get("name", "")
    if ptype == "status":
        return (inner or {}).get("name", "")
    if ptype == "multi_select":
        return ", ".join(item.get("name", "") for item in (inner or []))
    if ptype == "date":
        start = (inner or {}).get("start", "")
        end = (inner or {}).get("end")
        return f"{start} → {end}" if end else start
    if ptype == "people":
        return ", ".join(p.get("name", "") for p in (inner or []))
    if ptype == "formula":
        formula_type = (inner or {}).get("type")
        return str((inner or {}).get(formula_type, ""))
    if ptype == "rollup":
        rollup_type = (inner or {}).get("type")
        if rollup_type == "number":
            return str((inner or {}).get("number", ""))
        if rollup_type == "date":
            return str(((inner or {}).get("date") or {}).get("start", ""))
        return ""
    if ptype == "created_time":
        return str(inner or "")
    if ptype == "last_edited_time":
        return str(inner or "")
    return f"_({ptype})_"


async def _render_child_database_block(
    client: httpx.AsyncClient, block: dict, depth: int
) -> list[str]:
    """Inline-render the first N rows of a `child_database` block.

    Without this, the agent never sees the data inside a nested database — the
    old code emitted only `_(database)_ Title`. We cap row count so a huge
    database doesn't bloat the parent page beyond what an agent can scan.
    """
    body = block.get("child_database", {}) or {}
    title = body.get("title") or "Untitled database"
    indent = "  " * depth
    database_id = block["id"]

    meta_resp = await client.get(NOTION_DATABASE_URL.format(database_id=database_id))
    if meta_resp.status_code != 200:
        return [f"{indent}_(child database `{title}` — could not fetch)_"]
    db_meta = meta_resp.json()
    db_props = db_meta.get("properties") or {}
    # Column order: title first (Notion's convention), then everything else
    # by Notion's stable property order.
    columns: list[str] = []
    title_col: str | None = None
    for name, spec in db_props.items():
        if (spec or {}).get("type") == "title":
            title_col = name
        else:
            columns.append(name)
    if title_col is None:
        title_col = "Name"
    headers = [title_col, *columns]

    rows: list[list[str]] = []
    cursor: str | None = None
    while len(rows) < CHILD_DATABASE_ROW_LIMIT:
        payload: dict = {"page_size": min(100, CHILD_DATABASE_ROW_LIMIT - len(rows))}
        if cursor:
            payload["start_cursor"] = cursor
        resp = await client.post(
            NOTION_DATABASE_QUERY_URL.format(database_id=database_id), json=payload
        )
        if resp.status_code != 200:
            break
        page = resp.json()
        for row in page.get("results", []):
            props = row.get("properties") or {}
            row_cells = [_row_title_from_props(props)]
            for col in columns:
                row_cells.append(_scalar_prop_to_str(props.get(col, {}) or {}))
            rows.append([c.replace("|", "\\|").replace("\n", " ") for c in row_cells])
            if len(rows) >= CHILD_DATABASE_ROW_LIMIT:
                break
        if not page.get("has_more"):
            break
        cursor = page.get("next_cursor")

    if not rows:
        return [f"{indent}_(child database `{title}` — empty)_"]

    out = [f"{indent}**{title}**", ""]
    out.append(f"{indent}| {' | '.join(headers)} |")
    out.append(f"{indent}| {' | '.join(['---'] * len(headers))} |")
    for row in rows:
        out.append(f"{indent}| {' | '.join(row)} |")
    if len(rows) == CHILD_DATABASE_ROW_LIMIT:
        out.append(f"{indent}_(showing first {CHILD_DATABASE_ROW_LIMIT} rows)_")
    return out


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
