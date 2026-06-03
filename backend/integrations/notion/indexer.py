"""Notion → notion_index indexer (index only; body fetched lazily).

A Notion source's `external_ref` is a page or database id (auto-detected). We
walk the page tree (and database rows) to build the navigable path index — each
page/row becomes an INDEX ROW storing its title-based path and the Notion id
(`external_ref`). We never store the body; `read_source` calls
`fetch_notion_content` at read time, rendering the page's blocks to markdown
with the owner's token.

The walk still has to read each page's child blocks to discover sub-pages, so a
traversal hits the API; index-only refers to what we *store*, not how few calls
the crawl makes.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token
from .importers.page import (
    _extract_title,
    fetch_block_tree,
    normalize_resource_id,
)
from .provider import NOTION_API_VERSION

logger = logging.getLogger(__name__)

PAGE_URL = "https://api.notion.com/v1/pages/{id}"
DATABASE_URL = "https://api.notion.com/v1/databases/{id}"
DATABASE_QUERY_URL = "https://api.notion.com/v1/databases/{id}/query"
MAX_PAGE_DEPTH = 8


def _safe(segment: str) -> str:
    return (segment or "Untitled").replace("/", "-").strip() or "Untitled"


def _row_title(props: dict) -> str:
    for value in props.values():
        if value.get("type") == "title":
            parts = [t.get("plain_text", "") for t in value.get("title", [])]
            joined = "".join(parts).strip()
            if joined:
                return joined
    return "Untitled"


async def _index_page(
    client: httpx.AsyncClient,
    *,
    source_id: UUID,
    workspace_id: UUID,
    page_id: str,
    prefix: str,
    present: list[str],
    depth: int,
) -> None:
    if depth > MAX_PAGE_DEPTH:
        return
    meta_resp = await client.get(PAGE_URL.format(id=page_id))
    if meta_resp.status_code != 200:
        return
    title = _safe(_extract_title(meta_resp.json()))
    # Read child blocks only to discover sub-pages; the body isn't stored.
    _, child_ids = await fetch_block_tree(client, page_id)
    path = f"{prefix}{title}"
    await source_service.upsert_index_row(
        table="notion_index",
        source_id=source_id,
        workspace_id=workspace_id,
        path=path,
        name=title,
        kind="note",
        external_ref=page_id,
    )
    present.append(path)
    for child_id in child_ids:
        await _index_page(
            client,
            source_id=source_id,
            workspace_id=workspace_id,
            page_id=child_id,
            prefix=f"{path}/",
            present=present,
            depth=depth + 1,
        )


async def _index_database(
    client: httpx.AsyncClient,
    *,
    source_id: UUID,
    workspace_id: UUID,
    database_id: str,
    present: list[str],
) -> None:
    db_meta = await client.get(DATABASE_URL.format(id=database_id))
    db_meta.raise_for_status()
    db_title = _safe(_extract_title(db_meta.json()))

    cursor: str | None = None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = await client.post(DATABASE_QUERY_URL.format(id=database_id), json=body)
        resp.raise_for_status()
        payload = resp.json()
        for row in payload.get("results", []):
            props = row.get("properties", {}) or {}
            title = _safe(_row_title(props))
            path = f"{db_title}/{title}"
            await source_service.upsert_index_row(
                table="notion_index",
                source_id=source_id,
                workspace_id=workspace_id,
                path=path,
                name=title,
                kind="note",
                external_ref=row.get("id"),
            )
            present.append(path)
        if not payload.get("has_more"):
            return
        cursor = payload.get("next_cursor")


def _notion_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=120.0,
        headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_API_VERSION},
    )


async def index_notion(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    resource_id = normalize_resource_id(source["external_ref"])

    token = await get_valid_token(owner_user_id, "notion")
    present: list[str] = []

    async with _notion_client(token) as client:
        page_probe = await client.get(PAGE_URL.format(id=resource_id))
        if page_probe.status_code == 200:
            await _index_page(
                client,
                source_id=source_id,
                workspace_id=workspace_id,
                page_id=resource_id,
                prefix="",
                present=present,
                depth=0,
            )
        elif page_probe.status_code == 404:
            await _index_database(
                client,
                source_id=source_id,
                workspace_id=workspace_id,
                database_id=resource_id,
                present=present,
            )
        else:
            page_probe.raise_for_status()

    await source_service.soft_delete_missing("notion_index", source_id, present)
    logger.info("notion source %s: indexed %d document(s)", resource_id, len(present))
    return None


async def fetch_notion_content(owner_user_id: UUID, page_id: str) -> str:
    """Lazy read: render a Notion page's blocks to markdown with the owner's
    token."""
    token = await get_valid_token(owner_user_id, "notion")
    async with _notion_client(token) as client:
        lines, _ = await fetch_block_tree(client, page_id)
    return "\n".join(lines)
