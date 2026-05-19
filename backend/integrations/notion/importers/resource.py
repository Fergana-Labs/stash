"""Notion resource importer — auto-detects pages vs databases.

Mirrors the Drive importer pattern: one Celery task per provider that
fans out internally by resource type. The user pastes either a page
URL or a database URL; the task probes /v1/pages first, falls back to
/v1/databases on 404. No separate endpoint per resource type — one
import dialog handles both.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ....celery_app import celery
from ....tasks._celery_helpers import run_async
from ...storage import get_valid_token
from ..provider import NOTION_API_VERSION
from .database import import_database
from .page import import_page_recursive, normalize_resource_id

logger = logging.getLogger(__name__)

PROBE_PAGE_URL = "https://api.notion.com/v1/pages/{id}"
PROBE_DATABASE_URL = "https://api.notion.com/v1/databases/{id}"


async def _detect_and_import(
    user_id: UUID,
    workspace_id: UUID,
    resource_id: str,
    folder_id: UUID | None,
) -> dict:
    access_token = await get_valid_token(user_id, "notion")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
    }
    async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
        # Try page first — most users paste page URLs.
        page_resp = await client.get(PROBE_PAGE_URL.format(id=resource_id))
        if page_resp.status_code == 200:
            results = await import_page_recursive(
                client,
                user_id=user_id,
                workspace_id=workspace_id,
                page_id=resource_id,
                folder_id=folder_id,
            )
            return {
                "kind": "pages",
                "imported": results,
                "count": len(results),
            }

        if page_resp.status_code == 404:
            # Could be a database — probe before giving up.
            db_resp = await client.get(PROBE_DATABASE_URL.format(id=resource_id))
            if db_resp.status_code == 200:
                return await import_database(
                    client,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    database_id=resource_id,
                    folder_id=folder_id,
                )
            if db_resp.status_code == 404:
                raise RuntimeError(
                    f"Notion resource {resource_id} not found — "
                    "share the page or database with the connected integration first"
                )
            db_resp.raise_for_status()

        page_resp.raise_for_status()
        # Unreachable — raise_for_status always throws on non-2xx.
        raise RuntimeError("unexpected response while probing Notion resource")


@celery.task(name="backend.integrations.notion.importers.resource.import_notion_resource")
def import_notion_resource(
    user_id: str,
    workspace_id: str,
    resource_id: str,
    folder_id: str | None = None,
) -> dict:
    return run_async(
        _detect_and_import(
            user_id=UUID(user_id),
            workspace_id=UUID(workspace_id),
            resource_id=normalize_resource_id(resource_id),
            folder_id=UUID(folder_id) if folder_id else None,
        )
    )
