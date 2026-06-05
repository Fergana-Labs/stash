"""Asana project → asana_documents indexer (index only; search federated).

An Asana source's external_ref is a project gid. We don't copy task bodies —
Asana's own search (`/tasks/search`, paid tiers) is used live (see `search_asana`)
and the body is fetched lazily on read (`fetch_asana_content`). The sync only
builds the navigable index: one row per task keyed by its gid.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

API_BASE = "https://app.asana.com/api/1.0"
TASKS_URL = API_BASE + "/projects/{project_gid}/tasks"
# Fields rendered for a full read (lazy fetch).
TASK_FIELDS = "name,notes,completed,assignee.name,due_on,permalink_url"
PAGE_SIZE = 100
MAX_TASKS = 2000
SEARCH_LIMIT = 25


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


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def index_asana(source: dict) -> str | None:
    """Build the navigable index only — one row per task (gid + name), no body."""
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])
    project_gid = source["external_ref"]

    token = await get_valid_token(owner_user_id, "asana")
    url = TASKS_URL.format(project_gid=project_gid)

    present: list[str] = []
    offset: str | None = None
    async with httpx.AsyncClient(timeout=60.0, headers=_headers(token)) as client:
        while len(present) < MAX_TASKS:
            params = {"opt_fields": "name", "limit": PAGE_SIZE}
            if offset:
                params["offset"] = offset
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            for task in payload.get("data", []):
                gid = task.get("gid")
                if not gid:
                    continue
                await source_service.upsert_index_row(
                    table="asana_documents",
                    source_id=source_id,
                    workspace_id=workspace_id,
                    path=gid,
                    name=task.get("name") or "(untitled task)",
                    kind="task",
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


async def search_asana(source: dict, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Federated search via Asana's `/tasks/search` (paid tiers only). Scoped to
    the project; returns hits keyed by task gid (the index path)."""
    owner_user_id = UUID(source["owner_user_id"])
    project_gid = source["external_ref"]
    token = await get_valid_token(owner_user_id, "asana")
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        # The search endpoint is workspace-scoped; resolve the project's workspace.
        proj = await client.get(
            f"{API_BASE}/projects/{project_gid}", params={"opt_fields": "workspace"}
        )
        proj.raise_for_status()
        workspace_gid = proj.json()["data"]["workspace"]["gid"]
        resp = await client.get(
            f"{API_BASE}/workspaces/{workspace_gid}/tasks/search",
            params={"text": query, "projects.any": project_gid, "opt_fields": "name", "limit": min(limit, 100)},
        )
        resp.raise_for_status()
        tasks = resp.json().get("data", [])
    return [
        {"ref": t["gid"], "name": t.get("name") or t["gid"], "snippet": t.get("name") or ""}
        for t in tasks
        if t.get("gid")
    ]


async def fetch_asana_content(owner_user_id: UUID, gid: str) -> str:
    """Lazy read: render a single task. `external_ref` is the task gid."""
    token = await get_valid_token(owner_user_id, "asana")
    async with httpx.AsyncClient(timeout=30.0, headers=_headers(token)) as client:
        resp = await client.get(f"{API_BASE}/tasks/{gid}", params={"opt_fields": TASK_FIELDS})
        resp.raise_for_status()
        return _render_task(resp.json().get("data", {}))
