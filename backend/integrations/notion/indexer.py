"""Notion → source_documents indexer.

A Notion source's `external_ref` is a page or database id (auto-detected, like
the old importer). Pages are walked recursively — each page and child page
becomes a source document rendered to markdown via the shared block renderer.
Databases are walked row by row, each row a document. Everything is keyed by a
title-based path so the agent navigates the workspace like a file system.
"""

from __future__ import annotations

import json
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
    lines, child_ids = await fetch_block_tree(client, page_id)
    path = f"{prefix}{title}"
    await source_service.upsert_document(
        source_id=source_id,
        workspace_id=workspace_id,
        path=path,
        name=title,
        kind="note",
        content="\n".join(lines),
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
            await source_service.upsert_document(
                source_id=source_id,
                workspace_id=workspace_id,
                path=path,
                name=title,
                kind="note",
                content=json.dumps(props),
                external_ref=row.get("id"),
            )
            present.append(path)
        if not payload.get("has_more"):
            return
        cursor = payload.get("next_cursor")


async def index_notion(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    resource_id = normalize_resource_id(source["external_ref"])

    token = await get_valid_token(owner_user_id, "notion")
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_API_VERSION}
    present: list[str] = []

    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
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

    await source_service.soft_delete_missing(source_id, present)
    logger.info("notion source %s: indexed %d document(s)", resource_id, len(present))
    return None
