"""Asana project → asana_documents indexer (copied content; navigable).

An Asana source's external_ref is a project gid. We page through the project's
tasks and copy each into asana_documents as a text document keyed by the task
gid (names aren't unique). Idempotent re-sync via source_service (content-hash
dedupe + soft-delete of tasks that vanished).
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

TASKS_URL = "https://app.asana.com/api/1.0/projects/{project_gid}/tasks"
TASK_FIELDS = "name,notes,completed,assignee.name,due_on,permalink_url"
PAGE_SIZE = 100
MAX_TASKS = 2000


def _render_task(task: dict) -> str:
    name = task.get("name") or "(untitled task)"
    status = "Completed" if task.get("completed") else "Open"
    assignee = (task.get("assignee") or {}).get("name") or "Unassigned"
    due = task.get("due_on") or "—"
    notes = task.get("notes") or ""
    parts = [
        f"# {name}",
        f"Status: {status}",
        f"Assignee: {assignee}",
        f"Due: {due}",
    ]
    if notes.strip():
        parts.append(f"\n{notes.strip()}")
    return "\n".join(parts)


async def index_asana(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    project_gid = source["external_ref"]

    token = await get_valid_token(owner_user_id, "asana")
    headers = {"Authorization": f"Bearer {token}"}
    url = TASKS_URL.format(project_gid=project_gid)

    present: list[str] = []
    offset: str | None = None
    async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
        while len(present) < MAX_TASKS:
            params = {"opt_fields": TASK_FIELDS, "limit": PAGE_SIZE}
            if offset:
                params["offset"] = offset
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            for task in payload.get("data", []):
                gid = task.get("gid")
                if not gid:
                    continue
                await source_service.upsert_content_document(
                    table="asana_documents",
                    source_id=source_id,
                    workspace_id=workspace_id,
                    path=gid,
                    name=task.get("name") or "(untitled task)",
                    kind="task",
                    content=_render_task(task),
                    external_ref=gid,
                )
                present.append(gid)
            next_page = payload.get("next_page")
            if not next_page or not next_page.get("offset"):
                break
            offset = next_page["offset"]

    await source_service.soft_delete_missing("asana_documents", source_id, present)
    logger.info("asana source %s: indexed %d task(s)", project_gid, len(present))
    return None
